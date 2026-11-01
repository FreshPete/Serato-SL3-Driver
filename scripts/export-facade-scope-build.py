"""Bind explicit cross-facade ownership tests to their current Release build."""
import importlib.util
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('recreation_exports',ROOT/'scripts/export-asio-recreation-build.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
require,sha,read=helper.require,helper.sha,helper.read


def main():
    folder=ROOT/'artifacts/build/native';manifest=folder/'native-build-Release.json';build=read(manifest)
    for name,digest in build['inputs'].items():require(sha(ROOT/name)==digest.lower(),'Stale build input: '+name)
    require(sha(ROOT/'scripts/build-native.ps1')==build['buildScriptSha256'].lower(),'Changed build runner')
    log=folder/'ctest-Release.log';text=log.read_text(encoding='utf-8-sig')
    require(sha(log)==build['ctestLogSha256'].lower() and len(build['ctestTests'])==50 and
            '100% tests passed, 0 tests failed out of 50' in text,'Missing full Release result')
    for name in ('sl3_retained_host_tests','sl3_asio_retained_session_tests','sl3_asio_session_tests','sl3_driver_facade_tests',
                 'sl3_scope_probe_plan','sl3_scope_probe_lifecycle'):
        require(re.search(r'\b'+name+r'\s+\.+\s+Passed',text),'Missing tested owner path: '+name)
    feature=build['asioComponent']['hostSession']['facadeScope']
    require(feature=={'implemented':True,'exclusiveBorrowTested':True,'singleAcquisitionAcrossThreeComObjectsTested':True,
                     'explicitCloseTested':True,'failedOwnerSealedTested':True,'blockedCallbackRetirementTested':True,
                     'productionProviderUsesSharedScope':False,'physicalScopeTested':False,'timingSynthetic':True},
            'Scope feature contract differs')
    controller=build['asioComponent']['hostSession']['factoryScope']
    require(controller=={'productionCapabilityImplemented':True,'defaultFactoryUsesScope':False,
                         'preparationDoesNotAcquire':True,'singleAttemptPerFactory':True,
                         'explicitRetirementChecked':True,'canonicalComIdentityTested':True,
                         'controllerBeforeDeviceReleaseTested':True,'uninitializedDeviceAfterCloseTested':True,
                         'failedEndNoFallbackTested':True,'missingProductionConfigurationRejected':True,'physicalScopeTested':False,
                         'currentSeratoUsesScope':False},'Factory controller contract differs')
    refresh=build['asioComponent']['hostSession']['clockRefresh']
    require(refresh=={'readOnly':True,'opcode':'0x307','wireLayoutVersion':3,'recreatedFacadeReadsFreshClock':True,
                      'preparedBuffersAndActiveAudioRefused':True,'cachedFallbackOnFailure':False,
                      'changedClockMetadataTested':True,'timingProfileMismatchTested':True,
                      'physicalRefreshTested':False},'Clock refresh contract differs')
    facade=build['asioComponent']['driverFacade']
    identities={'sl3_asio.dll':build['asioComponent']['comDllSha256'],
                'sl3_asio_session_fixture.dll':facade['sessionFixtureDllSha256'],
                'sl3_asio_session_tests.exe':facade['sessionAbiTestExecutableSha256'],
                'sl3_retained_host_tests.exe':build['asioComponent']['hostSession']['retained']['testExecutableSha256'],
                'sl3_device_session_fixture.exe':build['deviceSession']['fixtureSha256'],
                'sl3_scope_probe.exe':build['scopeProbe']['executableSha256'],
                'sl3_scope_probe_simulated.exe':build['scopeProbe']['simulatedExecutableSha256']}
    for name,digest in identities.items():require(sha(folder/'Release'/name)==digest.lower(),'Changed tested binary: '+name)
    native=helper.exports(folder/'Release/sl3_asio.dll');fixture=helper.exports(folder/'Release/sl3_asio_session_fixture.dll')
    require(not any(name.startswith('sl3_test_') for name in native),'Test owner interface leaked into production')
    require({'sl3_test_configure_shared_owner_audit','sl3_test_close_shared_owner'}<=fixture,'Missing fixture scope controls')
    scope_probe=build['scopeProbe']
    require(scope_probe['planAndSimulatedLifecyclePassed'] is True and scope_probe['facadeObjects']==scope_probe['clockReads']==3 and
            scope_probe['acquisitions']==1 and scope_probe['audioStarts']==0 and scope_probe['timingProfileRequired'] is False and
            scope_probe['physicalScopeTested'] is False,'Metadata probe contract differs')
    require(sha(ROOT/'scripts/test-scope-host-probe.py')==scope_probe['testScriptSha256'].lower() and
            sha(ROOT/'scripts/validate-scope-host-probe.py')==scope_probe['validatorSha256'].lower(),'Probe test/validator changed')
    failed=ROOT/'analysis/facade-scope-first-failed-ctest-20261101.log'
    diagnostic=ROOT/'analysis/facade-scope-queue-diagnostic-absolute-20261101.json'
    require('Echo actual schedule to simulated worker' in failed.read_text(encoding='utf-8-sig'),
            'Missing preserved intermediate failure')
    attempts=read(diagnostic)
    require(len(attempts)==12 and all(row['exitCode']==0 for row in attempts),'Diagnostic repetition record differs')
    result={'scope':'Actual unregistered COM/IASIO plus isolated simulated worker; no physical USB/Serato operation',
            'releaseTestsPassed':50,'manifestSha256':sha(manifest),'ctestLogSha256':sha(log),
            'feature':feature,'factoryController':controller,'clockRefresh':refresh,'metadataProbe':scope_probe,
            'binaries':{name:value.lower() for name,value in identities.items()},
            'sharedComAudit':{'objects':3,'enumerationObjects':1,'audioObjects':2,'streamsPerAudioObject':2,
                              'acquisitions':1,'clockReads':7,'audioBeginEndPairs':4,'finalReleases':1,
                              'auditComparedAfterEveryStage':True,'competingBorrowAndCloseRejected':True},
            'productionTestExportsAbsent':True,'registrationChanged':False,'physicalScopeVerified':False,
            'intermediateQueueFailure':{'logSha256':sha(failed),'returnedQueueStatusRecorded':False,
                                        'causeVerified':False,'diagnosticRepeatsPassed':12,
                                        'diagnosticRecordSha256':sha(diagnostic),
                                        'testClientNowHandlesOnlyFullAsBackpressure':True,
                                        'overallDeadlineIncreased':False},
            'sourceInputs':{name:value.lower() for name,value in build['inputs'].items() if name in
                            ('src/asio/driver_facade.hpp','src/asio/driver_facade.cpp','src/asio/host_session.hpp',
                             'src/asio/host_session.cpp','src/asio/com_server.cpp','tests/native/asio_session_provider.cpp',
                             'tests/native/asio_session_tests.cpp','tests/native/retained_host_tests.cpp',
                             'src/asio/scope_interface.hpp','src/asio/driver_configuration.hpp',
                             'src/asio/driver_configuration.cpp','tests/native/asio_com_tests.cpp',
                             'src/core/device_session_protocol.hpp','src/windows/device_session.hpp',
                             'src/windows/device_session.cpp','tests/native/device_session_fixture.cpp',
                             'tests/native/device_session_tests.cpp')},
            'limits':['Default production factory still creates one owner per object unless explicitly scoped before first creation',
                      'The project scope capability is not requested by the inspected current Serato backend',
                      'Recreated metadata objects refresh the held clock; every audio begin also verifies it',
                      'Simulation does not prove physical handoff, analogue mapping, latency or current Serato admission']}
    output=ROOT/'docs/evidence/facade-scope-build-20261101.json';output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
