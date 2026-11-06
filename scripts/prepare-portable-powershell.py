"""Stage and verify a reviewed Windows x64 PowerShell ZIP; never execute it."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MAX_ARCHIVE = 160 * 1024 * 1024
MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 384 * 1024 * 1024
MAX_ENTRIES = 2048
REQUIRED = {'pwsh.exe', 'pwsh.dll', 'pwsh.runtimeconfig.json', 'coreclr.dll',
            'System.Management.Automation.dll', 'LICENSE.txt', 'ThirdPartyNotices.txt'}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def member_name(name):
    parts = PurePosixPath(name).parts
    require(name and '\\' not in name and not name.startswith('/') and
            all(part and part not in ('.', '..') for part in name.split('/')) and
            all(not any(ord(char) < 32 or char in ':<>"|?*' for char in part) and
                not part.endswith((' ', '.')) and
                not re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part)
                for part in parts), 'Unsafe Windows runtime member path')
    return parts


def inventory(archive):
    rows = archive.infolist()
    require(1 <= len(rows) <= MAX_ENTRIES and
            sum(row.file_size for row in rows) <= MAX_TOTAL, 'Runtime ZIP exceeds inventory bounds')
    seen = set()
    files = {}
    directories = set()
    for row in rows:
        name = row.filename[:-1] if row.is_dir() else row.filename
        parts = member_name(name)
        key = name.casefold()
        mode = row.external_attr >> 16
        require(key not in seen and not row.flag_bits & 1 and
                stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR) and
                not row.external_attr & 0x400, 'ZIP aliases, links or special entries refused')
        require(0 <= row.file_size <= MAX_FILE, 'Runtime member exceeds bound')
        seen.add(key)
        directories.update('/'.join(parts[:index]).casefold() for index in range(1, len(parts)))
        if row.is_dir():
            require(row.file_size == 0, 'Directory entry has content')
            directories.add(key)
        else:
            files[name] = row
    require(not directories.intersection(name.casefold() for name in files), 'File/directory alias refused')
    require(REQUIRED <= files.keys() and 'runtime-manifest.json' not in seen,
            'Expected complete PowerShell runtime and notices')
    return files


def regular(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
            'Regular non-reparse runtime file required')
    return info


def prepare(archive, expected, output=None):
    require(re.fullmatch('[0-9a-f]{64}', expected), 'Expected lowercase archive SHA-256')
    archive = Path(archive)
    require(regular(archive).st_size <= MAX_ARCHIVE and sha(archive) == expected,
            'Reviewed PowerShell archive hash/size differs')
    with zipfile.ZipFile(archive) as package:
        files = inventory(package)
        summary = {'filesVerified': len(files), 'expandedBytes': sum(row.file_size for row in files.values()),
                   'runtimeExecuted': False, 'systemPowerShellModified': False}
        if output is None:
            return {**summary, 'planOnly': True, 'filesWritten': False}
        output = Path(output).absolute()
        require(output.parent.resolve() == (ROOT / 'artifacts/build').resolve() and
                output.name.startswith('portable-powershell-') and not output.exists(),
                'Fresh artifacts/build/portable-powershell-* directory required')
        output.mkdir()
        records = {}
        for name, row in sorted(files.items()):
            target = output.joinpath(*member_name(name))
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            count = 0
            with package.open(row) as source, target.open('xb') as destination:
                while data := source.read(1024 * 1024):
                    count += len(data)
                    require(count <= row.file_size, 'ZIP member exceeded declared size')
                    destination.write(data)
                    digest.update(data)
            require(count == row.file_size, 'ZIP member size differs')
            records[name] = {'bytes': count, 'sha256': digest.hexdigest()}
        manifest = {'schema': 'sl3.portable-powershell.v1', 'archiveSha256': expected,
                    'files': records, 'systemPowerShellModified': False, 'liveSeratoValidated': False}
        with (output / 'runtime-manifest.json').open('x', encoding='utf-8') as stream:
            json.dump(manifest, stream, sort_keys=True, indent=2)
            stream.write('\n')
    return {**summary, 'prepared': True, 'directory': str(output),
            'runtimeManifestSha256': sha(output / 'runtime-manifest.json')}


def verify(directory, expected):
    directory = Path(directory).absolute()
    require(re.fullmatch('[0-9a-f]{64}', expected), 'Expected lowercase runtime manifest SHA-256')
    require(directory.is_dir() and not directory.is_symlink() and
            not getattr(directory.lstat(), 'st_file_attributes', 0) & 0x400, 'Ordinary runtime directory required')
    path = directory / 'runtime-manifest.json'
    require(regular(path).st_size <= 1024 * 1024 and sha(path) == expected, 'Runtime manifest differs')
    manifest = json.loads(path.read_bytes())
    files = manifest['files']
    require(manifest['schema'] == 'sl3.portable-powershell.v1' and
            1 <= len(files) <= MAX_ENTRIES and REQUIRED <= files.keys() and
            sum(row['bytes'] for row in files.values()) <= MAX_TOTAL, 'Unsupported runtime inventory')
    require(len({name.casefold() for name in files}) == len(files), 'Runtime path aliases refused')
    for name, details in files.items():
        target = directory.joinpath(*member_name(name))
        require(target.resolve().is_relative_to(directory.resolve()), 'Runtime member escaped its directory')
        info = regular(target)
        require(0 <= info.st_size <= MAX_FILE and info.st_size == details['bytes'] and
                sha(target) == details['sha256'], 'Runtime member differs: ' + name)
    actual = set()
    for target in directory.rglob('*'):
        require(not getattr(target.lstat(), 'st_file_attributes', 0) & 0x400 and not target.is_symlink(),
                'Runtime reparse points refused')
        if target.is_file():
            regular(target)
            actual.add(target.relative_to(directory).as_posix())
    require(actual == set(files) | {'runtime-manifest.json'}, 'Unexpected runtime files')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--archive', type=Path)
    action.add_argument('--verify', type=Path)
    parser.add_argument('--expected-archive-sha256')
    parser.add_argument('--prepare', type=Path)
    parser.add_argument('--expected-runtime-manifest-sha256')
    args = parser.parse_args()
    if args.verify:
        require(not args.prepare, 'Preparation and verification are separate actions')
        manifest = verify(args.verify, args.expected_runtime_manifest_sha256 or '')
        result = {'runtimeVerified': True, 'filesVerified': len(manifest['files']), 'runtimeExecuted': False}
    else:
        result = prepare(args.archive, args.expected_archive_sha256 or '', args.prepare)
    print(json.dumps(result, indent=2))
