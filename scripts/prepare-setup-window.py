"""Bind a one-time setup window to a reviewed native entry and prepared experiment."""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import runpy

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(v,t):
    if not v:raise ValueError(t)


def prepare(build_path,expected,kit,experiment,experiment_sha,output,watcher_dll=None):
    build_path,kit,output=(Path(p).absolute() for p in (build_path,kit,output))
    require((experiment is None)==(experiment_sha is None),'Supply both experiment and hash for a prebound window')
    require(sha(build_path)==expected,'Reviewed native entry build required');build=json.loads(build_path.read_bytes())
    require(build['schema']=='sl3.native-setup-entry-build.v1' and build['configuration']=='Release' and build['inertChecksPassed'],'Successful native entry Release build required')
    source_path=build_path.parent/'entry-source.json';require(sha(source_path)==build['sourceManifestSha256'],'Native entry source binding differs');source=json.loads(source_path.read_bytes())
    require(source['mutableActionsRequireAlreadyElevatedProcess'] and 'src/installer/SetupResultPipe.hpp' in source['sourcePins'] and all(sha(ROOT/n)==v for n,v in source['sourcePins'].items()),'Current result-channel native entry source required')
    require(all(sha(source_path.parent/n)==v for n,v in source['generatedPins'].items()),'Generated native entry source changed')
    entry=build_path.parent/'build/Release/SL3_Setup_Engineering.exe';require(sha(entry)==build['executableSha256'],'Native entry image changed')
    native_watcher=source.get('nativeWatcherPayload') is True
    require(not native_watcher or (experiment is None and watcher_dll is None),'Driver-only watcher setup requires a portable window')
    manifest_name='watcher-payload.json' if native_watcher else 'kit-manifest.json'
    require(sha(kit/manifest_name)==source['kitManifestSha256'],'Selected native entry kit differs')
    watcher_profile = json.loads((kit/manifest_name).read_bytes()) if native_watcher else {}
    application_lifetime = watcher_profile.get('applicationLifetime') is True
    buffer_frames = watcher_profile.get('diagnosticBufferFrames')
    application=''
    if experiment is not None:
        experiment=Path(experiment).absolute()
        api=runpy.run_path(str(kit/'scripts/serato-on-demand-test.py'))
        with ExitStack() as held:record=api['verify'](experiment,experiment_sha,held)
        require(record['projectRoot']==str(kit),'Prepared experiment belongs to another kit')
        application=record['application']
    pins={n:sha(ROOT/n) for n in ['src/installer/SetupWindow.cpp','src/installer/SessionWindow.cpp','src/installer/NativeSessionLauncher.cpp',
        'tests/native/setup_window_tests.cpp','scripts/prepare-setup-window.py','scripts/build-setup-window.ps1','src/installer/SetupResultPipe.hpp',
        'src/installer/SetupUsbPrerequisite.hpp','src/installer/SetupWindow.rc','src/installer/SetupWindow.ico']}
    values={'launcher':str(entry) if experiment else '', 'launcher_sha':build['executableSha256'],
        'plan':str(experiment) if experiment else '', 'plan_sha':experiment_sha or '', 'kit_root':str(kit) if experiment else '',
        'kit':str(kit/'kit-manifest.json') if experiment else '', 'kit_sha':source['kitManifestSha256'],
        'application':application,'powershell':str(kit/'runtime/powershell') if experiment else '',
        'watcher_setup_sha':'','watcher_sha':'','watcher_helper_sha':'',
        'native_watcher_payload_sha':source['kitManifestSha256'] if native_watcher else '',
        'native_watcher_application_lifetime':'1' if application_lifetime else '',
        'native_watcher_output_ready_trial':'1' if watcher_profile.get('outputReadyTrial') is True else '',
        'native_watcher_diagnostic_frames':str(buffer_frames) if buffer_frames == 32 or
            (buffer_frames == 64 and watcher_profile.get('outputDeadlineTrial') is True) else ''}
    watcher_assets={}
    if watcher_dll is not None:
        require(experiment is None,'Watcher bundling requires a portable window')
        watcher_source=Path('scripts/native/serato-notice-startup')
        files={'setup-notice-startup.ps1':ROOT/watcher_source/'setup-notice-startup.ps1',
               'watch-notice-startup.ps1':ROOT/watcher_source/'watch-notice-startup.ps1',
               'sl3-notice-startup-early.dll':Path(watcher_dll).absolute()}
        watcher_assets={name:{'path':str(path),'sha256':sha(path)} for name,path in files.items()}
        pins.update({str(path.relative_to(ROOT).as_posix()):sha(path) for path in files.values() if path.suffix=='.ps1'})
        pins[(watcher_source/'notice-startup.cpp').as_posix()]=sha(ROOT/watcher_source/'notice-startup.cpp')
        values['watcher_setup_sha']=watcher_assets['setup-notice-startup.ps1']['sha256']
        values['watcher_sha']=watcher_assets['watch-notice-startup.ps1']['sha256']
        values['watcher_helper_sha']=watcher_assets['sl3-notice-startup-early.dll']['sha256']
        require(values['watcher_helper_sha'].upper() in files['watch-notice-startup.ps1'].read_text(encoding='utf-8'),
                'The watcher must pin the bundled helper DLL')
    config='#pragma once\nnamespace session_window_config {\n'+''.join('inline const std::wstring '+k+'=L'+json.dumps(v)+';\n' for k,v in values.items())+'}\n'
    launcher=(source_path.parent/'launcher_config.hpp').read_text(encoding='utf-8')
    resource=(ROOT/'src/installer/SetupWindow.rc').as_posix()
    cmake=('cmake_minimum_required(VERSION 3.20)\nproject(sl3_setup_window LANGUAGES CXX RC)\nset(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")\n'
        'add_executable(SL3_Compatibility_Setup WIN32 "'+(ROOT/'src/installer/SetupWindow.cpp').as_posix()+'" "'+resource+'")\n'
        'add_executable(sl3_setup_window_tests "'+(ROOT/'tests/native/setup_window_tests.cpp').as_posix()+'" "'+resource+'")\n'
        'foreach(target SL3_Compatibility_Setup sl3_setup_window_tests)\n target_compile_features(${target} PRIVATE cxx_std_17)\n'
        ' target_compile_definitions(${target} PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX)\n'
        ' target_compile_options(${target} PRIVATE $<$<COMPILE_LANGUAGE:CXX>:/W4;/WX;/permissive-;/EHsc;/utf-8>)\n'
        ' target_include_directories(${target} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "'+(ROOT/'src/installer').as_posix()+'")\n'
        ' target_link_libraries(${target} PRIVATE windowsapp shell32 ole32 bcrypt advapi32 user32 gdi32 comctl32)\nendforeach()\n'
        'enable_testing()\nadd_test(NAME setup_window_contract COMMAND sl3_setup_window_tests)\nset_tests_properties(setup_window_contract PROPERTIES TIMEOUT 120)\n')
    require(output.parent.resolve()==(ROOT/'artifacts/build').resolve() and output.name.startswith('native-setup-window-') and not output.exists(),'Fresh setup window build output required');output.mkdir()
    for name,text in [('session_window_config.hpp',config),('launcher_config.hpp',launcher),('CMakeLists.txt',cmake)]:(output/name).write_text(text,encoding='utf-8')
    manifest={'schema':'sl3.setup-window-source.v1','sourcePins':pins,'generatedPins':{n:sha(output/n) for n in ('session_window_config.hpp','launcher_config.hpp','CMakeLists.txt')},
        'entryBuildSha256':expected,'nativeEntrySha256':build['executableSha256'],'experimentSha256':experiment_sha,'kitManifestSha256':source['kitManifestSha256'],
        'automaticActionsOnOpen':False,'elevationRequested':False,'seratoLaunched':False,'nativeDeviceAccess':False}
    if experiment is None:manifest['portableLayout']={'entry':str(entry),'kit':str(kit),'manifestName':manifest_name}
    if watcher_assets:manifest['portableLayout']['watcherAssets']=watcher_assets
    (output/'window-source.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8');return {'prepared':True,'directory':str(output),'sourceManifestSha256':sha(output/'window-source.json')}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('entry-build','expected-entry-build-sha256','kit','output'):p.add_argument('--'+name,required=True)
    for name in ('experiment','expected-experiment-sha256'):p.add_argument('--'+name)
    p.add_argument('--watcher-dll')
    a=p.parse_args();print(json.dumps(prepare(a.entry_build,a.expected_entry_build_sha256,a.kit,a.experiment,a.expected_experiment_sha256,a.output,a.watcher_dll),indent=2))
