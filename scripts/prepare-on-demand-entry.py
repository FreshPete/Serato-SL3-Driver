"""Prepare a native verifier for one exact setup-only kit; no installer or device operation."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(v,t):
    if not v:raise ValueError(t)


def prepare(kit,expected,output):
    kit=Path(kit).absolute();manifest=kit/'kit-manifest.json';require(sha(manifest)==expected,'Reviewed kit manifest required')
    meta=json.loads(manifest.read_bytes());inventory=kit/'kit-inventory.json';require(sha(inventory)==meta['inventorySha256'],'Reviewed kit inventory required')
    files=json.loads(inventory.read_bytes())['files'];require(all(sha(kit/n)==x['sha256'] for n,x in files.items()),'Reviewed kit input changed')
    # The selected helper is executed only after its declared bytes have matched
    # the externally reviewed manifest/inventory above.
    runpy.run_path(str(kit/'scripts/prepare-on-demand-kit.py'))['verify'](manifest,expected)
    files={**files,'kit-manifest.json':{'sha256':expected,'bytes':manifest.stat().st_size},
        'kit-inventory.json':{'sha256':meta['inventorySha256'],'bytes':inventory.stat().st_size}}
    source_names=['src/installer/OnDemandKitEntry.cpp','src/installer/NativeSessionLauncher.cpp','scripts/prepare-on-demand-entry.py','scripts/build-on-demand-entry.ps1',
        'src/installer/SetupResultPipe.hpp','tests/native/setup_result_pipe_tests.cpp']
    pins={n:sha(ROOT/n) for n in source_names}
    header=('#pragma once\n#include <string>\n#include <vector>\n#include <utility>\nnamespace sl3::launcher::release {\n'
        'inline const std::wstring python_sha=L'+json.dumps(meta['pythonExecutableSha256'])+';\n'
        'inline const std::wstring application_sha=L"66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265";\n'
        'inline const std::vector<std::pair<std::wstring,std::wstring>> source_pins={},runtime_pins={},powershell_pins={};\n}\n')
    setup=('#pragma once\nnamespace sl3::setup::release {\nstruct File {std::wstring name,sha;unsigned long long bytes;};\n'
        'inline const std::wstring kit_manifest_sha=L'+json.dumps(expected)+';\ninline const std::wstring application_sha=sl3::launcher::release::application_sha;\n'
        'inline const std::wstring python_manifest_sha=L'+json.dumps(meta['pythonManifestSha256'])+';\n'
        'inline const std::wstring powershell_manifest_sha=L'+json.dumps(meta['powershellManifestSha256'])+';\n'
        'inline const std::vector<File> files={\n'+',\n'.join(' {L'+json.dumps(n)+',L'+json.dumps(x['sha256'])+','+str(x['bytes'])+'ull}' for n,x in sorted(files.items()))+'\n};\n}\n')
    cmake=('cmake_minimum_required(VERSION 3.20)\nproject(sl3_setup_entry LANGUAGES CXX)\n'
        'if(NOT WIN32 OR NOT MSVC OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8)\nmessage(FATAL_ERROR "Windows x64 MSVC required")\nendif()\n'
        'set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")\n'
        'add_executable(SL3_Setup_Engineering "'+(ROOT/source_names[0]).as_posix()+'")\n'
        'target_compile_features(SL3_Setup_Engineering PRIVATE cxx_std_17)\n'
        'target_compile_definitions(SL3_Setup_Engineering PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX)\n'
        'target_compile_options(SL3_Setup_Engineering PRIVATE /W4 /WX /permissive- /EHsc /utf-8)\n'
        'target_include_directories(SL3_Setup_Engineering PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")\n'
        'target_link_libraries(SL3_Setup_Engineering PRIVATE windowsapp shell32 bcrypt advapi32)\n'
        'add_executable(sl3_setup_result_pipe_tests "'+(ROOT/'tests/native/setup_result_pipe_tests.cpp').as_posix()+'")\n'
        'target_compile_features(sl3_setup_result_pipe_tests PRIVATE cxx_std_17)\n'
        'target_compile_definitions(sl3_setup_result_pipe_tests PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX)\n'
        'target_compile_options(sl3_setup_result_pipe_tests PRIVATE /W4 /WX /permissive- /EHsc /utf-8)\n'
        'target_include_directories(sl3_setup_result_pipe_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")\n'
        'target_link_libraries(sl3_setup_result_pipe_tests PRIVATE windowsapp shell32 bcrypt advapi32)\n'
        'enable_testing()\nadd_test(NAME setup_help COMMAND SL3_Setup_Engineering --help)\n'
        'add_test(NAME setup_unknown COMMAND SL3_Setup_Engineering --install)\nset_tests_properties(setup_unknown PROPERTIES WILL_FAIL TRUE)\n')
    cmake+='add_test(NAME setup_result_pipe_contract COMMAND sl3_setup_result_pipe_tests)\nset_tests_properties(setup_result_pipe_contract PROPERTIES TIMEOUT 30)\n'
    output=Path(output).absolute();require(output.parent.resolve()==(ROOT/'artifacts/build').resolve() and output.name.startswith('native-on-demand-entry-') and not output.exists(),'Fresh native entry build output required');output.mkdir()
    values={'launcher_config.hpp':header,'setup_config.hpp':setup,'CMakeLists.txt':cmake}
    for name,text in values.items():(output/name).write_text(text,encoding='utf-8')
    record={'schema':'sl3.native-setup-entry-source.v1','kitManifestSha256':expected,'sourcePins':pins,
        'generatedPins':{n:sha(output/n) for n in values},'compiledPayloadFiles':len(files),'mutableActionsExposed':True,'mutableActionsRequireAlreadyElevatedProcess':True,
        'elevationRequested':False,'seratoLaunched':False,'nativeDeviceAccess':False}
    (output/'entry-source.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8');return {'prepared':True,'directory':str(output),'sourceManifestSha256':sha(output/'entry-source.json')}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kit',type=Path,required=True);p.add_argument('--expected-kit-manifest-sha256',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(prepare(a.kit,a.expected_kit_manifest_sha256,a.output),indent=2))
