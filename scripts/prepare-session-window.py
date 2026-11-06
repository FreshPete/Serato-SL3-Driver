"""Prepare a host-bound Windows GUI build around an existing verified session."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expected_cli_header(record):
    def rows(values):
        return ',\n'.join('    { L' + json.dumps(name) + ', L' + json.dumps(identity) + ' }'
                          for name, identity in sorted(values.items()))
    return ('#pragma once\n#include <string>\n#include <utility>\n#include <vector>\nnamespace sl3::launcher::release {\n'
            'inline const std::wstring python_sha=L' + json.dumps(record['pythonSha256']) + ';\n'
            'inline const std::wstring application_sha=L' + json.dumps(record['applicationSha256']) + ';\n'
            'inline const std::vector<std::pair<std::wstring,std::wstring>> source_pins={\n' + rows(record['sourcePins']) + '\n};\n'
            'inline const std::vector<std::pair<std::wstring,std::wstring>> runtime_pins={\n' + rows(record['runtimePins']) + '\n};\n'
            'inline const std::vector<std::pair<std::wstring,std::wstring>> powershell_pins={\n' + rows(record['powershellPins']) + '\n};\n}\n')


def prepare(plan, identity, powershell, release, release_identity, kit, kit_identity, output):
    api = runpy.run_path(str(ROOT / 'scripts/prepare-serato-session-plan.py'))
    require = api['require']
    plan = Path(plan).absolute()
    saved = api['verify'](plan, identity)
    release = Path(release).absolute()
    require(sha(release) == release_identity, 'Reviewed CLI release record required')
    record = json.loads(release.read_bytes())
    require(record['schema'] == 'sl3.native-launcher-release.v1' and record['sessionWrapperSupported'] is True,
            'Complete native session CLI required')
    for name, expected in record['sourcePins'].items():
        require(sha(ROOT / name) == expected, 'CLI source differs: ' + name)
    kit = Path(kit).absolute()
    kit_record = runpy.run_path(str(ROOT / 'scripts/prepare-portable-serato-kit.py'))['verify'](kit, kit_identity)
    require(kit_record['launcherSha256'] == saved['launcher']['sha256'], 'Kit and session CLI differ')
    powershell = Path(powershell).absolute()
    ps_identity = record['powershellPins']['runtime-manifest.json']
    runpy.run_path(str(ROOT / 'scripts/prepare-portable-powershell.py'))['verify'](powershell, ps_identity)
    require(record['sourcePins']['src/installer/NativeSessionLauncher.cpp'] == sha(ROOT / 'src/installer/NativeSessionLauncher.cpp'),
            'GUI shared verifier source differs')
    header = release.parent / 'launcher_config.hpp'
    expected_header = expected_cli_header(record)
    require(header.is_file() and header.read_bytes() == expected_header.encode('utf-8'),
            'CLI generated verification header differs from its reviewed release')
    output = Path(output).absolute()
    require(output.parent.resolve() == (ROOT / 'artifacts/build').resolve() and
            output.name.startswith('session-window-') and not output.exists(), 'Fresh session-window build directory required')
    values = {'launcher': saved['launcher']['path'], 'launcher_sha': saved['launcher']['sha256'],
              'plan': str(plan), 'plan_sha': identity, 'powershell': str(powershell), 'kit': str(kit),
              'kit_sha': kit_identity, 'application': saved['application']['path']}
    def literal(value):
        return 'L' + json.dumps(value, ensure_ascii=True)
    configuration = '#pragma once\nnamespace session_window_config {\n' + ''.join(
        'inline constexpr const wchar_t* ' + key + '=' + literal(value) + ';\n' for key, value in values.items()) + '}\n'
    cmake = ('cmake_minimum_required(VERSION 3.20)\nproject(sl3_session_window LANGUAGES CXX)\n'
             'if(NOT WIN32 OR NOT MSVC)\n message(FATAL_ERROR "Windows MSVC required")\nendif()\n'
             'set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")\n'
             'add_executable(SL3_Session WIN32 "' + (ROOT / 'src/installer/SessionWindow.cpp').as_posix() + '")\n'
             'add_executable(sl3_session_window_tests "' + (ROOT / 'tests/native/session_window_tests.cpp').as_posix() + '")\n'
             'foreach(target SL3_Session sl3_session_window_tests)\n'
             ' target_compile_features(${target} PRIVATE cxx_std_17)\n'
             ' target_compile_definitions(${target} PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX)\n'
             ' target_compile_options(${target} PRIVATE /W4 /WX /permissive- /EHsc /utf-8)\n'
             ' target_include_directories(${target} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")\n'
             ' target_link_libraries(${target} PRIVATE windowsapp shell32 bcrypt user32 gdi32)\nendforeach()\n')
    receipt = {'schema': 'sl3.session-window-preparation.v1', 'sessionPlanSha256': identity,
               'kitManifestSha256': kit_identity, 'cliReleaseSha256': release_identity,
               'cliHeaderSha256': sha(header), 'launcherSha256': values['launcher_sha'],
               'sources': {name: sha(ROOT / name) for name in ('src/installer/SessionWindow.cpp',
                           'src/installer/NativeSessionLauncher.cpp', 'scripts/prepare-session-window.py',
                           'tests/native/session_window_tests.cpp')},
               'applicationStarted': False, 'deviceAccess': False, 'liveValidated': False,
               'scope': 'One host-bound prepared session; not a distributable installer'}
    output.mkdir()
    for name, value in (('session_window_config.hpp', configuration), ('launcher_config.hpp', expected_header), ('CMakeLists.txt', cmake),
                        ('preparation.json', json.dumps(receipt, indent=2) + '\n')):
        with (output / name).open('x', encoding='utf-8') as stream:
            stream.write(value)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('session-plan', 'powershell-directory', 'cli-release', 'kit-manifest', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('expected-session-plan-sha256', 'expected-cli-release-sha256', 'expected-kit-manifest-sha256'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.session_plan, args.expected_session_plan_sha256, args.powershell_directory,
                            args.cli_release, args.expected_cli_release_sha256, args.kit_manifest,
                            args.expected_kit_manifest_sha256, args.output), indent=2))
