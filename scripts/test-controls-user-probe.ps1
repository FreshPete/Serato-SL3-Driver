#requires -Version 7.5
param([switch]$Run,[ValidateRange(20,60)][int]$TraceSeconds=60,[string]$ContextDirectory='tests/results/local/user-controls-01',
      [ValidateSet('Controls','Scope','BrokerScope','InputRecord')][string]$Scenario='Controls',
      [ValidateSet(0,44100,48000)][int]$ExpectedRate=0)
# Normal-token ownership/getter diagnostic. The separate administrator owns tracing.
$ErrorActionPreference='Stop';$root=Split-Path -Parent $PSScriptRoot
$scopeProbe=($Scenario -eq 'Scope');$brokerScope=($Scenario -eq 'BrokerScope');$inputRecord=($Scenario -eq 'InputRecord');$metadataProbe=($scopeProbe -or $brokerScope);$boundedProbe=($metadataProbe -or $inputRecord)
if($inputRecord -and $ExpectedRate -eq 0){throw 'Input recording requires an explicit expected rate'}
if(-not $inputRecord -and $ExpectedRate -ne 0){throw 'Expected rate belongs only to input recording'}
if($boundedProbe -and $TraceSeconds -ne 60){throw 'Metadata scenario requires a sixty-second trace window'}
$probeDeadline=if($boundedProbe){30000}else{40000}
if($ContextDirectory -match '["\r\n]'){throw 'Invalid context path'}
if(-not [IO.Path]::IsPathRooted($ContextDirectory)){$ContextDirectory=Join-Path $root $ContextDirectory}
$ContextDirectory=[IO.Path]::GetFullPath($ContextDirectory)
if($ContextDirectory.StartsWith('\\')){throw 'Local context directory required'}
if(-not $Run){[ordered]@{planOnly=$true;deviceAccess=$false;role='non-elevated read-only probe';scenario=$Scenario;contextDirectory=$ContextDirectory
    collectorWaitSeconds=90;probeDeadlineSeconds=($probeDeadline/1000);traceSeconds=$TraceSeconds;redirectsRequested=1;getters=$(if($inputRecord){@('one rate 0x30 read in single-open startup')}elseif($brokerScope){@('seven rate 0x30 reads across one acquisition and three clients')}elseif($scopeProbe){@('three rate 0x30 reads')}else{@('rate 0x30','audio controls 0x32')})
    audioStartAttempts=$(if($inputRecord){1}else{0});expectedRate=$ExpectedRate;outputPayload=$(if($inputRecord){'zero PCM only'}else{'no audio'});controlSetters=0;rateChanges=0;automaticRetry=$false;selfElevates=$false;securityChanges=$false}|ConvertTo-Json;return}
if(Test-Path -LiteralPath (Join-Path $ContextDirectory 'run.json')){throw 'Choose a fresh context; never retry a saved run'}
Import-Module (Join-Path $PSScriptRoot 'inspect-process.psm1')
$parent=Get-Sl3ProcessEvidence -ProcessId $PID -WithToken
$parentCheckedUtc=[datetime]::UtcNow.ToString('o')
if($parent.elevated -ne $false){throw 'Run this role from a normal, non-elevated terminal'}
$buildPath=Join-Path $root 'artifacts/build/native/native-build-Release.json'
$build=Get-Content -LiteralPath $buildPath -Raw|ConvertFrom-Json
$probe=Join-Path $root $(if($inputRecord){'artifacts/build/native/Release/sl3_input_record_probe.exe'}elseif($brokerScope){'artifacts/build/native/Release/sl3_broker_scope_probe.exe'}elseif($scopeProbe){'artifacts/build/native/Release/sl3_scope_probe.exe'}else{'artifacts/build/native/Release/sl3_host_probe.exe'})
$worker=Join-Path $root 'artifacts/build/native/Release/sl3_usbdk.exe'
$helper=Join-Path $root 'artifacts/extracted/usbdk-msi/UsbDkHelper.dll10'
$python=Join-Path $root '.venv/Scripts/python.exe'
$validator=Join-Path $PSScriptRoot 'validate-controls-user-probe.py'
$baseValidator=Join-Path $PSScriptRoot $(if($inputRecord){'validate-input-record-probe.py'}elseif($brokerScope){'validate-broker-scope-probe.py'}elseif($scopeProbe){'validate-scope-host-probe.py'}else{'validate-controls-host-probe.py'})
$tested=if($inputRecord){$build.inputRecordProbe}elseif($brokerScope){$build.brokerScopeProbe}elseif($scopeProbe){$build.scopeProbe}else{$build.hostProbe.controls}
$probeHash=if($inputRecord){$build.inputRecordProbe.executableSha256}elseif($brokerScope){$build.brokerScopeProbe.executableSha256}elseif($scopeProbe){$build.scopeProbe.executableSha256}else{$build.hostProbe.executableSha256}
$passed=if($inputRecord){$tested.planAndSimulatedRecordingPassed -and $tested.tracedRunnerPrepared -and -not $tested.physicalNativeRun}elseif($brokerScope){$tested.planAndSimulatedLifecyclePassed -and -not $tested.physicalNativeRun}elseif($scopeProbe){$tested.planAndSimulatedLifecyclePassed -and -not $tested.physicalScopeTested}else{$tested.simulatedLifecyclePassed -and -not $tested.nativeQueryRunDuringBuild}
if(-not $passed -or
   (Get-FileHash -LiteralPath $probe).Hash -ne $probeHash -or
   (Get-FileHash -LiteralPath $worker).Hash -ne $build.usbdk.executableSha256){throw 'Probe/worker differs from tested build'}
