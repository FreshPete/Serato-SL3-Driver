param([ValidateSet('Debug','Release')][string]$Configuration='Release',[switch]$WithAsioComponent,[switch]$WithUnmeasuredAsioDiagnostic,
      [string]$BuildDirectory='artifacts/build/native')
$ErrorActionPreference='Stop'
if($WithUnmeasuredAsioDiagnostic -and -not $WithAsioComponent){throw 'The unmeasured diagnostic requires the ASIO component'}
$root=Split-Path -Parent $PSScriptRoot
$build=[IO.Path]::GetFullPath($(if([IO.Path]::IsPathRooted($BuildDirectory)){$BuildDirectory}else{Join-Path $root $BuildDirectory}))
$buildRoot=[IO.Path]::GetFullPath((Join-Path $root 'artifacts/build'))+[IO.Path]::DirectorySeparatorChar
if(-not $build.StartsWith($buildRoot,[StringComparison]::OrdinalIgnoreCase)){throw 'BuildDirectory must be below this project artifacts/build'}
New-Item -ItemType Directory -Force -Path $build | Out-Null
Start-Transcript -Path (Join-Path $build "build-$Configuration.log") | Out-Null
try {
    $asioOption=if($WithAsioComponent){'ON'}else{'OFF'}
    $diagnosticOption=if($WithUnmeasuredAsioDiagnostic){'ON'}else{'OFF'}
    & cmake -S $root -B $build -G 'Visual Studio 16 2019' -A x64 '-DCMAKE_SYSTEM_VERSION=10.0.19041.0' "-DSL3_BUILD_ASIO_COMPONENT=$asioOption" "-DSL3_BUILD_UNMEASURED_ASIO_DIAGNOSTIC=$diagnosticOption"
    if($LASTEXITCODE -ne 0){throw 'Native CMake configuration failed'}
    & cmake --build $build --config $Configuration
    if($LASTEXITCODE -ne 0){throw 'Native build failed'}
    $testListingText=& ctest --test-dir $build -C $Configuration --show-only=json-v1
    if($LASTEXITCODE -ne 0){throw 'Native test inventory failed'}
    $testNames=@(($testListingText|ConvertFrom-Json).tests|ForEach-Object name)
    if($WithUnmeasuredAsioDiagnostic){
        foreach($name in @('sl3_asio_unmeasured_absent','sl3_broker_unmeasured_plan',
            'sl3_broker_unmeasured_rejects_long_lifetime','sl3_broker_unmeasured_lifecycle')){
            if($name -notin $testNames){throw "Required unmeasured ASIO diagnostic check missing: $name"}
        }
    }
    foreach($required in @('sl3_rate_selection_tests','sl3_control_frames_tests','sl3_core_tests','sl3_playback_tests','sl3_audio_bridge_tests','sl3_duplex_tests','sl3_continuous_tests','sl3_usbdk_stream_tests','sl3_session_tests','sl3_usbdk_rejects_stream_modes','sl3_worker_process_tests','sl3_mailbox_tests','sl3_audio_ring_tests','sl3_worker_protocol_tests','sl3_usbdk_rejects_worker_capture','sl3_capture_plan','sl3_capture_rejects_modes','sl3_usbdk_plan','sl3_usbdk_rejects_modes','sl3_usbdk_rejects_duplex_capture')){
        if($required -notin $testNames){throw "Required native test is missing: $required"}
    }
    if('sl3_input_recorder_tests' -notin $testNames){throw 'Required PCM prefix recorder test missing'}
    if('sl3_output_recorder_tests' -notin $testNames){throw 'Required software output recorder test missing'}
    if('sl3_output_capture_lifecycle' -notin $testNames){throw 'Required software output capture lifecycle test missing'}
    if($WithAsioComponent){foreach($name in @('sl3_input_record_probe_plan','sl3_input_record_probe_lifecycle')){if($name -notin $testNames){throw "Required input recording probe test missing: $name"}}}
    if('sl3_timer_verification_tests' -notin $testNames){throw 'Required timer-verification test is missing'}
    if('sl3_redirect_owner_tests' -notin $testNames){throw 'Required interprocess redirect ownership test is missing'}
    if('sl3_retained_broker_tests' -notin $testNames){throw 'Required separate-client retained broker test is missing'}
    if('sl3_broker_pipe_tests' -notin $testNames){throw 'Required authenticated broker pipe/process tests are missing'}
    if('sl3_broker_record_tests' -notin $testNames){throw 'Required pinned broker record/process binding tests are missing'}
    foreach($name in @('sl3_broker_scope_probe_plan','sl3_broker_scope_probe_lifecycle')){if($name -notin $testNames){throw "Required read-only broker diagnostic test missing: $name"}}
    foreach($required in @('sl3_driver_timer_query_tests','sl3_driver_timer_io_tests','sl3_usbdk_timer_plan',
        'sl3_usbdk_rejects_timer_without_challenge','sl3_usbdk_rejects_timer_malformed_challenge',
        'sl3_usbdk_rejects_timer_conflict','sl3_usbdk_rejects_unused_timer_challenge')){
        if($required -notin $testNames){throw "Required driver-timer diagnostic test is missing: $required"}
    }
    if('sl3_device_presence_tests' -notin $testNames){throw 'Required enumeration-readiness test is missing'}
    if('sl3_startup_journal_tests' -notin $testNames){throw 'Required startup-journal test is missing'}
    if('sl3_device_session_tests' -notin $testNames -or 'sl3_usbdk_rejects_device_modes' -notin $testNames){throw 'Required retained-device worker tests are missing'}
    if($WithAsioComponent -and 'sl3_asio_buffer_tests' -notin $testNames){throw 'Required SDK-facing ASIO test is missing'}
    if($WithAsioComponent){foreach($required in @('sl3_asio_activation_sta','sl3_asio_activation_mta')){if($required -notin $testNames){throw "Required Windows COM activation check missing: $required"}}}
    if($WithAsioComponent -and 'sl3_asio_com_tests' -notin $testNames){throw 'Required ASIO COM DLL test is missing'}
    if($WithAsioComponent -and 'sl3_asio_call_trace_tests' -notin $testNames){throw 'Required ASIO control-call trace test is missing'}
    if($WithAsioComponent -and 'sl3_broker_asio_tests' -notin $testNames){throw 'Required broker-backed IASIO lifecycle test is missing'}
    if($WithAsioComponent){foreach($required in @('sl3_broker_controller_plan','sl3_broker_controller_lifecycle')){if($required -notin $testNames){throw "Required broker controller check missing: $required"}}}
    if($WithAsioComponent -and 'sl3_asio_queue_tests' -notin $testNames){throw 'Required queue-to-SDK test is missing'}
    if($WithAsioComponent -and 'sl3_audio_owner_tests' -notin $testNames){throw 'Required audio-thread ownership test is missing'}
    if($WithAsioComponent -and 'sl3_host_session_tests' -notin $testNames){throw 'Required host-session control test is missing'}
    if($WithAsioComponent -and ('sl3_retained_host_tests' -notin $testNames -or 'sl3_asio_retained_session_tests' -notin $testNames)){throw 'Required retained ASIO lifecycle tests are missing'}
    if($WithAsioComponent -and ('sl3_host_probe_plan' -notin $testNames -or 'sl3_host_probe_lifecycle' -notin $testNames)){throw 'Required bounded host-probe tests are missing'}
    if($WithAsioComponent -and 'sl3_retained_probe_lifecycle' -notin $testNames){throw 'Required retained-lifecycle probe test is missing'}
    if($WithAsioComponent -and 'sl3_controls_probe_lifecycle' -notin $testNames){throw 'Required controls-only probe test is missing'}
    if($WithAsioComponent -and 'sl3_selection_probe_lifecycle' -notin $testNames){throw 'Required selection probe test is missing'}
    if($WithAsioComponent -and 'sl3_driver_facade_tests' -notin $testNames){throw 'Required ASIO facade test is missing'}
    if($WithAsioComponent){foreach($name in @('sl3_scope_probe_plan','sl3_scope_probe_lifecycle')){if($name -notin $testNames){throw "Required scope diagnostic test is missing: $name"}}}
    if($WithAsioComponent -and 'sl3_rate_probe_lifecycle' -notin $testNames){throw 'Required held-rate probe process tests are missing'}
    if($WithAsioComponent -and 'sl3_asio_session_tests' -notin $testNames){throw 'Required actual ASIO session ABI test is missing'}
    if($WithAsioComponent -and 'sl3_driver_configuration_tests' -notin $testNames){throw 'Required production ASIO configuration test is missing'}
    $ctestLog=Join-Path $build "ctest-$Configuration.log"
    & ctest --test-dir $build -C $Configuration --output-on-failure --output-log $ctestLog
    if($LASTEXITCODE -ne 0){throw 'Native capture core tests failed'}
    $exe=Join-Path $build "$Configuration/sl3_capture.exe"
    $planText=& $exe --plan
    if($LASTEXITCODE -ne 0){throw 'Native plan-only smoke test failed'}
    $plan=$planText | ConvertFrom-Json
    if(-not $plan.plan_only -or $plan.driver_changes){throw 'Unexpected default capture behaviour'}
    $usbdkExe=Join-Path $build "$Configuration/sl3_usbdk.exe"
    $usbdkPlanText=& $usbdkExe --plan
    if($LASTEXITCODE -ne 0){throw 'UsbDk plan-only smoke test failed'}
    $usbdkPlan=$usbdkPlanText|ConvertFrom-Json
    if(-not $usbdkPlan.plan_only -or $usbdkPlan.helper_loaded -or $usbdkPlan.driver_changes){throw 'Unexpected UsbDk plan behaviour'}
    $inputs=@{}
    $sourceFiles=@(Get-Item -LiteralPath (Join-Path $root 'CMakeLists.txt')) + @(Get-ChildItem -LiteralPath (Join-Path $root 'src') -Recurse -File | Where-Object Extension -in @('.cpp','.hpp')) + @(Get-ChildItem -LiteralPath (Join-Path $root 'tests/native') -Recurse -File | Where-Object Extension -in @('.cpp','.hpp'))
    $sourceFiles+=@(Get-ChildItem -LiteralPath (Join-Path $root 'third_party/usbdk') -File)
    $sourceFiles+=@(Get-Item -LiteralPath (Join-Path $root 'src/asio/sl3_asio.def'))
    $sourceFiles+=@(Get-ChildItem -LiteralPath (Join-Path $root 'tests/native') -Filter '*.def' -File)
    if($WithAsioComponent){
        $sourceFiles+=@(Get-Item -LiteralPath (Join-Path $root 'artifacts/references/asio-sdk-2.3.4/ASIOSDK/common/asio.h'),(Join-Path $root 'artifacts/references/asio-sdk-2.3.4/ASIOSDK/common/asiosys.h'))
        $sourceFiles+=@(Get-Item -LiteralPath (Join-Path $root 'artifacts/references/asio-sdk-2.3.4/ASIOSDK/common/iasiodrv.h'))
    }
    $sourceFiles+=@(Get-Item -LiteralPath (Join-Path $root 'scripts/export-output-capture.py'),(Join-Path $root 'scripts/test-output-capture.py'))
    foreach($file in $sourceFiles){$inputs[$file.FullName.Substring($root.Length+1).Replace('\','/')]=(Get-FileHash -LiteralPath $file.FullName).Hash}
    $record=[ordered]@{utc=[datetime]::UtcNow.ToString('o');configuration=$Configuration;architecture='x64';generator='Visual Studio 16 2019';windowsSdk='10.0.19041.0';coreTestsPassed=$true;planOnlyPassed=$true;physicalCaptureTested=$false;inputs=$inputs;executableSha256=(Get-FileHash -LiteralPath $exe).Hash;executableBytes=(Get-Item -LiteralPath $exe).Length}
    $record.ctestTests=$testNames
    $record.redirectOwner=[ordered]@{softwareTestsPassed=$true;testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_redirect_owner_tests.exe")).Hash
        nativeOpenGuardConnected=$true;globalObject=$true;nonWaiting=$true;retainedAcrossAudioStop=$true
        physicalOverlapTested=$false;kernelDetachmentVerified=$false;safeSuccessiveAcquisitionVerified=$false}
    $record.inputRecorder=[ordered]@{softwareTestsPassed=$true;testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_input_recorder_tests.exe")).Hash;fixedCallbackPrefix=$true;callbackAllocationTestsPassed=$true;physicalRecordingRun=$false}
    $record.outputCapture=[ordered]@{softwareTestsPassed=$true;maximumSeconds=5;optInEnvironment='SL3_OUTPUT_CAPTURE_DIRECTORY'
        manualArmRequired=$true;sampleRates=@(44100,48000);source='worker-dequeued-output-pcm';fileIoOnStreamThread=$false
        physicalSeratoRecordingRun=$false;analogOutputVerified=$false;usbCompletionVerified=$false
        recorderTestSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_output_recorder_tests.exe")).Hash
        lifecycleFixtureSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_output_capture_fixture.exe")).Hash}
    if($WithAsioComponent){$record.inputRecordProbe=[ordered]@{planAndSimulatedRecordingPassed=$true
        executableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_input_record_probe.exe")).Hash
        simulatedExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_input_record_probe_simulated.exe")).Hash
        testScriptSha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'test-input-record-probe.py')).Hash
        validatorSha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'validate-input-record-probe.py')).Hash
        simulatedFullPrefixBytesVerified=$true;nominalMilliseconds=3000;outputPayload='zero PCM only';physicalNativeRun=$false;tracedRunnerPrepared=$true}}
    $record.ctestLogSha256=(Get-FileHash -LiteralPath $ctestLog).Hash
    $record.buildScriptSha256=(Get-FileHash -LiteralPath $PSCommandPath).Hash
    $record.brokerScopeProbe=[ordered]@{planAndSimulatedLifecyclePassed=$true
        executableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_broker_scope_probe.exe")).Hash
        simulatedExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_broker_scope_probe_simulated.exe")).Hash
        testScriptSha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'test-broker-scope-probe.py')).Hash
        simulatedClientProcesses=3;simulatedClockReads=7;simulatedAcquisitions=1;audioStarts=0
        serverRejectsAudio=$true;timingProfileRequired=$false;asioConfigurationPublished=$false;physicalNativeRun=$false}
    $record.retainedBroker=[ordered]@{separateClientProcessTestsPassed=$true
        testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_retained_broker_tests.exe")).Hash
        simulatedClients=2;simulatedAcquisitions=1;simulatedStreams=2;simulatedClockReads=6
        clientDeathAndStaleLeaseTestsPassed=$true;nativeBrokerRun=$false;productionAsioClientAttachmentEnabled=$false}
    $record.brokerPipe=[ordered]@{simulatedProcessTestsPassed=$true
        testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_broker_pipe_tests.exe")).Hash
        exactProcessChallenge=$true;clientMappingReferenceBound=$true;directPcm=$true
        terminalDetachAcknowledgement=$true
        nativeRun=$false;automaticDiscoveryImplemented=$false;productionOrdinaryAsioAttachmentEnabled=$false}
    $record.brokerRecord=[ordered]@{softwareTestsPassed=$true
        testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_broker_record_tests.exe")).Hash
        recordAndImagePinned=$true;processCreationIdentityChecked=$true;runtimeWorkerHashContract=$true
        recordPublicationImplemented=$WithAsioComponent.IsPresent;nativePositiveRun=$false}
    if($WithAsioComponent){$record.brokerController=[ordered]@{planAndSimulatedLifecyclePassed=$true
        executableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_broker_controller.exe")).Hash
        simulatedExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_broker_controller_simulated.exe")).Hash
        testScriptSha256=(Get-FileHash -LiteralPath (Join-Path $root 'scripts/test-broker-controller.py')).Hash
        explicitLifetimeAndStop=$true;nativeStartupJournalWired=$true;atomicPublication=$true
        nativePositiveRun=$false;installed=$false;registrationChanged=$false}}
    if($WithUnmeasuredAsioDiagnostic){$record.unmeasuredAsioDiagnostic=[ordered]@{
        dllSha256=(Get-FileHash -LiteralPath (Join-Path $build "unmeasured/$Configuration/sl3_asio.dll")).Hash
        brokerSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_broker_controller_unmeasured.exe")).Hash
        simulatedBrokerSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_broker_controller_unmeasured_simulated.exe")).Hash
        rateHz=44100;bufferFrames=128;latencyAvailable=$false;maximumLifetimeMs=600000
        simulatedCallbacksPassed=$true;nativePositiveRun=$false;installed=$false}}
    if($WithAsioComponent){$record.brokerAsio=[ordered]@{simulatedOrdinaryComLifecyclePassed=$true
        testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_broker_asio_tests.exe")).Hash
        ordinaryObjects=3;starts=4;acquisitions=1;freshClockReads=8;customFactoryScopeRequested=$false
        clientDetachDistinctFromPhysicalRelease=$true;blockedCallbackModuleRetentionPassed=$true
        productionRecordConfigurationSupported=$true;productionBrokerConfigurationInstalled=$false;nativeBrokerAudioRun=$false}}
    if($WithAsioComponent){$record.hostProbe=[ordered]@{planAndSimulatedLifecyclePassed=$true;executableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_host_probe.exe")).Hash;simulatedExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_host_probe_simulated.exe")).Hash;nativeDeviceRunDuringBuild=$false;streamMilliseconds=1000;outputPayload='zero PCM only';singleOpenIntervals=@(8,64)}}
    if($WithAsioComponent){$record.scopeProbe=[ordered]@{planAndSimulatedLifecyclePassed=$true;executableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_scope_probe.exe")).Hash;simulatedExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_scope_probe_simulated.exe")).Hash;validatorSha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'validate-scope-host-probe.py')).Hash;testScriptSha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'test-scope-host-probe.py')).Hash;facadeObjects=3;acquisitions=1;clockReads=3;audioStarts=0;timingProfileRequired=$false;physicalScopeTested=$false}}
    if($WithAsioComponent){$record.hostProbe.retained=[ordered]@{simulatedLifecyclePassed=$true;streams=2;streamMilliseconds=1000;intervals=8;bankFrames=128;physicalLifecycleTested=$false;validatorSha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'validate-retained-host-probe.py')).Hash;testScriptSha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'test-retained-host-probe.py')).Hash;runnerSha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'test-retained-host-traced.ps1')).Hash}}
    if($WithAsioComponent){
        $record.hostProbe.controls=[ordered]@{simulatedLifecyclePassed=$true;nativeQueryRunDuringBuild=$false;audioStartAttempts=0;getter='0x32';scriptInputs=[ordered]@{}}
        foreach($name in @('test-controls-host-traced.ps1','validate-controls-host-probe.py','test-controls-host-probe.py','read-startup-journal.ps1',
            'capture-usb-startup.ps1','preflight-usbdk.ps1','collect-windows-state.ps1','export-usbdk-physical-checkpoint.py','validate-usbdk-capture.py',
            'prepare-usbdk-lifecycle-trace.py','observe-sl3-usb-identity.py','supervise-usb-identity.py','controls-usb-identity.py',
            'capture-controls-user-context.ps1','test-controls-user-probe.ps1','inspect-process.psm1','validate-controls-user-probe.py','validate-usb-state-capture.py')){
            $record.hostProbe.controls.scriptInputs[$name]=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name)).Hash
        }
        $record.scopeProbe.scriptInputs=[ordered]@{}
        foreach($name in @($record.hostProbe.controls.scriptInputs.Keys)+@('validate-scope-host-probe.py')){
            $record.scopeProbe.scriptInputs[$name]=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name)).Hash
        }
        $record.brokerScopeProbe.scriptInputs=[ordered]@{}
        foreach($name in @($record.hostProbe.controls.scriptInputs.Keys)+@('validate-broker-scope-probe.py')){
            $record.brokerScopeProbe.scriptInputs[$name]=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name)).Hash
        }
        $record.inputRecordProbe.scriptInputs=[ordered]@{}
        foreach($name in @($record.hostProbe.controls.scriptInputs.Keys)+@('validate-input-record-probe.py')){
            $record.inputRecordProbe.scriptInputs[$name]=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name)).Hash
        }
        $record.inputRecordProbe.traceLauncherInputs=[ordered]@{}
        foreach($name in @('prepare-input-record-trace.py','start-input-record-trace.ps1')){
            $record.inputRecordProbe.traceLauncherInputs[$name]=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name)).Hash
        }
        $record.brokerScopeProbe.traceLauncherInputs=[ordered]@{}
        foreach($name in @('prepare-broker-scope-trace.py','start-broker-scope-trace.ps1')){
            $record.brokerScopeProbe.traceLauncherInputs[$name]=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name)).Hash
        }
        $record.scopeProbe.traceLauncherInputs=[ordered]@{}
        foreach($name in @('prepare-scope-trace.py','start-scope-trace.ps1')){
            $record.scopeProbe.traceLauncherInputs[$name]=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name)).Hash
        }
        $observerManifest=Join-Path $root 'artifacts/build/usb-state-observer/observer-build-Release.json'
        if(Test-Path -LiteralPath $observerManifest){
            $observerBuild=Get-Content -LiteralPath $observerManifest -Raw|ConvertFrom-Json
            $record.hostProbe.controls.stateObserverReferences=[ordered]@{manifestSha256=(Get-FileHash -LiteralPath $observerManifest).Hash
                executableSha256=$observerBuild.executableSha256;testRecordSha256=$observerBuild.testRecordSha256;inputs=$observerBuild.inputs}
        }
    }
    if($WithAsioComponent){
        $record.hostProbe.selection=[ordered]@{simulatedLifecyclePassed=$true;nativeSettingRunDuringBuild=$false;audioStartAttempts=0;singleTarget=$true;immutableRequestBeforeLaunch=$true;outcomeSeparateFromCleanup=$true;scriptInputs=[ordered]@{}}
        foreach($name in @('test-selection-host-probe.py','validate-selection-host-probe.py','validate-controls-host-probe.py')){
            $record.hostProbe.selection.scriptInputs[$name]=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name)).Hash
        }
        $record.hostProbe.selection.supervisedLauncherPrepared=$true
        $record.hostProbe.selection.traceScriptInputs=[ordered]@{}
        foreach($name in @($record.hostProbe.controls.scriptInputs.Keys)+@('test-selection-host-probe.py','validate-selection-host-probe.py','test-selection-user-probe.ps1','validate-selection-user-probe.py')){
            $record.hostProbe.selection.traceScriptInputs[$name]=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name)).Hash
        }
    }
    if($WithAsioComponent){
        $record.hostProbe.retained.scriptInputs=[ordered]@{}
        foreach($name in @('validate-retained-host-probe.py','test-retained-host-probe.py','test-retained-host-traced.ps1','test-retained-sequence.ps1',
                          'read-startup-journal.ps1','capture-usb-startup.ps1','preflight-usbdk.ps1','collect-windows-state.ps1',
                          'export-usbdk-physical-checkpoint.py','validate-usbdk-capture.py','analyse-callback-timing.py')){
            $record.hostProbe.retained.scriptInputs[$name]=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name)).Hash
        }
    }
    if($WithAsioComponent){
        $record.hostProbe.rateSelection=[ordered]@{testsPassed=$true;mode='--select-rate';nativeRequiresReviewedInitialRate=$true
            maximumAcquisitions=1;maximumSelections=1;audioStarts=0;physicalRateChangeTested=$false;sharedTraceImplemented=$false;scriptInputs=@{}}
        foreach($name in @('test-rate-host-probe.py','validate-rate-host-probe.py','validate-usbdk-rate.py','validate-rate-io.py','validate-controls-host-probe.py',
                          'export-usbdk-physical-checkpoint.py','validate-usbdk-capture.py')){
            $record.hostProbe.rateSelection.scriptInputs[$name]=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name)).Hash
        }
        $record.hostProbe.rateSelection.traceRunnerPrepared=$true
        $record.hostProbe.rateSelection.traceLauncherPrepared=$true
        $record.hostProbe.rateSelection.sharedTraceImplemented=$true
        $record.hostProbe.rateSelection.positiveElevatedLauncherTested=$false
        $record.hostProbe.rateSelection.traceScriptInputs=@{}
        foreach($name in @('test-controls-host-traced.ps1','validate-controls-host-probe.py','test-controls-host-probe.py',
            'read-startup-journal.ps1','capture-usb-startup.ps1','preflight-usbdk.ps1','collect-windows-state.ps1',
            'export-usbdk-physical-checkpoint.py','validate-usbdk-capture.py','prepare-usbdk-lifecycle-trace.py',
            'observe-sl3-usb-identity.py','supervise-usb-identity.py','controls-usb-identity.py','capture-controls-user-context.ps1',
            'test-controls-user-probe.ps1','inspect-process.psm1','validate-controls-user-probe.py','validate-usb-state-capture.py',
            'test-rate-host-probe.py','validate-rate-host-probe.py','validate-usbdk-rate.py','test-rate-user-probe.ps1','validate-rate-user-probe.py','validate-rate-io.py')){
            $record.hostProbe.rateSelection.traceScriptInputs[$name]=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name)).Hash
        }
        $record.hostProbe.rateSelection.traceLauncherInputs=@{}
        foreach($name in @('prepare-rate-trace.py','start-rate-trace.ps1')){
            $record.hostProbe.rateSelection.traceLauncherInputs[$name]=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name)).Hash
        }
    }
    $record.rateSelection=[ordered]@{testsPassed=$true;testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_rate_selection_tests.exe")).Hash;offlineOnly=$false;maximumRequests=3;maximumReceivedFrames=12;nativeSetterConnected=$true;nativeDiagnosticImplemented=$true;automaticStartupRateChanges=$false;physicalRateChangeTested=$false}
    $record.controlFrames=[ordered]@{testsPassed=$true;testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_control_frames_tests.exe")).Hash;maximumReceivedFrames=4;nativeRateQueryConnected=$true;additionalQueriesSubmitted=$false;deviceResponseVerified=$false;physicalQueriesTested=$false}
    $record.driverTimerDiagnostic=[ordered]@{softwareTestsPassed=$true;queryTestExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_driver_timer_query_tests.exe")).Hash
        adapterTestExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_driver_timer_io_tests.exe")).Hash
        explicitNativeMode='--timer-query';challengeBytes=8;replyBytes=8;maximumWrites=1;maximumReads=4;budgetMilliseconds=1500
        nativeQueryRunDuringBuild=$false;automaticStartupExchange=$false;responseVerified=$false;currentSeratoAdmissionVerified=$false}
    $record.controlSelectionIo=[ordered]@{injectedIoTestsPassed=$true;budgetMilliseconds=4500;maximumWrites=3;maximumReads=12;maximumSetters=1;runtimeAdapterConnected=$true;physicalSettingsTested=$false;testExecutableSha256=$record.controlFrames.testExecutableSha256}
    $record.controlSelectionWire=[ordered]@{testsPassed=$true;version=1;requestBytes=24;replyBytes=132;targetCorrelationRequired=$true;optionalFieldsCanonical=$true;workerCommandConnected=$true;physicalSettingsTested=$false;testExecutableSha256=$record.controlFrames.testExecutableSha256}
    $record.controlSelectionIpc=[ordered]@{testsPassed=$true;protocolVersion=3;command='0x306';workerWatchdogMilliseconds=7500;hostReplyMilliseconds=8000;idleHeldOnly=$true;capabilityRequired=$true;hostApiConnected=$true;simulatedProcessTestsPassed=$true;nativeAdapterConnected=$true;nativeDiagnosticOnly=$true;nativeSingleTarget=$true;nativeAudioStartRefused=$true;physicalSettingsTested=$false}
    $record.continuousEngine=[ordered]@{testsPassed=$true;testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_continuous_tests.exe")).Hash;fakeDuplexBatches=18000;slotsPerDirection=4;maximumExpectedSchedules=16;nativeUsbBackendConnected=$true;physicalAudioTested=$false}
    $record.nativeStreamAdapter=[ordered]@{testsPassed=$true;librarySha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_usbdk_stream.lib")).Hash;testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_usbdk_stream_tests.exe")).Hash;simulatedInputBatches=8000;simulatedOutputSubmissions=7984;realSharedQueuesTested=$true;isolatedFailStopCases=4;physicalUsbTested=$false;productionSessionConnected=$true;helperLoaded=$false}
    $record.streamSession=[ordered]@{protocolVersion=2;testsPassed=$true;librarySha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_stream_session.lib")).Hash;fixtureSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_session_fixture.exe")).Hash;testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_session_tests.exe")).Hash;productionWorkerLoopImplemented=$true;realProcessSimulatedLifecycleTested=$true;nativeAbsentHelperRejected=$true;physicalSessionTested=$false;asioSessionOwnerConnected=[bool]$WithAsioComponent}
    $record.deviceSession=[ordered]@{protocolVersion=3;testsPassed=$true;testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_device_session_tests.exe")).Hash;fixtureSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_device_session_fixture.exe")).Hash;nativeWorkerImplemented=$true;freshAudioChannelPerStart=$true;simulatedRetainedLifetimeTested=$true;nativeAbsentHelperRejected=$true;physicalRetainedLifetimeTested=$false;asioSessionOwnerConnected=[bool]$WithAsioComponent}
    $record.deviceSession.controls=[ordered]@{readOnly=$true;explicitIdleHeldDeviceOnly=$true;nativeQueryConnected=$true;hostApiConnected=[bool]$WithAsioComponent;maximumWrites=1;maximumReceivedFrames=4;controlBudgetMilliseconds=1500;simulatedInspectionAndFailureTestsPassed=$true;physicalQueryRunDuringBuild=$false}
    $record.workerProcess=[ordered]@{testsPassed=$true;librarySha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_worker_process.lib")).Hash;fixtureSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_worker_fixture.exe")).Hash;testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_worker_process_tests.exe")).Hash;hardwareIntegrated=$false;ipcImplemented=$false}
    $record.mailbox=[ordered]@{testsPassed=$true;librarySha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_mailbox.lib")).Hash;testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_mailbox_tests.exe")).Hash;maximumPayloadBytes=32768;crossProcessFramingImplemented=$true;continuousAudioImplemented=$false;asioConnected=$false}
    $record.mailbox.transportVersion=3
    $record.audioRings=[ordered]@{testsPassed=$true;testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_audio_ring_tests.exe")).Hash;slotsPerDirection=8;maximumPcmBytesPerBlock=8064;mappingBytes=196800;physicalAudioTested=$false;asioConnected=$false}
    $record.audioRings.allowedPacketCounts=@(8,16,24,32,40,48,56,64)
    $record.audioRings.workWakesIncludeReleasedSpace=$true
    $record.usbdkWorker=[ordered]@{protocolVersion=1;testsPassed=$true;testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_worker_protocol_tests.exe")).Hash;maximumCaptureReplyBytes=32544;finiteInputIpcImplemented=$true;physicalInputIpcTested=$false;continuousAudioImplemented=$false;audioOutputImplemented=$false;asioConnected=$false}
    $record.asioComponent=[ordered]@{built=[bool]$WithAsioComponent;testsPassed=[bool]$WithAsioComponent;driverRegistered=$false;hardwareIntegrated=$false}
    if($WithAsioComponent){
        $record.asioComponent.librarySha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_asio_buffers.lib")).Hash
        $record.asioComponent.testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_asio_buffer_tests.exe")).Hash
        $record.asioComponent.comDllSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_asio.dll")).Hash
        $record.asioComponent.comTestExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_asio_com_tests.exe")).Hash
        $record.asioComponent.registrationFreeActivation=[ordered]@{staPassed=$true;mtaPassed=$true;productionUnavailableTested=$true;simulatedBrokerStreamsTested=$true;testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_asio_activation_tests.exe")).Hash;registryChanged=$false;installed=$false;physicalAudioTested=$false;seratoAdmissionTested=$false}
        $record.asioComponent.callTrace=[ordered]@{implemented=$true;testsPassed=$true;providerGuid='953df2f7-5f98-4895-a57a-73c0188c4321';maximumCallsPerModule=4096;callbackPathsInstrumented=$false;manifestInstalled=$false;traceSessionStarted=$false;actualEtwCaptureTested=$false;physicalAudioTested=$false;testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_asio_call_trace_tests.exe")).Hash}
        $record.asioComponent.callTrace.ownedSession=[ordered]@{implemented=$true;defaultEnabled=$false;environmentFlag='SL3_ASIO_PRIVATE_TRACE';maximumSessionsPerModule=4;maximumFileMegabytes=4;ordinaryTokenOnly=$true;factoryAndDeviceLeases=$true;sessionRunDuringBuild=$false}
        $record.asioComponent.deviceInitializationAvailable=$false
        $record.asioComponent.queuePump=[ordered]@{testsPassed=$true;librarySha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_asio_queue.lib")).Hash;testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_asio_queue_tests.exe")).Hash;syntheticProcessBlocksTested=7200;physicalAudioTested=$false;continuousUsbSessionImplemented=$true;comDllConnected=$true}
        $record.asioComponent.nativeProvider=[ordered]@{implemented=$true;configurationInstalled=(Test-Path -LiteralPath (Join-Path $build "$Configuration/sl3-asio.conf"));librarySha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_driver_configuration.lib")).Hash;testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_driver_configuration_tests.exe")).Hash;productionDllRejectionTested=$true;measurementTruthVerified=$false;physicalNativeSessionTested=$false}
        $record.asioComponent.nativeProvider.sessionLocator=[ordered]@{implemented=$true;fixedBrokerAndWorkerPins=$true;exactBrokerFileIdentity=$true;mutablePointerReleasedAfterResolution=$true;immutableTargetLeasesRetained=$true;recursiveFallback=$false;createNewPointerPublicationTested=$true;existingPointerReplacement=$false;productionComKindRefusalTested=$true;simulatedStaMtaStreamsTested=$true;installed=$false;physicalNativeSessionTested=$false}
        $record.asioComponent.nativeProvider.pointerWithdrawal=[ordered]@{implemented=$true;exactHashRequired=$true;ownedTypedSingleFile=$true;exclusiveOpenedHandleDeletion=$true;readerAndHardlinkRefusalTested=$true;malformedAndSizeRefusalTested=$true;activeSimulatedClientContinues=$true;explicitRepublishTested=$true;stalePointerWithdrawalTested=$true;automaticReplacement=$false;installed=$false;physicalAudioTested=$false}
        $record.asioComponent.driverFacade=[ordered]@{testsPassed=$true;librarySha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_driver_facade.lib")).Hash;testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_driver_facade_tests.exe")).Hash;sessionAbiTestExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_asio_session_tests.exe")).Hash;sessionFixtureDllSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_asio_session_fixture.dll")).Hash;actualAsioVtableSessionsTested=$true;preferredBankRetryTested=$true;rejectedApplicationFrames=240;acceptedPreferredFrames=128;timingProfileSynthetic=$true;productionProviderConfigured=$false;physicalAudioTested=$false}
        $record.asioComponent.hostSession=[ordered]@{testsPassed=$true;librarySha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_host_session.lib")).Hash;testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_host_session_tests.exe")).Hash;clockInspectionImplemented=$true;freshWorkerPerStart=$false;temporaryModeFreshWorkerPerStart=$true;independentRetirementTested=$true;physicalAudioTested=$false;comDllConnected=$true}
        $record.asioComponent.hostSession.retained=[ordered]@{testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_retained_host_tests.exe")).Hash;productionProviderUsesRetainedDevice=$true;freshDataChannelPerStart=$true;stopPreservesDevice=$true;callbackIndependentRetirementTested=$true;actualAsioVtableTested=$true;timingProfileInstalled=$false;physicalRetainedLifecycleTested=$false}
        $record.asioComponent.hostSession.facadeScope=[ordered]@{implemented=$true;exclusiveBorrowTested=$true;singleAcquisitionAcrossThreeComObjectsTested=$true;explicitCloseTested=$true;failedOwnerSealedTested=$true;blockedCallbackRetirementTested=$true;productionProviderUsesSharedScope=$false;physicalScopeTested=$false;timingSynthetic=$true}
        $record.asioComponent.hostSession.factoryScope=[ordered]@{productionCapabilityImplemented=$true;defaultFactoryUsesScope=$false;preparationDoesNotAcquire=$true;singleAttemptPerFactory=$true;explicitRetirementChecked=$true;canonicalComIdentityTested=$true;controllerBeforeDeviceReleaseTested=$true;uninitializedDeviceAfterCloseTested=$true;failedEndNoFallbackTested=$true;missingProductionConfigurationRejected=$true;physicalScopeTested=$false;currentSeratoUsesScope=$false}
        $record.asioComponent.hostSession.clockRefresh=[ordered]@{readOnly=$true;opcode='0x307';wireLayoutVersion=3;recreatedFacadeReadsFreshClock=$true;preparedBuffersAndActiveAudioRefused=$true;cachedFallbackOnFailure=$false;changedClockMetadataTested=$true;timingProfileMismatchTested=$true;physicalRefreshTested=$false}
        $record.asioComponent.audioOwner=[ordered]@{testsPassed=$true;librarySha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_audio_owner.lib")).Hash;testExecutableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_audio_owner_tests.exe")).Hash;unregisteredFixtureDllSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_audio_owner_fixture.dll")).Hash;blockedCallbackAndDllUnloadTested=$true;callbackRetirementImplemented=$true;physicalAudioTested=$false;comDllConnected=$true;hostControlOwnerConnected=$true}
    }
    $record.usbdk=[ordered]@{executableSha256=(Get-FileHash -LiteralPath $usbdkExe).Hash;executableBytes=(Get-Item -LiteralPath $usbdkExe).Length;planOnlyPassed=$true;physicalCaptureTested=$false;helperLoadedDuringPlan=$false}
    $record|ConvertTo-Json -Depth 5|Set-Content -LiteralPath (Join-Path $build "native-build-$Configuration.json") -Encoding utf8
} finally {Stop-Transcript|Out-Null}
