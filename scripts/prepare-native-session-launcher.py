"""Prepare a reusable native launcher project with no .NET runtime dependency."""
import argparse
import json
from pathlib import Path
import runpy
import sys

ROOT=Path(__file__).resolve().parents[1]
SOURCE='src/installer/NativeSessionLauncher.cpp'
TEST='tests/native/launcher_argument_tests.cpp'
BUILDER='scripts/prepare-native-session-launcher.py'


def prepare(runtime,runtime_sha,output=None,powershell=None,powershell_sha=None):
    api=runpy.run_path(str(ROOT/'scripts/serato-session-capsule.py'))
    runtime=Path(runtime).absolute()
    api['require'](Path(sys.executable).absolute()==runtime/'python.exe','Run under selected private runtime')
    verified=runpy.run_path(str(ROOT/'scripts/prepare-embedded-python.py'))['verify'](runtime,runtime_sha)
    pins={**api['source_hashes'](),SOURCE:api['sha'](ROOT/SOURCE),BUILDER:api['sha'](ROOT/BUILDER),
          'scripts/prepare-embedded-python.py':api['sha'](ROOT/'scripts/prepare-embedded-python.py')}
    powershell_pins={}
    if powershell is not None:
        powershell=Path(powershell).absolute()
        ps_api=runpy.run_path(str(ROOT/'scripts/prepare-portable-powershell.py'))
        ps_manifest=ps_api['verify'](powershell,powershell_sha or '')
        powershell_pins={name:details['sha256'] for name,details in ps_manifest['files'].items()}
        powershell_pins['runtime-manifest.json']=powershell_sha
        session_api=runpy.run_path(str(ROOT/'scripts/prepare-serato-session-plan.py'))
        pins.update({name:api['sha'](ROOT/name) for name in session_api['EXTRA_SOURCES']})
        pins['scripts/prepare-portable-powershell.py']=api['sha'](ROOT/'scripts/prepare-portable-powershell.py')
        pins['scripts/prepare-fresh-serato-session.py']=api['sha'](ROOT/'scripts/prepare-fresh-serato-session.py')
        archive_api=runpy.run_path(str(ROOT/'scripts/prepare-serato-installed-phase-archive.py'))
        kit_sources=(*archive_api['SOURCES'],'scripts/prepare-portable-serato-kit.py',
                     'scripts/assemble-portable-serato-kit.py','scripts/rebind-asio-deployment.py','LICENSE')
        pins.update({name:api['sha'](ROOT/name) for name in kit_sources})
    runtime_pins={name:details['sha256'] for name,details in verified['files'].items()}
    runtime_pins['runtime-manifest.json']=runtime_sha
    python_sha=api['sha'](Path(sys.executable))
    record={'schema':'sl3.native-launcher-release.v1','sourcePins':pins,'runtimePins':runtime_pins,
            'pythonSha256':python_sha,'applicationSha256':api['APP_SHA'],'sessionBoundAtBuildTime':False,
            'powershellPins':powershell_pins,'sessionWrapperSupported':bool(powershell_pins),
            'dotNetRuntimeRequired':False,'staticMsvcRuntimeRequested':True,'liveValidated':False}
    def rows(values):return ',\n'.join('    { L'+json.dumps(name)+', L'+json.dumps(identity)+' }' for name,identity in sorted(values.items()))
    config=('#pragma once\n#include <string>\n#include <utility>\n#include <vector>\nnamespace sl3::launcher::release {\n'
            'inline const std::wstring python_sha=L'+json.dumps(python_sha)+';\n'
            'inline const std::wstring application_sha=L'+json.dumps(api['APP_SHA'])+';\n'
            'inline const std::vector<std::pair<std::wstring,std::wstring>> source_pins={\n'+rows(pins)+'\n};\n'
            'inline const std::vector<std::pair<std::wstring,std::wstring>> runtime_pins={\n'+rows(runtime_pins)+'\n};\n'
            'inline const std::vector<std::pair<std::wstring,std::wstring>> powershell_pins={\n'+rows(powershell_pins)+'\n};\n}\n')
    if output is None:return {**record,'planOnly':True,'filesWritten':False}
    output=Path(output).absolute()
    api['require'](output.parent.resolve()==(ROOT/'artifacts/build').resolve() and output.name.startswith('native-session-launcher-') and
                   not output.exists(),'Fresh artifacts/build/native-session-launcher-* directory required')
    cmake=('cmake_minimum_required(VERSION 3.20)\nproject(sl3_native_launcher LANGUAGES CXX)\n'
           'if(NOT WIN32 OR NOT MSVC)\n message(FATAL_ERROR "Windows MSVC required")\nendif()\n'
           'set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")\n'
           'add_executable(SL3_Rebuild_Development_x64 "'+(ROOT/SOURCE).as_posix()+'")\n'
           'add_executable(sl3_launcher_argument_tests "'+(ROOT/TEST).as_posix()+'")\n'
           'foreach(target SL3_Rebuild_Development_x64 sl3_launcher_argument_tests)\n'
           ' target_compile_features(${target} PRIVATE cxx_std_17)\n'
           ' target_compile_definitions(${target} PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX)\n'
           ' target_compile_options(${target} PRIVATE /W4 /WX /permissive- /EHsc /utf-8)\n'
           ' target_include_directories(${target} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")\n'
           ' target_link_libraries(${target} PRIVATE windowsapp shell32 bcrypt)\nendforeach()\n')
    output.mkdir()
    for name,data in (('launcher_config.hpp',config),('CMakeLists.txt',cmake),('release.json',json.dumps(record,sort_keys=True,indent=2)+'\n')):
        with (output/name).open('x',encoding='utf-8',newline='\n') as stream:stream.write(data)
    return {'prepared':True,'directory':str(output),'sourceCount':len(pins),'runtimeFilesPinned':len(runtime_pins),
            'powershellFilesPinned':len(powershell_pins),'dotNetRuntimeRequired':False,'deviceAccess':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--embedded-runtime',type=Path,required=True)
    parser.add_argument('--expected-runtime-manifest-sha256',required=True)
    parser.add_argument('--prepare',type=Path)
    parser.add_argument('--portable-powershell',type=Path)
    parser.add_argument('--expected-powershell-manifest-sha256')
    args=parser.parse_args()
    api=runpy.run_path(str(ROOT/'scripts/serato-session-capsule.py'))
    api['require'](bool(args.portable_powershell)==bool(args.expected_powershell_manifest_sha256),
                   'Complete portable PowerShell binding required')
    print(json.dumps(prepare(args.embedded_runtime,args.expected_runtime_manifest_sha256,args.prepare,
                             args.portable_powershell,args.expected_powershell_manifest_sha256),indent=2))
