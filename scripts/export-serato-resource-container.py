"""Export verified container metadata and bounded static source bindings."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT/relative)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    reader = module('resource_reader', 'scripts/inspect-serato-resource-archive.py')
    h = module('sl3_image', 'scripts/export-serato-clock-handshake-evidence.py')
    report = reader.inspect()
    app = h.Image(reader.APP_RELATIVE, reader.APP_SHA)
    installed = Path('C:/Program Files/Serato/Serato DJ Pro')
    reader.require(hashlib.sha256((installed/'Serato DJ Pro.exe').read_bytes()).hexdigest() == reader.APP_SHA, 'Installed executable differs')
    reader.require(hashlib.sha256((installed/'userio_resources.bin').read_bytes()).hexdigest() == reader.ARCHIVE_SHA, 'Installed archive differs')
    reader.require(report['memberCount'] == 229 and report['xmlMembersParsed'] == 228 and report['schemaMembersNotParsed'] == 1,
                   'Unexpected container coverage')
    reader.require(not report['sl3IdentityMatchesInRecognizedNodes'] and not report['sl3NamedMembers'], 'SL3 absence finding changed')
    reports = {}
    for name in ('serato500-archive-setup-01.json', 'serato500-container-index-01.json', 'serato500-container-load-01.json',
                 'serato500-archive-codec-01.json', 'serato500-resource-transform-01.json'):
        path = ROOT/'analysis'/name
        decoded = json.loads(path.read_text(encoding='utf-8-sig'))
        reader.require(decoded['binary_sha256'] == app.sha, 'Focused image mismatch')
        for function in decoded['functions']:
            reader.require(function['complete'] and (int(function['start'], 16), int(function['end_exclusive'], 16)) in app.spans,
                           'Incomplete focused function')
        reports[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    members = report.pop('members')
    report.update({'installedExecutableAndArchiveMatch': True, 'focusedReports': reports,
                   'memberMetadataSha256': hashlib.sha256(json.dumps(members, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                   'readerSourceSha256': hashlib.sha256((ROOT/'scripts/inspect-serato-resource-archive.py').read_bytes()).hexdigest(),
                   'staticBoundary': {'keySetup': '14139c650', 'keyToBytes': '141772250', 'containerIndex': '1417740d0',
                                      'readMember': '141775520', 'decodeWrapper': '1417723b0', 'wordTransform': '141cc5ed0',
                                      'paddingCheck': '141cc6250', 'innerZipReader': '141cbca70'}})
    output = ROOT/'docs/evidence/serato500-resource-container.json'
    output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(output)


if __name__ == '__main__':
    main()
