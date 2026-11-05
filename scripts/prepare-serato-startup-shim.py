"""Prepare the startup-only shim offline. Never launches, attaches or installs."""
import argparse
import ast
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re

import pefile

ROOT = Path(__file__).resolve().parents[1]
APP_SHA = '66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265'
TEMPLATE = ROOT / 'scripts/serato-sl3-startup-shim.js'


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def points(source):
    match = re.search(r'const points = (\[[\s\S]*?\n  \]);', source)
    require(match, 'Missing literal startup entry guards')
    result = ast.literal_eval(match.group(1))
    require([(p[0], p[1]) for p in result] == [('arrival', 0x185ee90), ('click', 0x185ec00), ('panel', 0x5b0cb0)],
            'Unexpected startup guard inventory')
    require(all(isinstance(p[2], str) and re.fullmatch('[0-9a-f]{16}', p[2]) for p in result), 'Invalid entry bytes')
    return result


def asio_path(value):
    path = PureWindowsPath(value)
    require(path.is_absolute() and re.fullmatch('[a-zA-Z]:', path.drive) and
            path.name.lower() == 'sl3_asio.dll' and '..' not in path.parts and
            not any(char in str(path)[2:] for char in ':<>"|?*\r\n\x00'), 'Expected absolute local SL3 ASIO DLL path')
    return str(path)


def output_path(path):
    path = Path(path)
    require(path.parent.resolve() == (ROOT / 'analysis').resolve() and path.name.startswith('sl3-startup-shim-')
            and not path.exists() and not path.is_symlink(), 'Fresh analysis/sl3-startup-shim-* directory required')
    return path


def prepare(application, planned_asio, output=None):
    target = asio_path(planned_asio)
    destination = output_path(output) if output is not None else None
    application = Path(application)
    require(application.stat().st_size <= 512 * 1024 * 1024, 'Application exceeds inspection bound')
    data = application.read_bytes()
    require(digest(data) == APP_SHA, 'Application differs from reviewed Serato 5.0.0.1278')
    source = TEMPLATE.read_bytes()
    entry_points = points(source.decode('utf-8'))
    pe = pefile.PE(data=data, fast_load=True)
    try:
        require(pe.FILE_HEADER.Machine == 0x8664 and pe.OPTIONAL_HEADER.Magic == 0x20b, 'Windows x64 application required')
        for name, rva, expected in entry_points:
            require(pe.get_data(rva, 8) == bytes.fromhex(expected), 'Application entry differs: ' + name)
    finally:
        pe.close()
    script = ('globalThis.SL3_SESSION_CONFIG = Object.freeze(' + json.dumps({'asioPath': target}) + ');\n').encode() + source
    result = {'schema': 'sl3.startup-shim-preparation.v1', 'applicationSha256': APP_SHA,
              'templateSha256': digest(source), 'preparedScriptSha256': digest(script), 'plannedAsioPath': target,
              'guardedEntries': [{'name': name, 'rva': rva, 'bytesChecked': 8} for name, rva, _ in entry_points],
              'hostMustReverifyApplicationAndAsio': True, 'hostMustUnloadAndDetachAfterStart': True,
              'prepared': destination is not None, 'applicationLaunched': False, 'processAttached': False,
              'registryWritten': False, 'deviceAccess': False, 'liveShimValidated': False}
    if destination is not None:
        destination.mkdir()
        with (destination / 'startup-shim.js').open('xb') as stream:
            stream.write(script)
        with (destination / 'preparation.json').open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--asio-path', required=True)
    parser.add_argument('--prepare', type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.app, args.asio_path, args.prepare), indent=2))
