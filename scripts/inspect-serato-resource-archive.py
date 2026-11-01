"""Read the pinned Serato resource container without executing vendor code.

No extracted paths or XML are written. Key material is derived transiently from
the original executable and never included in the metadata report.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import struct
import xml.etree.ElementTree as ET
import zipfile

import pefile

ROOT = Path(__file__).resolve().parents[1]
APP_SHA = '66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265'
ARCHIVE_SHA = '872fc4fdad2eab2ddd34387d2d3c04dd9731c84798d9fdc7bd05ca54e1567db8'
APP_RELATIVE = 'artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe'
LIMIT = 16*1024*1024
MASK = 0xffffffff
DELTA = 0x9e3779b9


def require(condition, message):
    if not condition:
        raise ValueError(message)


def decode_block(data, key):
    require(8 <= len(data) <= LIMIT and len(data) % 4 == 0, 'Invalid encrypted block length')
    require(len(key) == 4 and all(type(k) is int and 0 <= k <= MASK for k in key), 'Invalid key shape')
    words = list(struct.unpack('<' + 'I'*(len(data)//4), data))
    count = len(words)
    total = ((6 + 52//count)*DELTA) & MASK
    y = words[0]
    while total:
        e = (total >> 2) & 3
        for p in range(count-1, -1, -1):
            z = words[p-1] if p else words[-1]
            mix = (((z >> 5) ^ ((y << 2) & MASK)) + ((y >> 3) ^ ((z << 4) & MASK))) & MASK
            mix ^= ((total ^ y) + (key[(p & 3) ^ e] ^ z)) & MASK
            y = words[p] = (words[p] - mix) & MASK
        total = (total - DELTA) & MASK
    plain = struct.pack('<' + 'I'*count, *words)
    padding = plain[-1]
    require(1 <= padding <= 4 and plain[-padding:] == bytes([padding])*padding, 'Invalid resource padding')
    return plain[:-padding]


def parse_index(index, archive_size, payload_start):
    require(8 <= len(index) <= LIMIT and 8 <= payload_start <= archive_size, 'Invalid index bounds')
    count = struct.unpack_from('<Q', index)[0]
    require(0 < count <= 10000, 'Invalid resource count')
    position = 8
    entries = []
    names = set()
    for _ in range(count):
        require(position+24 <= len(index), 'Truncated index record')
        size, offset, name_size = struct.unpack_from('<3Q', index, position)
        position += 24
        require(0 < name_size <= 4096 and position+name_size <= len(index), 'Invalid name length')
        name = index[position:position+name_size].decode('utf-8')
        position += name_size
        path = PurePosixPath(name)
        require(bool(path.parts) and not path.is_absolute() and path.as_posix() == name and all(p not in ('.', '..') for p in path.parts)
                and not any(c in name for c in ('\\', '\0', ':')), 'Invalid resource name')
        require(name not in names, 'Duplicate resource name')
        require(size >= 8 and size <= LIMIT and size % 4 == 0 and payload_start <= offset
                and offset+size <= archive_size, 'Invalid member extent')
        names.add(name)
        entries.append({'name': name, 'offset': offset, 'size': size})
    require(position == len(index), 'Unexpected index suffix')
    end = payload_start
    for entry in sorted(entries, key=lambda e: e['offset']):
        require(entry['offset'] >= end, 'Overlapping member extents')
        end = entry['offset'] + entry['size']
    return entries


def unpack_member(data, key, expected_name):
    decoded = decode_block(data, key)
    with zipfile.ZipFile(io.BytesIO(decoded)) as archive:
        members = archive.infolist()
        require(len(members) == 1, 'Expected exactly one inner ZIP member')
        item = members[0]
        require(item.filename == expected_name and not item.is_dir() and 0 < item.file_size <= LIMIT
                and not item.flag_bits & 1, 'Inner member contract mismatch')
        # ZipFile.read verifies the member CRC. No filesystem extraction occurs.
        contents = archive.read(item)
        require(len(contents) == item.file_size, 'Uncompressed length mismatch')
        return contents, item.CRC


def inspect():
    app = ROOT/APP_RELATIVE
    raw_app = app.read_bytes()
    require(hashlib.sha256(raw_app).hexdigest() == APP_SHA, 'Original executable changed')
    raw = app.with_name('userio_resources.bin').read_bytes()
    require(hashlib.sha256(raw).hexdigest() == ARCHIVE_SHA, 'Original archive changed')
    image = pefile.PE(data=raw_app, fast_load=True)
    seed = image.get_data(0x2f2de98, 16)
    require(len(seed) == 16, 'Missing resource setup bytes')
    key_bytes = bytes((((x ^ 0xcf) >> (i & 7)) | ((x ^ 0xcf) << ((8-(i & 7)) & 7))) & 255 for i, x in enumerate(seed))
    key = struct.unpack('<4I', key_bytes)
    index_size = struct.unpack_from('<Q', raw)[0]
    require(index_size <= len(raw)-8, 'Index exceeds archive')
    index = decode_block(raw[8:8+index_size], key)
    entries = parse_index(index, len(raw), 8+index_size)
    rows = []
    kinds = Counter()
    sl3_nodes = []
    phase = None
    safe_fields = ('vendor_id', 'product_id', 'bcd_device', 'midi_direction', 'has_hid',
                   'requires_usb', 'is_wireless_device', 'num_wireless_decks', 'handshake_type')
    for entry in entries:
        xml, crc = unpack_member(raw[entry['offset']:entry['offset']+entry['size']], key, entry['name'])
        # Permit only a simple local root-name declaration. Reject external
        # identifiers, entity definitions and internal subsets before parsing.
        suffix = PurePosixPath(entry['name']).suffix
        require(suffix in ('.xml', '.xsd'), 'Unexpected resource type')
        if suffix == '.xml':
            declaration_free = re.sub(rb'<!DOCTYPE\s+[A-Za-z_][A-Za-z0-9_.:-]*\s*>', b'', xml, flags=re.IGNORECASE)
            require(b'<!DOCTYPE' not in declaration_free.upper() and b'<!ENTITY' not in declaration_free.upper(),
                    'Unsupported XML declaration in '+entry['name'])
            root = ET.fromstring(declaration_free)
        else:
            # The schema is an asset, not a device definition. Hash and CRC it,
            # without processing its declarations or resolving schema resources.
            root = ET.Element('unparsed_schema_asset')
        descriptors = []
        for node in root.iter():
            if node.tag not in ('native_pro_device', 'native_intro_device', 'osa_device'):
                continue
            fields = {tag: node.find(tag).get('value') for tag in safe_fields if node.find(tag) is not None}
            kinds[node.tag] += 1
            descriptors.append({'kind': node.tag, 'fields': fields})
            try:
                identity = (int(fields.get('vendor_id') or '', 0), int(fields.get('product_id') or '', 0))
            except ValueError:
                identity = None
            if identity == (0x1cc5, 1):
                sl3_nodes.append(entry['name'])
        if entry['name'] == 'hid/hid_mwm_phase.xml':
            phase = descriptors
        rows.append({**entry, 'xmlBytes': len(xml), 'xmlSha256': hashlib.sha256(xml).hexdigest(), 'zipCrc32': crc,
                     'xmlParsed': suffix == '.xml',
                     'recognizedDescriptorKinds': [d['kind'] for d in descriptors]})
    return {'schema': 'sl3.serato.resource-inspection.v1', 'applicationSha256': APP_SHA, 'archiveSha256': ARCHIVE_SHA,
            'archiveBytes': len(raw), 'encryptedIndexBytes': index_size,
            'decodedIndexSha256': hashlib.sha256(index).hexdigest(), 'memberCount': len(rows),
            'allMemberZipCrcsVerified': True, 'xmlMembersParsed': sum(e['xmlParsed'] for e in rows),
            'schemaMembersNotParsed': sum(not e['xmlParsed'] for e in rows), 'descriptorKindCounts': dict(kinds),
            'sl3IdentityMatchesInRecognizedNodes': sl3_nodes,
            'sl3NamedMembers': [e['name'] for e in rows if 'sl3' in e['name'].lower() or 'sl_3' in e['name'].lower()],
            'phaseInteroperabilityFields': phase, 'members': rows,
            'vendorCodeExecuted': False, 'filesExtracted': False, 'applicationChanges': False,
            'limits': ['Only this pinned archive is inspected; other resource providers are not covered',
                       'Scalar descriptor identity fields are inspected, not all possible identity encodings',
                       'Decoded data and interoperability fields do not establish runtime device support or authentication',
                       'No archive writer, injection, signing, driver admission, audio or DVS test']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.output:
        require(not args.output.exists(), 'Existing evidence is never overwritten')
    report = inspect()
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'members'}, indent=2))


if __name__ == '__main__':
    main()
