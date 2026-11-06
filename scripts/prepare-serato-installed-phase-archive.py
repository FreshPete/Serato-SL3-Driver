"""Reproduce the tested Phase archive from an owner's original Serato installation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pefile

ROOT = Path(__file__).resolve().parents[1]
PHASE_SHA = 'd135e6f1c03601cc44b3e5f623eed36af81bbff585332a3fdc8d5d533b2cb66a'
XML_SHA = 'ad522345d4f5fa4a429d1a5e4f737ddf523bb360ed409bd32346a2a680236a86'
HISTORY = 'docs/evidence/serato-legacy-sl3-descriptors.json'
SOURCES = ('scripts/prepare-serato-installed-phase-archive.py', 'scripts/prepare-serato-sl3-archive.py',
           'scripts/prepare-serato-sl3-candidate.py', 'scripts/inspect-serato-resource-archive.py',
           'scripts/validate-descriptor-schema.ps1', 'scripts/prepare-portable-powershell.py', HISTORY)


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def module(name):
    return runpy.run_path(str(ROOT / 'scripts' / name))


def phase_descriptor(candidate, history, schema):
    require(digest(schema) == candidate.SCHEMA_SHA, 'Reviewed current schema required')
    base = candidate.candidate_bytes(history, candidate.schema_device_order(schema))
    # Reproduce the earlier experiment's serialization, including its discarded
    # comment and whitespace. Exact output hashes below prevent recipe drift.
    xml = ET.tostring(ET.fromstring(base), encoding='utf-8', xml_declaration=True)
    substitutions = (
        (b'<driver_detection>', b'<installer><win_x86 name="" /><win_x64 name="SL3_Rebuild_Development_x64.exe" /></installer><driver_detection>'),
        (b'<provides_talk_over', b'<connect_on_finish_install value="true" /><provides_talk_over'),
        (b'<sample_rate value="HZ48000" />', b'<sample_rate value="HZ44100" />'),
    )
    for before, after in substitutions:
        require(xml.count(before) == 1, 'Expected unique descriptor construction point')
        xml = xml.replace(before, after)
    require(digest(xml) == XML_SHA, 'Descriptor differs from tested Phase bytes')
    return xml


def validate(xml, schema, powershell):
    runtime = Path(powershell).absolute()
    with tempfile.TemporaryDirectory(prefix='sl3-installed-phase-schema-') as temporary:
        directory = Path(temporary)
        for name, raw in (('descriptor.xml', xml), ('schema.xsd', schema)):
            with (directory / name).open('xb') as stream:
                stream.write(raw)
        environment = os.environ.copy()
        environment.update(PSModulePath=str(runtime / 'Modules'), POWERSHELL_UPDATECHECK='Off',
                           POWERSHELL_TELEMETRY_OPTOUT='1')
        result = subprocess.run([str(runtime / 'pwsh.exe'), '-NoLogo', '-NoProfile', '-NonInteractive', '-File',
                                 str(ROOT / 'scripts/validate-descriptor-schema.ps1'),
                                 '-SchemaPath', str(directory / 'schema.xsd'), '-XmlPath', str(directory / 'descriptor.xml')],
                                env=environment, capture_output=True, text=True, encoding='utf-8', timeout=45,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        require(result.returncode == 0, 'Descriptor schema validation failed: ' + result.stderr)
        report = json.loads(result.stdout)
        require(report.get('valid') is True and report['schemaSha256'] == digest(schema) and
                report['xmlSha256'] == digest(xml) and report['externalResolution'] is False,
                'Schema validation input binding differs')
        return report


def prepare(application, powershell, runtime_sha, output=None):
    archive = module('prepare-serato-sl3-archive.py')
    candidate = archive['c']
    reader = SimpleNamespace(**module('inspect-serato-resource-archive.py'))
    destination = archive['location'](Path(output)) if output is not None else None
    if destination is not None:
        require(not destination.exists() and destination.parent.is_dir(), 'Fresh archive output directory required')
    pins = {name: digest(candidate.read(ROOT / name)) for name in SOURCES}
    require(pins[HISTORY] == candidate.HISTORY_SHA, 'Reviewed historical specification evidence required')
    targets = json.loads(candidate.read(ROOT / HISTORY))['targets']
    require(len(targets) == 2 and {row['version'] for row in targets} == {'2.5.5', '2.5.6'} and
            candidate.candidate_bytes(targets[0]) == candidate.candidate_bytes(targets[1]),
            'Historical specification evidence differs')
    application = Path(application).absolute()
    require(application.name == 'Serato DJ Pro.exe', 'Expected Serato executable filename')
    image = candidate.read(application, 256 * 1024 * 1024)
    require(digest(image) == reader.APP_SHA, 'Original Serato 5.0.0.1278 executable required')
    source = application.with_name('userio_resources.bin')
    original = candidate.read(source)
    require(digest(original) == reader.ARCHIVE_SHA, 'Original adjacent Serato archive required')
    pe = pefile.PE(data=image, fast_load=True)
    try:
        require(pe.FILE_HEADER.Machine == 0x8664 and pe.OPTIONAL_HEADER.Magic == 0x20b, 'Windows x64 image required')
        seed = pe.get_data(0x2f2de98, 16)
    finally:
        pe.close()
    require(len(seed) == 16, 'Reviewed resource seed location differs')
    key = struct.unpack('<4I', bytes((((value ^ 0xcf) >> (index & 7)) |
                                    ((value ^ 0xcf) << ((8 - (index & 7)) & 7))) & 255
                                   for index, value in enumerate(seed)))
    _, entries = archive['inspect_index'](original, key, reader)
    schemas = [row for row in entries if row['name'] == 'midi/MIDI.xsd']
    require(len(entries) == 229 and len(schemas) == 1, 'Original resource inventory differs')
    row = schemas[0]
    schema, _ = reader.unpack_member(original[row['offset']:row['offset'] + row['size']], key, row['name'])
    xml = phase_descriptor(candidate, targets[0], schema)
    runtime = Path(powershell).absolute()
    require(';' not in str(runtime), 'PowerShell directory cannot contain a semicolon')
    module('prepare-portable-powershell.py')['verify'](runtime, runtime_sha)
    validation = validate(xml, schema, runtime)
    result, proof = archive['append_candidate'](original, xml, key, reader)
    require(digest(result) == PHASE_SHA and proof['originalMembers'] == 229 and proof['candidateMembers'] == 230,
            'Archive differs from tested Phase bytes')
    for name, expected in pins.items():
        require(digest(candidate.read(ROOT / name)) == expected, 'Preparation source changed: ' + name)
    require(digest(candidate.read(application, 256 * 1024 * 1024)) == reader.APP_SHA and
            digest(candidate.read(source)) == reader.ARCHIVE_SHA, 'Original input changed during preparation')
    report = {'schema': 'sl3.installed-phase-archive-preparation.v1', 'sourcePins': pins,
              'applicationSha256': reader.APP_SHA, 'originalArchiveSha256': reader.ARCHIVE_SHA,
              'archiveSha256': PHASE_SHA, 'archiveBytes': len(result), 'descriptorSha256': XML_SHA,
              'powershellManifestSha256': runtime_sha, 'schemaValidation': validation, 'preservation': proof,
              'prepared': destination is not None, 'persistentFilesWritten': destination is not None,
              'temporaryValidationFilesUsed': True, 'historicalExecutablesRead': False,
              'intermediateCandidateArchiveRead': False, 'nativeBuildRequired': False,
              'applicationExecuted': False, 'installedApplicationModified': False,
              'registryWritten': False, 'deviceAccess': False, 'liveValidatedByThisPreparation': False}
    if destination is not None:
        destination.mkdir()
        with (destination / 'userio_resources.bin').open('xb') as stream:
            stream.write(result)
        with (destination / 'archive-preparation.json').open('x', encoding='utf-8') as stream:
            json.dump(report, stream, sort_keys=True, indent=2)
            stream.write('\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--portable-powershell', type=Path, required=True)
    parser.add_argument('--expected-powershell-manifest-sha256', required=True)
    parser.add_argument('--prepare', type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.app, args.portable_powershell,
                             args.expected_powershell_manifest_sha256, args.prepare), indent=2))
