"""Verify saved non-elevated descriptor-only access; never load the USB helper."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def validate_result(record, output):
    for name in ('parentToken', 'childToken'):
        token = record[name]
        require(token['elevated'] is False and type(token['elevationType']) is int and token['elevationType'] == 3,
                'Expected actually queried limited non-elevated tokens')
    require(record['tokenQueryError'] is None and record['childExited'] is True and
            record['forcedTermination'] is False and type(record['exitCode']) is int and record['exitCode'] == 0,
            'Token query, native exit or retirement failed')
    require(type(record['elapsedSeconds']) in (int, float) and math.isfinite(record['elapsedSeconds']) and
            record['elapsedSeconds'] > 0, 'Invalid process timing')
    expected = {'matched_sl3': 1, 'descriptor_fixture_matches': True, 'high_speed': True, 'device_redirected': False}
    require(output == expected and all(type(output[k]) is type(v) for k, v in expected.items()), 'Not a descriptor-only success')
    return {'nonElevatedDescriptorAccessVerified': True, 'redirectAccessVerified': False,
            'nonElevatedStreamingVerified': False, 'separateStandardAccountTested': False}


def main():
    folder = ROOT/'tests/results/local/usbdk-user-list-20261030-01'
    record = read(folder/'run.json'); output = read(folder/'stdout.txt')
    result = validate_result(record, output)
    checkpoint = ROOT/'artifacts/build/checkpoints/control-selection-io-20261030'
    build_path = checkpoint/'native-build-Release.json'; build = read(build_path)
    require(digest(build_path) == record['manifestSha256'] and
            digest(checkpoint/'Release/sl3_usbdk.exe') == record['workerSha256'] == build['usbdk']['executableSha256'].lower(),
            'Archived tested native identity differs')
    require(record['helperSha256'] == '66bbfe6f99b417f97c7a9e97816e24af7dde0e01b8e535c41e91e1c6c19cfeda' and
            digest(ROOT/'artifacts/extracted/usbdk-msi/UsbDkHelper.dll10') == record['helperSha256'], 'Reviewed helper differs')
    for name in ('stdout', 'stderr'):
        require(digest(folder/(name+'.txt')) == record[name+'Sha256'], 'Native output binding differs')
    require((folder/'stderr.txt').read_bytes() == b'', 'Native helper reported an error')
    source_path = ROOT/'artifacts/build/checkpoints/usbdk-user-list-20261030/usbdk_main.cpp'
    require(digest(source_path) == build['inputs']['src/windows/usbdk_main.cpp'].lower(), 'Archived list source differs')
    source = source_path.read_text(encoding='utf-8-sig')
    scope = source[source.index('Watchdog watchdog;Api api;api.load(helper);auto selected=api.select();'):]
    require(scope.index('if(list){') < scope.index('Device device(api)') and
            '"' not in scope[:scope.index('if(list){')] and
            'device_redirected\\\":false' in scope[:scope.index('Device device(api)')], 'List early-return guard differs')
    spec = importlib.util.spec_from_file_location('access_source', ROOT/'scripts/prepare-usbdk-lifecycle-trace.py')
    pinned = importlib.util.module_from_spec(spec); spec.loader.exec_module(pinned)
    refs = ROOT/'artifacts/references/usbdk-1.0.22'
    sources = {}
    for name in ('ControlDevice.cpp', 'UsbDkHelper.cpp', 'UsbDkUtil.cpp'):
        text = (refs/name).read_text(encoding='utf-8-sig')
        require(hashlib.sha256(text.encode()).hexdigest() == pinned.SOURCE_LF[name], 'Reviewed access source changed')
        sources[name] = pinned.SOURCE_LF[name]
    control = (refs/'ControlDevice.cpp').read_text()
    require('WdfControlDeviceInitAllocate(Driver, &SDDL_DEVOBJ_SYS_ALL_ADM_RWX_WORLD_RWX_RES_RWX)' in control and
            'UsbDkCreateCurrentProcessHandle(Context->CallerProcessHandle)' in control, 'Reviewed access/caller route differs')
    post = read(folder/'post-state.json'); props = {p['KeyName']: p['Data'] for p in post['properties']}
    require(props == {'DEVPKEY_Device_ProblemCode': 39, 'DEVPKEY_Device_Service': 'strmdrv',
                      'DEVPKEY_Device_DriverInfPath': 'oem136.inf'} and post['testProcesses'] == [] and
            post['secureBootAttested'] is False, 'Original resting post-state differs')
    result.update(scope='Actual limited-token descriptor-only access; source review does not prove streaming permission',
                  parentToken=record['parentToken'], childToken=record['childToken'], childExited=True,
                  elapsedSeconds=record['elapsedSeconds'], nativeOutput=output, workerSha256=record['workerSha256'],
                  helperSha256=record['helperSha256'], reviewedSourceCommit=pinned.COMMIT, sourceLfSha256=sources,
                  nativeListSourceSha256=digest(source_path),
                  controlDeviceSddlMacro='SDDL_DEVOBJ_SYS_ALL_ADM_RWX_WORLD_RWX_RES_RWX',
                  liveDeviceAclDumped=False, aclChanged=False, secureBootAttestedDuringRun=False,
                  fullRecoveryAttested=False,
                  files={name: digest(folder/name) for name in ('run.json', 'stdout.txt', 'stderr.txt', 'post-state.json')},
                  limits=['The current account used its limited token; a separately created standard-user account was not tested',
                          'No StartRedirect, SL3 command-pipe transaction, audio, native ASIO deployment or Serato open',
                          'Default source descriptor is not an attestation of every live policy/ACL override',
                          'Driver installation/tracing administrative requirements remain separate from runtime transport',
                          'Repeated redirection readiness remains unresolved independently of access rights'])
    log = ROOT/'analysis/usbdk-user-access-python-tests.log'
    text = log.read_text(encoding='utf-8-sig')
    require('Ran 114 tests' in text and text.rstrip().endswith('OK'), 'Access evidence software checks failed')
    result['softwareChecks'] = {'fullPythonTests': 114, 'logSha256': digest(log),
                                'testSourceSha256': digest(ROOT/'tests/test_usbdk_user_access.py')}
    (ROOT/'docs/evidence/usbdk-user-access-20261030.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('Verified actual limited parent/child tokens, exact native descriptor-only result and reviewed access source; redirection remains untested')


if __name__ == '__main__':
    main()
