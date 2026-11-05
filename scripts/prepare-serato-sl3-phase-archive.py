"""Rebuild the pinned Serato 5.0.0 Phase diagnostic archive offline."""

import argparse
from pathlib import Path
import runpy
import struct


ROOT = Path(__file__).resolve().parents[1]
INSTALLER_ARCHIVE_SHA = 'f7bfe219438f2f3e135325a4eea67eacf92c44a4990e0aa6d0ae02f5b63b918e'
PHASE_ARCHIVE_SHA = 'd135e6f1c03601cc44b3e5f623eed36af81bbff585332a3fdc8d5d533b2cb66a'
BASE_RATE = b'<sample_rate value="HZ48000" />'
PHASE_RATE = b'<sample_rate value="HZ44100" />'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('installer_archive', type=Path, help='Reviewed 48 kHz installer candidate archive')
    parser.add_argument('--prepare', type=Path, help='Fresh analysis/sl3-archive-candidate-* directory')
    args = parser.parse_args()
    archive = runpy.run_path(str(ROOT / 'scripts/prepare-serato-sl3-archive.py'))
    candidate = archive['c']
    output = archive['location'](args.prepare) if args.prepare else None
    if output:
        candidate.require(not output.exists(), 'Fresh output directory required')

    baseline = candidate.read(args.installer_archive)
    candidate.require(candidate.digest(baseline) == INSTALLER_ARCHIVE_SHA, 'Installer archive differs')
    image = candidate.module('phase_image', 'export-serato-clock-handshake-evidence.py')
    reader = candidate.module('phase_reader', 'inspect-serato-resource-archive.py')
    app = image.Image(reader.APP_RELATIVE, image.CURRENT_SHA)
    original = candidate.read(ROOT / Path(reader.APP_RELATIVE).with_name(archive['ARCHIVE']))
    candidate.require(candidate.digest(original) == reader.ARCHIVE_SHA, 'Original archive differs')
    seed = app.data(0x142f2de98, 16)
    key = struct.unpack('<4I', bytes(
        (((byte ^ 0xcf) >> (index & 7)) | ((byte ^ 0xcf) << ((8 - (index & 7)) & 7))) & 255
        for index, byte in enumerate(seed)
    ))
    _, entries = archive['inspect_index'](baseline, key, reader)
    member = next(entry for entry in entries if entry['name'] == archive['MEMBER'])
    offset = member['offset']
    xml, _ = reader.unpack_member(baseline[offset:offset + member['size']], key, archive['MEMBER'])
    candidate.require(xml.count(BASE_RATE) == 1 and PHASE_RATE not in xml, 'Expected a single 48 kHz nominal rate')
    phase_xml = xml.replace(BASE_RATE, PHASE_RATE)
    result, proof = archive['append_candidate'](original, phase_xml, key, reader)
    candidate.require(candidate.digest(result) == PHASE_ARCHIVE_SHA, 'Phase archive differs from the rehearsed bytes')
    if output:
        output.mkdir()
        with (output / archive['ARCHIVE']).open('xb') as stream:
            stream.write(result)
    print(f'Phase archive SHA-256 {PHASE_ARCHIVE_SHA}')
    print(f'Original members verified: {proof["originalMembers"]}')


if __name__ == '__main__':
    main()
