"""Inspect saved kernel image rundown, without starting a session or opening USB.

Metadata agreement is useful version evidence, not a hash of loaded memory or a
USB readiness decision. XPerf's separately added ImageID/RSDS events are ignored.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET

NS = {'e': 'http://schemas.microsoft.com/win/2004/08/events/event',
      't': 'http://schemas.microsoft.com/win/2004/08/events/trace'}
SYSTEM_PROVIDER = '{9e814aad-3204-11d2-9a82-006008a86939}'
IMAGE_GUID = '{2cb15d1d-5fc1-11d2-abe1-00a0c911f518}'
HEADER_GUID = '{68fdd900-4a3e-11d1-84f4-0000f80464e3}'
OPCODES = {2: 'Unload', 3: 'DCStart', 4: 'DCEnd', 10: 'Load'}
V3_FIELDS = {'ImageBase','ImageSize','ProcessId','ImageChecksum','TimeDateStamp','SignatureLevel','SignatureType',
             'Reserved0','DefaultBase','Reserved1','Reserved2','Reserved3','Reserved4','FileName'}
MAX_XML = 512 * 1024 * 1024


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def integer(value, bits=32):
    require(isinstance(value, str), 'Missing numeric property')
    value = value.strip()
    require(value and (value.isdecimal() or
            value.lower().startswith('0x') and all(c in '0123456789abcdefABCDEF' for c in value[2:]) and len(value) > 2),
            'Invalid unsigned property')
    result = int(value, 16 if value.lower().startswith('0x') else 10)
    require(0 <= result < 1 << bits, 'Numeric property exceeds width')
    return result


def canonical_path(value):
    require(isinstance(value, str) and 0 < len(value) <= 32767 and '\0' not in value,
            'Invalid kernel image path')
    require(value.startswith('\\') and '/' not in value and
            all(p not in ('.', '..') for p in value.split('\\')), 'Expected absolute kernel image path')
    return value.casefold()


def image_metadata(path, kernel_path):
    require(256 <= path.stat().st_size <= 32 * 1024 * 1024, 'Image size exceeds bound')
    raw = path.read_bytes()
    require(raw[:2] == b'MZ', 'Expected PE image')
    offset = struct.unpack_from('<I', raw, 0x3c)[0]
    require(offset >= 64 and offset + 24 + 112 <= len(raw) and raw[offset:offset + 4] == b'PE\0\0',
            'Invalid PE header')
    machine, = struct.unpack_from('<H', raw, offset + 4)
    opt_size, = struct.unpack_from('<H', raw, offset + 20)
    magic, = struct.unpack_from('<H', raw, offset + 24)
    require(machine == 0x8664 and magic == 0x20b and opt_size >= 112 and offset + 24 + opt_size <= len(raw),
            'Expected bounded AMD64 PE32+ image')
    timestamp, = struct.unpack_from('<I', raw, offset + 8)
    size, checksum = struct.unpack_from('<I4xI', raw, offset + 24 + 56)
    require(size and timestamp and checksum, 'Image has missing comparison metadata')
    canonical_path(kernel_path)
    require(PureWindowsPath(kernel_path).name.casefold() == path.name.casefold(),
            'Kernel path basename differs from selected image')
    return {'kernelPath': kernel_path, 'sizeOfImage': size, 'timeDateStamp': timestamp,
            'imageChecksum': checksum, 'diskSha256': hashlib.sha256(raw).hexdigest()}


def inspect_xml(path, expected=None):
    """Inspect an already decoded file; callers must preserve its ETL provenance."""
    require(0 < path.stat().st_size <= MAX_XML, 'Decoded XML size exceeds bound')
    # tracerpt writes UTF-8. Reject entity declarations before invoking the parser.
    with path.open('rb') as stream:
        tail = b''
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            scan = tail + block
            require(b'\0' not in scan and b'<!doctype' not in scan.lower() and b'<!entity' not in scan.lower(),
                    'Expected UTF-8 XML without DTD/entities')
            tail = scan[-16:]
    rows = defaultdict(list)
    counts = Counter()
    versions = Counter()
    headers = []
    total = image_events = other_image_opcodes = nonkernel = 0
    with path.open('rb') as parsed_stream:
        iterator = ET.iterparse(parsed_stream, events=('start', 'end'))
        _, root = next(iterator)
        require(root.tag == 'Events', 'Expected tracerpt Events root')
        for kind, event in iterator:
            if kind != 'end' or event.tag != '{' + NS['e'] + '}Event':
                continue
            total += 1
            require(total <= 2_000_000, 'Event count exceeds bound')
            provider = event.find('e:System/e:Provider', NS)
            guid = event.findtext('t:ExtendedTracingInfo/t:EventGuid', namespaces=NS)
            provider_guid = provider.get('Guid', '').lower() if provider is not None else ''
            if guid and guid.lower() in (HEADER_GUID, IMAGE_GUID):
                require(provider_guid == SYSTEM_PROVIDER, 'Classic event has unexpected system provider')
                fields = {}
                for field in event.findall('e:EventData/e:Data', NS):
                    name = field.get('Name')
                    require(name and name not in fields and len(field.text or '') <= 32767,
                            'Duplicate, unnamed or oversized event property')
                    fields[name] = (field.text or '').strip()
                opcode = integer(event.findtext('e:System/e:Opcode', namespaces=NS), 8)
                if guid.lower() == HEADER_GUID and opcode == 0 and 'EventsLost' in fields:
                    headers.append({key: integer(fields.get(key), 64) for key in
                                    ('EventsLost', 'BuffersLost', 'StartTime', 'EndTime')})
                    require(len(headers) <= 64, 'Header count exceeds bound')
                if guid.lower() == IMAGE_GUID:
                    image_events += 1
                    version = integer(event.findtext('e:System/e:Version', namespaces=NS), 8)
                    versions[str(version)] += 1
                    if opcode not in OPCODES:
                        other_image_opcodes += 1
                    else:
                        require(version in (2, 3), 'Unsupported image event version')
                        if version == 3:
                            # Installed Image/EventVersion(3), Image_Load WMI
                            # schema: two uint8 signature fields split the old
                            # reserved word; common image identity fields remain.
                            require(set(fields) == V3_FIELDS, 'Unexpected version-3 image schema')
                            for field, bits in [('SignatureLevel',8),('SignatureType',8),('Reserved0',16),
                                                ('DefaultBase',64),('Reserved1',32),('Reserved2',32),
                                                ('Reserved3',32),('Reserved4',32)]:
                                integer(fields[field], bits)
                        pid = integer(fields.get('ProcessId'))
                        if pid:
                            nonkernel += 1
                        else:
                            require(sum(counts.values()) < 16384, 'Kernel image event count exceeds bound')
                            name = fields.get('FileName')
                            key = canonical_path(name)
                            stamp = event.find('e:System/e:TimeCreated', NS)
                            require(stamp is not None and stamp.get('SystemTime'), 'Missing event timestamp')
                            base = integer(fields.get('ImageBase'), 64)
                            size = integer(fields.get('ImageSize'), 64)
                            require(base and size and size < 1 << 32, 'Invalid loaded image extent')
                            row = {'ordinal': total, 'operation': OPCODES[opcode], 'eventVersion':version, 'time': stamp.get('SystemTime'),
                                   'kernelPath': name, 'imageBase': str(base), 'sizeOfImage': size,
                                   'timeDateStamp': integer(fields.get('TimeDateStamp')),
                                   'imageChecksum': integer(fields.get('ImageChecksum'))}
                            if version == 3:
                                row.update(signatureLevel=integer(fields['SignatureLevel'],8), signatureType=integer(fields['SignatureType'],8))
                            rows[key].append(row)
                            counts[OPCODES[opcode]] += 1
            event.clear()
            root.remove(event)
    require(total > 0, 'No decoded events')
    loss_free = bool(headers) and all(h['EventsLost'] == h['BuffersLost'] == 0 and
                                      0 < h['StartTime'] < h['EndTime'] for h in headers)
    images = []
    identity_keys = ('imageBase', 'sizeOfImage', 'timeDateStamp', 'imageChecksum', 'eventVersion')
    for key in sorted(rows):
        observations = rows[key]
        pair = (len(observations) == 2 and [r['operation'] for r in observations] == ['DCStart', 'DCEnd'] and
                all(observations[0][k] == observations[1][k] for k in identity_keys) and
                all(observations[0][k] for k in ('timeDateStamp', 'imageChecksum')))
        images.append({'canonicalKernelPath': key, 'consistentRundownPair': bool(pair), 'observations': observations})
    comparison = None
    if expected is not None:
        matches = [x for x in images if x['canonicalKernelPath'] == canonical_path(expected['kernelPath'])]
        comparison = {'expected': expected, 'targetPresent': bool(matches),
                      'matchingRundownMetadata': bool(loss_free and len(matches) == 1 and matches[0]['consistentRundownPair'] and
                          all(matches[0]['observations'][0][k] == expected[k] for k in
                              ('sizeOfImage', 'timeDateStamp', 'imageChecksum')))}
    return {'scope': 'Offline classic kernel image metadata; no loaded-memory hash or USB readiness assertion',
            'events': total, 'imageEvents': image_events, 'imageEventVersions':dict(versions), 'nonKernelImageEvents': nonkernel,
            'otherImageOpcodes': other_image_opcodes, 'kernelImageOperations': dict(counts),
            'headers': headers, 'sourceReportsNoLoss': loss_free, 'kernelImages': images,
            'comparison': comparison, 'loadedMemoryIdentityVerified': False,
            'usbWindowQualified': False, 'readinessAdmission': False,
            'limits': ['A rundown pair describes this image trace, not a separately captured USB window.',
                       'Path, size, checksum and timestamp agreement is version evidence, not an RSDS or loaded-memory hash.',
                       'XPerf-added ImageID/RSDS records are not treated as kernel memory identity.',
                       'A missing path, unknown version, zero metadata, reload or disagreement cannot qualify a matching pair.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--etl', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--image', type=Path)
    parser.add_argument('--kernel-path')
    args = parser.parse_args()
    require(bool(args.image) == bool(args.kernel_path), '--image and --kernel-path must be supplied together')
    etl, output = args.etl.resolve(), args.output.resolve()
    require(0 < etl.stat().st_size <= 64 * 1024 * 1024, 'ETL size exceeds bound')
    require(not output.exists() and output.parent.is_dir(), 'Expected new output in an existing directory')
    expected = image_metadata(args.image.resolve(), args.kernel_path) if args.image else None
    tracerpt = Path(os.environ['SystemRoot']) / 'System32/tracerpt.exe'
    before = digest(etl)
    with tempfile.TemporaryDirectory(prefix='sl3-offline-image-') as folder:
        xml = Path(folder) / 'events.xml'
        run = subprocess.run([str(tracerpt), str(etl), '-o', str(xml), '-of', 'XML', '-y'],
                             capture_output=True, timeout=60)
        require(run.returncode == 0, f'Offline trace decoder failed ({run.returncode})')
        result = inspect_xml(xml, expected)
        result['decodedXmlSha256'] = digest(xml)
        result['decoderOutput'] = run.stdout.decode(errors='replace')[-4096:]
    require(digest(etl) == before, 'Source ETL changed during inspection')
    result.update({'sourceEtlSha256': before, 'sourceEtlBytes': etl.stat().st_size,
                   'inspectorSha256': digest(Path(__file__)), 'decoderSha256': digest(tracerpt)})
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ('events', 'kernelImageOperations', 'sourceReportsNoLoss', 'comparison',
                                            'loadedMemoryIdentityVerified', 'readinessAdmission')}))


if __name__ == '__main__':
    main()
