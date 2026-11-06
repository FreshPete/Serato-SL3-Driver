"""Inspect a local-only Frida build as data; never import/load the candidate."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

PINS = {
    '.': '29016dbd9d8fce836b2b86892b04cc31c2f767aa',
    'releng': '564352a3eac2ca0f5db776b6929955dbb20cf731',
    'subprojects/frida-core': '317363ce8064e3ede421ded3e53e1d3ffcfd782d',
    'subprojects/frida-gum': 'c73c1bbf24ab6bab4e46e11faedd051579e1e942',
    'subprojects/frida-python': '50ad5f65ddcb1270cbc25505f987fac14e763491',
    'subprojects/efni': '329dd8e94505e95e066251e3d4dfe25d0e55eec3',
    'releng/meson': '145667c57ed2649ddcc6fbb11b6008e0d451df1d',
    'releng/tomlkit': '911cccd630965ff423316e25b4685ecf7df0ec0a',
    'subprojects/frida-python/frida-bindgen': 'eace04901ef6300429e8c343095297df042dba0e',
}
WINDOWS_INCLUDES = {
    'gum/backend-windows/gummodule-windows.c': ('#include "gummodule-windows.h"', 'gumprocess.h'),
    'gum/backend-windows/gumprocess-windows.c': ('#include "gumprocess-priv.h"', 'gum-init.h'),
    'gum/backend-dbghelp/gumdbghelpbacktracer.c': ('#include "gum/gumdbghelpbacktracer.h"', 'gum/gumwindows.h'),
}
AGENT_ANCHOR = b'#include "frida-payload.h"\n'
AGENT_DECLARATIONS = (b'\n#ifdef _MSC_VER\nvoid frida_libc_shim_init (void);\n'
                      b'void frida_libc_shim_deinit (void);\n#endif\n')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_configuration(options, targets, ninja):
    values = {x['name']: x['value'] for x in options}
    required = {'frida_python': 'enabled', 'frida-core:local_backend': 'enabled',
                'frida-core:compat': ['disabled'], 'frida-core:tests': 'disabled',
                'frida-gum:tests': 'disabled'}
    required.update({name: 'disabled' for name in
                    ('frida_tools', 'frida_node', 'frida_net', 'frida_swift', 'frida_qml',
                     'server', 'portal', 'gadget', 'inject', 'graft_tool')})
    required.update({'frida-core:' + name + '_backend': 'disabled' for name in
                    ('fruity', 'droidy', 'socket', 'simmy', 'barebone', 'compiler')})
    for name, value in required.items():
        require(values.get(name) == value, 'Unexpected build option: ' + name)
    serialized = json.dumps(targets).lower()
    require('idun' not in serialized and 'idun' not in ninja.lower(), 'Unexpected Idun build dependency')
    require('HAVE_LOCAL_BACKEND' in ninja, 'Local backend compilation flag missing')
    for name in ('FRUITY', 'DROIDY', 'SOCKET', 'SIMMY', 'BAREBONE', 'COMPILER'):
        require('HAVE_' + name + '_BACKEND' not in ninja, 'Unexpected backend compilation flag: ' + name)
    require(any(x.get('name') == '_frida' for x in targets), 'Python binding target missing')
    return required


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_header_change(original, anchor, header):
    anchor = anchor.encode('ascii') + b'\n'
    require(original.count(anchor) == 1, 'Unique upstream include anchor required')
    return original.replace(anchor, anchor + b'\n#include "' + header.encode('ascii') + b'"\n')


def verify_header_change(original, actual, anchor, header):
    require(actual.replace(b'\r\n', b'\n') == expected_header_change(original, anchor, header),
            'Reviewed header-only patch differs')


def verify_agent_change(original, actual):
    require(original.count(AGENT_ANCHOR) == 1 and
            actual.replace(b'\r\n', b'\n') == original.replace(AGENT_ANCHOR, AGENT_ANCHOR + AGENT_DECLARATIONS),
            'Reviewed agent declarations differ')


def inspect(source, build, configuration_only=False, allow_reviewed_windows_includes=False):
    source, build = source.resolve(), build.resolve()
    git = lambda directory, *args: subprocess.check_output(
        ['git', '-C', str(directory), *args], text=True, timeout=30).strip()
    header_changes = []
    declaration_changes = []
    for relative, expected in PINS.items():
        directory = source / relative
        require(git(directory, 'rev-parse', 'HEAD') == expected, 'Source commit differs: ' + relative)
        status = git(directory, 'status', '--porcelain', '--untracked-files=no', '--ignore-submodules=untracked')
        if status and allow_reviewed_windows_includes and relative == '.':
            require({line.strip() for line in status.splitlines()} <=
                    {'M subprojects/frida-gum', 'M subprojects/frida-core'}, 'Unexpected modified submodule')
        elif status and allow_reviewed_windows_includes and relative == 'subprojects/frida-core':
            name = 'lib/agent/agent-glue.c'
            require(status.strip() == 'M ' + name, 'Only the reviewed agent declarations are permitted')
            original = subprocess.check_output(['git', '-C', str(directory), 'show', 'HEAD:' + name], timeout=30)
            actual = (directory / name).read_bytes().replace(b'\r\n', b'\n')
            verify_agent_change(original, actual)
            declaration_changes.append({'path': name, 'originalSha256': hashlib.sha256(original).hexdigest(),
                                        'normalizedPatchedSha256': hashlib.sha256(actual).hexdigest()})
        elif status and allow_reviewed_windows_includes and relative == 'subprojects/frida-gum':
            require({line.strip() for line in status.splitlines()} == {'M ' + name for name in WINDOWS_INCLUDES},
                    'Only the reviewed Windows include changes are permitted')
            for name, (anchor, header) in WINDOWS_INCLUDES.items():
                original = subprocess.check_output(['git', '-C', str(directory), 'show', 'HEAD:' + name], timeout=30)
                actual = (directory / name).read_bytes()
                verify_header_change(original, actual, anchor, header)
                header_changes.append({'path': name, 'includeAdded': header,
                                       'originalSha256': hashlib.sha256(original).hexdigest(),
                                       'normalizedPatchedSha256': hashlib.sha256(actual.replace(b'\r\n', b'\n')).hexdigest()})
        else:
            require(not status, 'Tracked source changes present: ' + relative)
    options = build / 'meson-info/intro-buildoptions.json'
    targets = build / 'meson-info/intro-targets.json'
    ninja = build / 'build.ninja'
    configuration = check_configuration(json.loads(options.read_text()), json.loads(targets.read_text()),
                                        ninja.read_text())
    result = {'schema': 'sl3.frida-local-build-inspection.v1', 'sourceCommits': PINS,
              'requiredOptions': configuration, 'targetCount': len(json.loads(targets.read_text())),
              'buildMetadataSha256': {p.name: digest(p) for p in (options, targets, ninja)},
              'configurationOnly': configuration_only, 'candidateInspected': False,
              'reviewedWindowsIncludeChangesAllowed': allow_reviewed_windows_includes,
              'sourceHeaderChanges': header_changes,
              'sourceDeclarationChanges': declaration_changes,
              'candidateImported': False, 'candidateExecuted': False, 'seratoStarted': False,
              'deviceOpened': False, 'securityHoldCleared': False,
              'runtimeCompatibilityVerified': False, 'antivirusCompatibilityVerified': False,
              'embeddedAssetContentsAttested': False}
    if configuration_only:
        return result
    candidate = build / 'subprojects/frida-python/frida/_frida.pyd'
    require(candidate.is_file(), 'Candidate Python binding has not been built')
    require(0 < candidate.stat().st_size <= 256 * 1024 * 1024, 'Candidate image size outside inspection bounds')
    import pefile
    with pefile.PE(data=candidate.read_bytes()) as pe:
        require(pe.FILE_HEADER.Machine == 0x8664 and pe.OPTIONAL_HEADER.Magic == 0x20b,
                'Native AMD64 PE32+ image required')
        exports = sorted(x.name.decode('ascii') for x in pe.DIRECTORY_ENTRY_EXPORT.symbols if x.name)
        require('PyInit__frida' in exports, 'Python extension entry export missing')
        imports = sorted({x.dll.decode('ascii').lower() for attribute in
                          ('DIRECTORY_ENTRY_IMPORT', 'DIRECTORY_ENTRY_DELAY_IMPORT')
                          for x in getattr(pe, attribute, [])})
        require('python3.dll' in imports and not any(x.startswith('python3') and x != 'python3.dll' for x in imports),
                'Stable Python ABI dependency required')
    return {**result, 'candidateInspected': True, 'candidateSha256': digest(candidate),
            'candidateBytes': candidate.stat().st_size, 'candidateImports': imports, 'candidateExports': exports}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--configuration-only', action='store_true')
    parser.add_argument('--allow-reviewed-windows-includes', action='store_true',
                        help='Allow only the exact include additions and agent declarations encoded in this inspector')
    args = parser.parse_args()
    print(json.dumps(inspect(args.source, args.build, args.configuration_only,
                             args.allow_reviewed_windows_includes), indent=2))
