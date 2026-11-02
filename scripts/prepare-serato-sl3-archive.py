"""Build an offline additive archive experiment; never deploy or execute Serato."""
import argparse
import io
import json
from pathlib import Path
import re
import struct
import zipfile

import importlib.util

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('sl3_candidate', ROOT/'scripts/prepare-serato-sl3-candidate.py')
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)
MEMBER = 'audio/audio_rane_sl3_rebuild.xml'
ARCHIVE = 'userio_resources.bin'


def encode_block(plain, key, reader):
    """Inverse of the independently checked resource decoder, including padding."""
    c.require(type(plain) is bytes and 4 <= len(plain) <= reader.LIMIT-4, 'Bounded plaintext required')
    c.require(len(key) == 4 and all(type(k) is int and 0 <= k <= reader.MASK for k in key), 'Invalid key shape')
    padding = 4-len(plain) % 4
    padded = plain+bytes([padding])*padding
    words = list(struct.unpack('<'+'I'*(len(padded)//4), padded))
    count = len(words)
    total = 0
    z = words[-1]
    for _ in range(6+52//count):
        total = (total+reader.DELTA) & reader.MASK
        e = (total >> 2) & 3
        for p in range(count):
            y = words[(p+1) % count]
            mix = (((z >> 5) ^ ((y << 2) & reader.MASK))+((y >> 3) ^ ((z << 4) & reader.MASK))) & reader.MASK
            mix ^= ((total ^ y)+(key[(p & 3) ^ e] ^ z)) & reader.MASK
            z = words[p] = (words[p]+mix) & reader.MASK
    return struct.pack('<'+'I'*count, *words)


def index_bytes(entries):
    result = bytearray(struct.pack('<Q', len(entries)))
    for entry in entries:
        name = entry['name'].encode('utf-8')
        result.extend(struct.pack('<3Q', entry['size'], entry['offset'], len(name)))
        result.extend(name)
    return bytes(result)


def zip_candidate(xml):
    c.require(type(xml) is bytes and 0 < len(xml) <= 65536, 'Bounded candidate XML required')
    output = io.BytesIO()
    info = zipfile.ZipInfo(MEMBER, (2026, 11, 2, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 0
    info.external_attr = 0x20
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr(info, xml)
    return output.getvalue()


def inspect_index(raw, key, reader):
    c.require(16 <= len(raw) <= reader.LIMIT, 'Bounded archive required')
    size = struct.unpack_from('<Q', raw)[0]
    c.require(8 <= size <= len(raw)-8, 'Index extent invalid')
    plain = reader.decode_block(raw[8:8+size], key)
    entries = reader.parse_index(plain, len(raw), 8+size)
    c.require(encode_block(plain, key, reader) == raw[8:8+size], 'Index inverse differs')
    return size, entries


def append_candidate(raw, xml, key, reader):
    old_size, old = inspect_index(raw, key, reader)
    c.require(MEMBER not in {e['name'] for e in old}, 'Candidate name already present')
    c.require(len(old) < 10000, 'Resource count limit reached')
    payload_start = 8+old_size
    # Keep the original payload, including gaps and suffix, byte-for-byte.
    addition = encode_block(zip_candidate(xml), key, reader)
    rows = [dict(e) for e in old]+[{'name': MEMBER, 'offset': 0, 'size': len(addition)}]
    new_size = len(encode_block(index_bytes(rows), key, reader))
    delta = new_size-old_size
    for entry in rows[:-1]:
        entry['offset'] += delta
    rows[-1]['offset'] = len(raw)+delta
    index = encode_block(index_bytes(rows), key, reader)
    c.require(len(index) == new_size, 'Index storage size changed')
    result = struct.pack('<Q', new_size)+index+raw[payload_start:]+addition
    c.require(len(result) <= reader.LIMIT, 'Output archive too large')
    verified_size, verified = inspect_index(result, key, reader)
    c.require(verified == rows and verified_size == new_size, 'Rebuilt index differs')
    proofs = []
    for before, after in zip(old, verified[:-1]):
        original = raw[before['offset']:before['offset']+before['size']]
        stored = result[after['offset']:after['offset']+after['size']]
        c.require(original == stored, 'Original encrypted member changed')
        plain = reader.decode_block(stored, key)
        c.require(encode_block(plain, key, reader) == stored, 'Member inverse differs')
        contents, crc = reader.unpack_member(stored, key, before['name'])
        proofs.append({'name': before['name'], 'encryptedSha256': c.digest(stored),
                       'decodedSha256': c.digest(contents), 'crc32': crc})
    own, crc = reader.unpack_member(addition, key, MEMBER)
    c.require(own == xml, 'Appended XML differs')
    c.require(result[8+new_size:len(raw)+delta] == raw[payload_start:], 'Original payload suffix changed')
    proof = {'originalMembers': len(old), 'candidateMembers': len(verified), 'allOriginalEncryptedMembersUnchanged': True,
             'allOriginalMemberCrcsPassed': True, 'allOriginalCodecInverseChecksPassed': True,
             'originalPayloadSuffixSha256': c.digest(raw[payload_start:]), 'indexSizeDelta': delta,
             'originalMemberProofsSha256': c.digest(json.dumps(proofs, sort_keys=True, separators=(',', ':')).encode()),
             'candidateMember': MEMBER, 'candidateCrc32': crc, 'candidateXmlSha256': c.digest(xml)}
    return result, proof


def location(path):
    c.require(not path.is_symlink() and not path.is_junction(), 'Reparse output refused')
    absolute = path.absolute()
    c.require(absolute.parent.resolve() == (ROOT/'analysis').resolve() and
              re.fullmatch(r'sl3-archive-candidate-[A-Za-z0-9-]{1,64}', absolute.name), 'Use direct analysis/sl3-archive-candidate-* directory')
    return absolute


def prepare(candidate):
    candidate = c.location(candidate)
    c.require(candidate.is_dir() and {p.name for p in candidate.iterdir()} == {c.XML_NAME, 'candidate.json'}, 'Exact descriptor bundle required')
    context = c.source_context()
    xml = c.candidate_bytes(context['history'], c.schema_device_order(context['schemaBytes']))
    c.require(c.read(candidate/c.XML_NAME, 65536) == xml, 'Candidate XML differs')
    validation = c.validate_schema(xml, context['schemaBytes'])
    original_manifest = c.read(candidate/'candidate.json')
    c.require(c.parsed(original_manifest) == c.manifest(context, xml, validation), 'Candidate source/runtime differs')
    h = c.module('archive_image', 'export-serato-clock-handshake-evidence.py')
    reader = c.module('archive_reader', 'inspect-serato-resource-archive.py')
    app = h.Image(reader.APP_RELATIVE, h.CURRENT_SHA)
    seed = app.data(0x142f2de98, 16)
    key = struct.unpack('<4I', bytes((((x ^ 0xcf) >> (n & 7)) | ((x ^ 0xcf) << ((8-(n & 7)) & 7))) & 255 for n, x in enumerate(seed)))
    relative = str(Path(reader.APP_RELATIVE).with_name(ARCHIVE))
    raw = c.read(ROOT/relative)
    c.require(c.digest(raw) == reader.ARCHIVE_SHA, 'Original archive differs')
    result, proof = append_candidate(raw, xml, key, reader)
    c.require(proof['originalMembers'] == 229 and proof['candidateMembers'] == 230, 'Pinned member inventory differs')
    pins = dict(context['pins'])
    pins['scripts/prepare-serato-sl3-archive.py'] = c.digest(c.read(Path(__file__)))
    report = {'schema': 'sl3.offline-archive-candidate.v1', 'status': 'offline_hypothesis',
              'sourceSha256': pins, 'descriptorManifestSha256': c.digest(original_manifest),
              'originalArchiveSha256': reader.ARCHIVE_SHA, 'archiveSha256': c.digest(result),
              'archiveBytes': len(result), 'schemaValidation': validation, 'preservation': proof,
              'applicationExecuted': False, 'installedApplicationModified': False, 'installedArchiveModified': False,
              'descriptorRegistered': False, 'driverInstalled': False, 'deviceAccess': False, 'audioPlayed': False,
              'currentSeratoAdmissionVerified': False, 'twoDeckDvsVerified': False, 'deploymentApproved': False,
              'integrityBoundary': 'Offline CRC/byte preservation only; no runtime trust/signature or parser acceptance established',
              'remaining': ['Real provider load and duplicate descriptor precedence', 'NONE control/connection hypothesis and omitted legacy controls',
                            'Application integrity/signature checks and explicit install/rollback review',
                            'Measured native profile, driver deployment, physical audio and legitimate current Serato/DVS tests']}
    # Recheck the full read set before any output publication.
    for relative, digest in pins.items():
        c.require(c.digest(c.read(ROOT/relative, 256*1024*1024)) == digest, 'Source changed during archive preparation')
    c.require(c.read(candidate/'candidate.json') == original_manifest and c.read(candidate/c.XML_NAME) == xml, 'Descriptor changed during preparation')
    return result, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--prepare', type=Path)
    mode.add_argument('--validate', type=Path)
    args = parser.parse_args()
    path = location(args.prepare or args.validate) if args.prepare or args.validate else None
    if args.prepare:
        c.require(not path.exists() and path.parent.is_dir(), 'Fresh output directory required')
    if args.validate:
        c.require(path.is_dir() and {p.name for p in path.iterdir()} == {ARCHIVE, 'archive-candidate.json'}, 'Exact archive bundle required')
    result, report = prepare(args.candidate)
    if args.prepare:
        path.mkdir()
        with (path/ARCHIVE).open('xb') as f:
            f.write(result)
        with (path/'archive-candidate.json').open('x', encoding='utf-8', newline='\n') as f:
            json.dump(report, f, indent=2)
            f.write('\n')
    elif args.validate:
        c.require(c.read(path/ARCHIVE) == result, 'Archive bytes differ')
        c.require(c.parsed(c.read(path/'archive-candidate.json')) == report, 'Archive manifest differs')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
