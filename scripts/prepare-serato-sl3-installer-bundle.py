"""Package an existing SL3 installer offline for an attended Serato experiment."""
import argparse
import hashlib
from pathlib import Path
import runpy
import struct

import pefile


SCRIPTS = Path(__file__).resolve().parent
INSTALLER = 'SL3_Rebuild_Development_x64.exe'


def qt_name_hash(encoded_name):
    value = 0
    for unit, in struct.iter_unpack('>H', encoded_name):
        value = (value << 4) + unit
        value ^= (value & 0xf0000000) >> 23
        value &= 0x0fffffff
    return value


def resource_bundle(name, payload, timestamp_ms=0):
    """Build an uncompressed, single-file Qt version 3 resource."""
    encoded = name.encode('utf-16-be')
    names = struct.pack('>HI', len(encoded) // 2, qt_name_hash(encoded)) + encoded
    contents = struct.pack('>I', len(payload)) + payload
    tree = struct.pack('>IHIIQ', 0, 2, 1, 1, 0)
    tree += struct.pack('>IHHHIQ', 0, 0, 0, 1, 0, timestamp_ms)
    names_offset = 24 + len(contents)
    tree_offset = names_offset + len(names)
    return b'qres' + struct.pack('>5I', 3, tree_offset, 24, names_offset, 0) + contents + names + tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('installer', type=Path)
    parser.add_argument('output_directory', type=Path)
    args = parser.parse_args()
    archive = runpy.run_path(str(SCRIPTS / 'prepare-serato-sl3-archive.py'))
    qrc = runpy.run_path(str(SCRIPTS / 'inspect-serato-qrc-resources.py'))
    codec, image = qrc['codec'], qrc['image_helper']
    if args.installer.name != INSTALLER:
        parser.error(f'expected {INSTALLER}')
    with args.installer.open('rb') as stream:
        payload = stream.read(codec.LIMIT - 1023)
    if not 64 <= len(payload) <= codec.LIMIT - 1024:
        parser.error('installer size is outside the supported bundle bounds')
    pe = pefile.PE(data=payload, fast_load=True)
    if pe.FILE_HEADER.Machine != 0x8664 or pe.FILE_HEADER.Characteristics & 0x2000:
        parser.error('expected a Windows x64 executable')

    app = image.Image(codec.APP_RELATIVE, codec.APP_SHA)
    seed = app.data(0x142f2de98, 16)
    key = struct.unpack('<4I', bytes(
        (((byte ^ 0xcf) >> (index & 7)) | ((byte ^ 0xcf) << ((8 - (index & 7)) & 7))) & 255
        for index, byte in enumerate(seed)
    ))
    plain = resource_bundle(INSTALLER, payload)
    encrypted = archive['encode_block'](plain, key, codec)
    decoded = codec.decode_block(encrypted, key)
    files, nodes = qrc['bundle_index'](decoded)
    codec.require(decoded == plain and nodes == 2 and files == [{
        'path': '/' + INSTALLER, 'territory': 0, 'language': 1, 'flags': 0,
        'storedBytes': len(payload),
    }], 'Installer resource round-trip differs')

    bundle_name = hashlib.md5(INSTALLER.encode('ascii'), usedforsecurity=False).hexdigest() + '.bin'
    output = args.output_directory / bundle_name
    with output.open('xb') as stream:
        stream.write(encrypted)
    print(f'{output}  SHA-256 {hashlib.sha256(encrypted).hexdigest()}')


if __name__ == '__main__':
    main()