$pins=$tested.scriptInputs.PSObject.Properties
$pinCount=if($boundedProbe){19}else{18}
if(@($pins).Count -ne $pinCount){throw 'Expected all reviewed split-role dependencies'}
foreach($pin in $pins){if((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $pin.Name)).Hash -ne $pin.Value){throw "Reviewed dependency changed: $($pin.Name)"}}
$plan=& $probe --plan|ConvertFrom-Json
if($LASTEXITCODE -ne 0 -or $plan.simulated){throw 'Unexpected probe kind'}
if($inputRecord){if(-not $plan.planOnly -or $plan.deviceAccess -or $plan.nominalInputMilliseconds -ne 3000 -or $plan.maximumCollectionMilliseconds -ne 6000 -or $plan.audioOutputPayload -cne 'zero PCM only' -or -not $plan.oneAcquisitionRequested -or -not $plan.expectedRateRequired -or $plan.timingProfileWritten){throw 'Unexpected input recording contract'}}
elseif($brokerScope){if(-not $plan.planOnly -or $plan.deviceAccess -or $plan.clients -ne 3 -or $plan.acquisitions -ne 1 -or $plan.audioAllowed -or $plan.requiresTimingProfile -or $plan.watchdogMs -ne 20000){throw 'Unexpected broker scope contract'}}
elseif($scopeProbe){if(-not $plan.plan_only -or $plan.facade_objects -ne 3 -or $plan.acquisitions -ne 1 -or $plan.clock_reads -ne 3 -or $plan.audio_starts -ne 0 -or $plan.rate_setters -ne 0 -or $plan.requires_timing_profile){throw 'Unexpected scope probe contract'}}
elseif($plan.device_access -or $plan.controls_inspection.audio -or $plan.controls_inspection.mode -ne '--controls'){throw 'Unexpected probe contract'}
function Read-Json([string]$Name){Get-Content -LiteralPath (Join-Path $ContextDirectory $Name) -Raw|ConvertFrom-Json -DateKind String}
function Save-Run{$record|ConvertTo-Json -Depth 14|Set-Content -LiteralPath (Join-Path $ContextDirectory 'run.json')}
function Contract($State){
    [ordered]@{secureBoot=$State.secureBoot;deviceGuard=$State.deviceGuard;hvciRegistry=$State.hvciRegistry
        devices=@($State.devices|Sort-Object {$_.device.InstanceId}|ForEach-Object {
            [ordered]@{device=$_.device;properties=@($_.properties|Sort-Object KeyName)}})
        asio=$State.asio;application=$State.application}|ConvertTo-Json -Depth 12 -Compress
}
function Quoted([string]$Value){'"'+$Value+'"'}
function Child([string]$File,[string[]]$Arguments,[string]$Name){
    Start-Process -FilePath $File -ArgumentList $Arguments -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $ContextDirectory "$Name-output.txt") -RedirectStandardError (Join-Path $ContextDirectory "$Name-error.txt")
}
function Worker-Pid{
    $path=Join-Path $ContextDirectory $(if($brokerScope){'probe/worker-startup.tsv'}else{'probe/worker-1.tsv'})
    if(-not (Test-Path -LiteralPath $path)){return $null}
    $stream=[IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
    try{
        if($stream.Length -gt 65536){throw 'Oversized startup journal'}
        $bytes=[byte[]]::new([int]$stream.Length);$count=$stream.Read($bytes,0,$bytes.Length)
        $text=[Text.Encoding]::ASCII.GetString($bytes,0,$count)
        if($text -match '\A[0-9]+\t([1-9][0-9]*)\tworker\.enter\r?\n'){return [uint32]$Matches[1]}
        return $null
    }finally{$stream.Dispose()}
}
# Start this role first, then the administrator collector with the same fresh path.
$deadline=[datetime]::UtcNow.AddSeconds(90);$trace=$null
while([datetime]::UtcNow -lt $deadline){
    try{$trace=Read-Json 'trace/capture.json'}catch{$trace=$null}
    if($trace -and $trace.status -eq 'recording'){break}
    if($trace -and $trace.status -in @('failed','window completed','cleanup requires attention')){throw 'Collector is no longer admitting a test'}
    Start-Sleep -Milliseconds 100
}
if(-not $trace -or $trace.status -ne 'recording'){throw 'Collector did not become ready; no device test launched'}
$context=Read-Json 'context.json'
if($trace.plan.durationSeconds -ne $TraceSeconds){throw 'Collector duration differs from the requested probe plan; no device test launched'}
$observed=Get-Sl3ProcessEvidence -ProcessId $trace.collectorPid
$checkedUtc=[datetime]::UtcNow.ToString('o')
$trace|ConvertTo-Json -Depth 12|Set-Content -LiteralPath (Join-Path $ContextDirectory 'admitted-trace.json')
$context|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $ContextDirectory 'admitted-context.json')
@{process=$observed;checkedUtc=$checkedUtc}|ConvertTo-Json -Depth 5|Set-Content -LiteralPath (Join-Path $ContextDirectory 'collector-process.json')
$admission=& $python $validator --admission $ContextDirectory
if($LASTEXITCODE -ne 0 -or ($admission|ConvertFrom-Json).valid -ne $true){throw "No device launch: $admission"}
# The verifier can take seconds on a cold start. Reobserve the live collector
# after it returns instead of treating verifier time as a fresh observation.
$launchTrace=Read-Json 'trace/capture.json'
$launchProcess=Get-Sl3ProcessEvidence -ProcessId $launchTrace.collectorPid
$launchCheckedUtc=[datetime]::UtcNow.ToString('o')
if($launchTrace.status -ne 'recording' -or $launchTrace.session -ne $trace.session -or
   $launchTrace.producerSha256 -ne $trace.producerSha256 -or $launchTrace.startedUtc -ne $trace.startedUtc -or
   $launchProcess.pid -ne $observed.pid -or $launchProcess.creationFileTimeUtc -ne $observed.creationFileTimeUtc -or
   $launchProcess.imagePath -ine $observed.imagePath -or $launchProcess.alive -ne $true -or
   $launchTrace.collectorCreationFileTimeUtc -ne $launchProcess.creationFileTimeUtc -or
   $launchTrace.collectorImagePath -ine $launchProcess.imagePath -or
   $launchTrace.plan.durationSeconds -ne $TraceSeconds -or
   ([datetime]$launchCheckedUtc-[datetime]$launchTrace.startedUtc).TotalSeconds -lt 0 -or
   ([datetime]$launchCheckedUtc-[datetime]$launchTrace.startedUtc).TotalSeconds -gt [Math]::Min(10,$TraceSeconds-15)){
    throw 'Collector changed or launch window expired during verification; no device test launched'
}
@{trace=$launchTrace;process=$launchProcess;checkedUtc=$launchCheckedUtc}|ConvertTo-Json -Depth 12|
    Set-Content -LiteralPath (Join-Path $ContextDirectory 'launch-admission.json')
$record=[ordered]@{schema=$(if($inputRecord){'sl3.input-record.traced-run.v1'}elseif($brokerScope){'sl3.broker-scope.traced-run.v1'}elseif($scopeProbe){'sl3.scope-host.traced-run.v1'}else{'sl3.controls-host.traced-run.v1'});splitUserContext=$true;startedUtc=[datetime]::UtcNow.ToString('o');completed=$false;error=$null
    workerSha256=$build.usbdk.executableSha256;probeSha256=$probeHash;probeExitCode=$null;traceExitCode=$null
    traceCleanupConfirmed=$false;secureBootBefore=$true;secureBootAfter=$false;recoveryConfirmed=$false
    withUsbDkLifecycle=$true;withUsbIdentity=$false;driverChanges=$false;securityChanges=$false;asioRegistration=$false;automaticRetry=$false;traceSeconds=$TraceSeconds
    buildManifestSha256=(Get-FileHash -LiteralPath $buildPath).Hash;runnerInputs=$tested.scriptInputs
    parentImagePath=$parent.imagePath;probeImagePath=$probe;workerImagePath=$worker
    userProcesses=[ordered]@{parent=@{process=$parent;checkedUtc=$parentCheckedUtc}}}
if($boundedProbe){$record.scenario=$Scenario}
if($inputRecord){$record.expectedRateHz=$ExpectedRate}
$record.launchAdmissionSha256=(Get-FileHash -LiteralPath (Join-Path $ContextDirectory 'launch-admission.json')).Hash
foreach($pair in @(@('admitted-trace.json','admittedTraceSha256'),@('admitted-context.json','admittedContextSha256'),@('collector-process.json','collectorProcessSha256'))){
    $record[$pair[1]]=(Get-FileHash -LiteralPath (Join-Path $ContextDirectory $pair[0])).Hash
}
$child=$null;Save-Run
try{
    if(([datetime]::UtcNow-[datetime]$launchCheckedUtc).TotalSeconds -gt 2){throw 'Collector launch observation expired before launch'}
    $record.probeStartedUtc=[datetime]::UtcNow.ToString('o');Save-Run
    $probeMode=if($boundedProbe){'--run'}else{'--controls'}
    $probeArguments=@($probeMode,'--worker',(Quoted $worker),'--worker-sha256',$record.workerSha256.ToLowerInvariant(),
        '--helper',(Quoted $helper),'--output',(Quoted (Join-Path $ContextDirectory 'probe')))
    if($inputRecord){$probeArguments+=@('--expected-rate',[string]$ExpectedRate)}
    $child=Child $probe $probeArguments 'probe'
    $record.probePid=$child.Id
    try{$record.userProcesses.probe=@{process=(Get-Sl3ProcessEvidence -ProcessId $child.Id -WithToken);checkedUtc=[datetime]::UtcNow.ToString('o')}}
    catch{$record.tokenQueryError=$_.Exception.Message}
    $limit=[Diagnostics.Stopwatch]::StartNew();$workerAttempted=$false
    while(-not $child.HasExited -and $limit.ElapsedMilliseconds -lt $probeDeadline){
        if(-not $workerAttempted){
            $workerPid=Worker-Pid
            if($workerPid){
                $workerAttempted=$true
                try{$record.userProcesses.worker=@{process=(Get-Sl3ProcessEvidence -ProcessId $workerPid -WithToken);checkedUtc=[datetime]::UtcNow.ToString('o')}}
                catch{$record.tokenQueryError=$_.Exception.Message}
                Save-Run
            }
        }
        Start-Sleep -Milliseconds 20
    }
    if(-not $child.HasExited){
        $record.probeTimedOut=$true;$child.Kill($true);$record.probeRetiredAfterKill=$child.WaitForExit(5000)
        throw 'Probe exceeded its deadline; preserve evidence and inspect recovery before another attempt'
    }
    $child.WaitForExit();$record.probeExitCode=$child.ExitCode
    $record.probeCompletedUtc=[datetime]::UtcNow.ToString('o')
    if($child.ExitCode -ne 0){throw 'Controls probe failed; do not retry'}
    $sampleArguments=if($boundedProbe){@((Join-Path $ContextDirectory 'probe'),'--worker-sha256',$record.workerSha256.ToLowerInvariant())}else{@('--probe',(Join-Path $ContextDirectory 'probe'),'--worker-sha256',$record.workerSha256)}
    $sample=& $python $baseValidator @sampleArguments
    $sample|Set-Content -LiteralPath (Join-Path $ContextDirectory 'probe-validation.json')
    if($LASTEXITCODE -ne 0 -or ($sample|ConvertFrom-Json).valid -ne $true){throw 'Native sample/ownership validation failed'}
    $record.probeRecordSha256=(Get-FileHash -LiteralPath (Join-Path $ContextDirectory $(if($brokerScope -or $inputRecord){'probe/result.json'}else{'probe/probe.json'}))).Hash
    $record.probeValidationSha256=(Get-FileHash -LiteralPath (Join-Path $ContextDirectory 'probe-validation.json')).Hash
    if($record.tokenQueryError -or -not $record.userProcesses.worker){throw 'Token evidence incomplete; native sample retained separately'}
}catch{$record.error=$_.Exception.Message}
finally{
    if($child -and -not $child.HasExited){
        try{$record.probeContainmentRequested=$true;$child.Kill($true);$record.probeRetiredAfterKill=$child.WaitForExit(5000)}
        catch{$record.probeContainmentError=$_.Exception.Message}
    }
    # Never stop/kill the separate elevated collector. It owns its bounded trace.
    try{
        $end=[datetime]::UtcNow.AddSeconds(90)
        do{
            $context=Read-Json 'context.json'
            if($context.completedUtc){break}
            Start-Sleep -Milliseconds 200
        }while([datetime]::UtcNow -lt $end)
        if(-not $context.completed -or $context.error){throw 'Administrator collector did not complete cleanly'}
        $record.contextSha256=(Get-FileHash -LiteralPath (Join-Path $ContextDirectory 'context.json')).Hash
        foreach($key in @('beforeStateSha256','afterStateSha256','traceRecordSha256')){$record[$key]=$context.$key}
        $after=Read-Json 'after-state.json';$record.secureBootAfter=($after.secureBoot -eq $true)
        $trace=Read-Json 'trace/capture.json'
        $record.traceExitCode=0
        $record.traceCleanupConfirmed=(@($trace.commands|Where-Object {($_.arguments -join ' ') -eq "delete -n $($trace.session)" -and $_.exitCode -eq 0}).Count -eq 1)
        $etls=@(Get-ChildItem -LiteralPath (Join-Path $ContextDirectory 'trace') -Filter '*.etl')
        if($etls.Count -ne 1 -or -not $record.traceCleanupConfirmed){throw 'Expected one ETL and successful collector cleanup'}
        $record.etlSha256=(Get-FileHash -LiteralPath $etls[0].FullName).Hash
        $decode=Child 'tracerpt.exe' @((Quoted $etls[0].FullName),'-o',(Quoted (Join-Path $ContextDirectory 'events.xml')),'-of','XML','-y') 'decode'
        if(-not $decode.WaitForExit(60000)){$decode.Kill($true);$null=$decode.WaitForExit(5000);throw 'Trace decoder timed out'}
        if($decode.ExitCode -ne 0){throw 'Trace decoding failed'}
        $stats=& $python (Join-Path $PSScriptRoot 'validate-usbdk-capture.py') --trace-xml (Join-Path $ContextDirectory 'events.xml')
        if($LASTEXITCODE -ne 0){throw 'Trace statistics unavailable'}
        $record.traceStats=$stats|ConvertFrom-Json
        $before=Read-Json 'before-state.json'
        $record.recoveryConfirmed=((Contract $before) -ceq (Contract $after))
        if(-not $record.secureBootAfter -or -not $record.recoveryConfirmed){throw 'Selected security/device recovery differs'}
    }catch{if(-not $record.error){$record.error=$_.Exception.Message}}
    $record.completed=($null -eq $record.error);$record.completedUtc=[datetime]::UtcNow.ToString('o');Save-Run
}
if($record.error){throw $record.error}
$finalArguments=@('--run',$ContextDirectory,'--worker-sha256',$record.workerSha256,'--probe-sha256',$record.probeSha256)
if($inputRecord){$finalArguments+='--input-record'}elseif($brokerScope){$finalArguments+='--broker-scope'}elseif($scopeProbe){$finalArguments+='--scope'}
$result=& $python $validator @finalArguments
$result|Set-Content -LiteralPath (Join-Path $ContextDirectory 'run-validation.json')
if($LASTEXITCODE -ne 0 -or ($result|ConvertFrom-Json).valid -ne $true){
    $record.completed=$false;$record.error='Final normal-token/trace/recovery validation failed';$record.recoveryConfirmed=$false;Save-Run;throw $record.error
}
$result
