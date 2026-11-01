#requires -Version 7.5
param([switch]$Run,[string]$ContextDirectory='tests/results/local/user-rate-01',[string]$TargetHz='',[string]$ExpectedInitialHz='')
# One normal-token held-rate diagnostic; a separate administrator owns tracing.
$ErrorActionPreference='Stop';$root=Split-Path -Parent $PSScriptRoot
if($ContextDirectory -match '["\r\n]'){throw 'Invalid context path'}
if(-not [IO.Path]::IsPathRooted($ContextDirectory)){$ContextDirectory=Join-Path $root $ContextDirectory}
$ContextDirectory=[IO.Path]::GetFullPath($ContextDirectory)
if($ContextDirectory.StartsWith('\\')){throw 'Local context directory required'}
foreach($value in @($TargetHz,$ExpectedInitialHz)){
    if($value -and $value -cnotmatch '^(44100|48000)$'){throw 'Use a canonical 44100 or 48000 clock value'}
}
if(-not $Run){[ordered]@{planOnly=$true;deviceAccess=$false;role='non-elevated single-target held-rate probe';targetHz=$TargetHz;expectedInitialHz=$ExpectedInitialHz;contextDirectory=$ContextDirectory
    collectorWaitSeconds=90;probeDeadlineSeconds=30;traceSeconds=60;redirectsRequested=1;maximumRateSetters=1;audioStartAttempts=0
    controlSetters=0;automaticRetry=$false;automaticRollback=$false;rateRestorationVerified=$false;selfElevates=$false;securityChanges=$false}|ConvertTo-Json;return}
if(-not $TargetHz -or -not $ExpectedInitialHz){throw 'Explicit target and reviewed initial clock required'}
if((Test-Path -LiteralPath (Join-Path $ContextDirectory 'intent.json')) -or (Test-Path -LiteralPath (Join-Path $ContextDirectory 'run.json'))){throw 'Choose a fresh context; never retry a saved run'}
Import-Module (Join-Path $PSScriptRoot 'inspect-process.psm1')
$parent=Get-Sl3ProcessEvidence -ProcessId $PID -WithToken
$parentCheckedUtc=[datetime]::UtcNow.ToString('o')
if($parent.elevated -ne $false){throw 'Run this role from a normal, non-elevated terminal'}
$buildPath=Join-Path $root 'artifacts/build/native/native-build-Release.json'
$build=Get-Content -LiteralPath $buildPath -Raw|ConvertFrom-Json
$probe=Join-Path $root 'artifacts/build/native/Release/sl3_host_probe.exe'
$worker=Join-Path $root 'artifacts/build/native/Release/sl3_usbdk.exe'
$helper=Join-Path $root 'artifacts/extracted/usbdk-msi/UsbDkHelper.dll10'
$python=Join-Path $root '.venv/Scripts/python.exe'
$validator=Join-Path $PSScriptRoot 'validate-rate-user-probe.py'
$baseValidator=Join-Path $PSScriptRoot 'validate-rate-host-probe.py'
if(-not $build.hostProbe.rateSelection.testsPassed -or $build.hostProbe.rateSelection.physicalRateChangeTested -or
   (Get-FileHash -LiteralPath $probe).Hash -ne $build.hostProbe.executableSha256 -or
   (Get-FileHash -LiteralPath $worker).Hash -ne $build.usbdk.executableSha256){throw 'Rate probe/worker differs from tested build'}
$pins=$build.hostProbe.rateSelection.traceScriptInputs.PSObject.Properties
if(@($pins).Count -ne 23 -or -not $build.hostProbe.rateSelection.traceRunnerPrepared){throw 'Expected all reviewed rate trace dependencies'}
foreach($pin in $pins){if((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $pin.Name)).Hash -ne $pin.Value){throw "Reviewed dependency changed: $($pin.Name)"}}
$intentText=& $python $validator --intent --target $TargetHz --expected-initial $ExpectedInitialHz --worker-sha256 $build.usbdk.executableSha256 --probe-sha256 $build.hostProbe.executableSha256
if($LASTEXITCODE -ne 0 -or ($intentText|ConvertFrom-Json).valid -ne $true){throw "No device launch: $intentText"}
$prerequisite=$intentText|ConvertFrom-Json -DateKind String
function Read-Json([string]$Name){Get-Content -LiteralPath (Join-Path $ContextDirectory $Name) -Raw|ConvertFrom-Json -DateKind String}
function Save-Run{$record|ConvertTo-Json -Depth 14|Set-Content -LiteralPath (Join-Path $ContextDirectory 'run.json')}
function Preserve-ProbeFiles{
    foreach($pair in @(@('probe/request.json','requestRecordSha256'),@('probe/probe.json','probeRecordSha256'),@('probe/worker-1.tsv.rate/rate.json','nativeRateRecordSha256'))){
        try{
            $saved=Join-Path $ContextDirectory $pair[0]
            if(Test-Path -LiteralPath $saved){$record[$pair[1]]=(Get-FileHash -LiteralPath $saved).Hash}
        }catch{
            $record.evidencePreservationError=$_.Exception.Message
            if(-not $record.error){$record.error=$_.Exception.Message}
        }
    }
}
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
    $path=Join-Path $ContextDirectory 'probe/worker-1.tsv'
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
# Immutable intent is saved after the fresh collector creates the directory, before admission/launch.
$intentPath=Join-Path $ContextDirectory 'intent.json'
$intentStream=[IO.File]::Open($intentPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
try{$intentBytes=[Text.Encoding]::UTF8.GetBytes(($prerequisite|ConvertTo-Json -Depth 14));$intentStream.Write($intentBytes);$intentStream.Flush($true)}finally{$intentStream.Dispose()}
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
   $launchTrace.plan.durationSeconds -ne 60 -or
   ([datetime]$launchCheckedUtc-[datetime]$launchTrace.startedUtc).TotalSeconds -lt 0 -or
   ([datetime]$launchCheckedUtc-[datetime]$launchTrace.startedUtc).TotalSeconds -gt [Math]::Min(10,60-15)){
    throw 'Collector changed or launch window expired during verification; no device test launched'
}
@{trace=$launchTrace;process=$launchProcess;checkedUtc=$launchCheckedUtc}|ConvertTo-Json -Depth 12|
    Set-Content -LiteralPath (Join-Path $ContextDirectory 'launch-admission.json')
$record=[ordered]@{schema='sl3.rate-user.traced-run.v1';splitUserContext=$true;startedUtc=[datetime]::UtcNow.ToString('o');completed=$false;error=$null
    workerSha256=$prerequisite.workerSha256;probeSha256=$prerequisite.probeSha256;targetHz=$prerequisite.targetHz;expectedInitialHz=$prerequisite.expectedInitialHz;intentRecordSha256=(Get-FileHash -LiteralPath $intentPath).Hash;probeExitCode=$null;traceExitCode=$null
    traceCleanupConfirmed=$false;secureBootBefore=$true;secureBootAfter=$false;recoveryConfirmed=$false
    withUsbDkLifecycle=$true;withUsbIdentity=$false;driverChanges=$false;securityChanges=$false;asioRegistration=$false;automaticRetry=$false
    buildManifestSha256=$prerequisite.buildManifestSha256;runnerInputs=$build.hostProbe.rateSelection.traceScriptInputs;traceSeconds=60;rateRestorationVerified=$false
    parentImagePath=$parent.imagePath;probeImagePath=$probe;workerImagePath=$worker
    userProcesses=[ordered]@{parent=@{process=$parent;checkedUtc=$parentCheckedUtc}}}
$record.launchAdmissionSha256=(Get-FileHash -LiteralPath (Join-Path $ContextDirectory 'launch-admission.json')).Hash
foreach($pair in @(@('admitted-trace.json','admittedTraceSha256'),@('admitted-context.json','admittedContextSha256'),@('collector-process.json','collectorProcessSha256'))){
    $record[$pair[1]]=(Get-FileHash -LiteralPath (Join-Path $ContextDirectory $pair[0])).Hash
}
$child=$null;Save-Run
try{
    $admissionAge=([datetime]::UtcNow-[datetime]$launchCheckedUtc).TotalSeconds
    if($admissionAge -lt 0 -or $admissionAge -gt 2){throw 'Collector admission expired before launch'}
    $record.probeStartedUtc=[datetime]::UtcNow.ToString('o');Save-Run
    $child=Child $probe @('--select-rate','--worker',(Quoted $worker),'--worker-sha256',$record.workerSha256,
        '--helper',(Quoted $helper),'--output',(Quoted (Join-Path $ContextDirectory 'probe')),'--target',$TargetHz,'--expected-initial',$ExpectedInitialHz) 'probe'
    $record.probePid=$child.Id
    try{$record.userProcesses.probe=@{process=(Get-Sl3ProcessEvidence -ProcessId $child.Id -WithToken);checkedUtc=[datetime]::UtcNow.ToString('o')}}
    catch{$record.tokenQueryError=$_.Exception.Message}
    $limit=[Diagnostics.Stopwatch]::StartNew();$workerAttempted=$false
    while(-not $child.HasExited -and $limit.ElapsedMilliseconds -lt 30000){
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
    if($child.ExitCode -ne 0){throw 'Rate probe failed; preserve the operation evidence and do not retry'}
    $sample=& $python $baseValidator --probe (Join-Path $ContextDirectory 'probe') --worker-sha256 $record.workerSha256
    $sample|Set-Content -LiteralPath (Join-Path $ContextDirectory 'probe-validation.json')
    if($LASTEXITCODE -ne 0 -or ($sample|ConvertFrom-Json).valid -ne $true){throw 'Native sample/ownership validation failed'}
    $record.probeRecordSha256=(Get-FileHash -LiteralPath (Join-Path $ContextDirectory 'probe/probe.json')).Hash
    $record.requestRecordSha256=(Get-FileHash -LiteralPath (Join-Path $ContextDirectory 'probe/request.json')).Hash
    $record.probeValidationSha256=(Get-FileHash -LiteralPath (Join-Path $ContextDirectory 'probe-validation.json')).Hash
    if($record.tokenQueryError -or -not $record.userProcesses.worker){throw 'Token evidence incomplete; native sample retained separately'}
}catch{$record.error=$_.Exception.Message}
finally{
    if($child -and -not $child.HasExited){
        try{$record.probeContainmentRequested=$true;$child.Kill($true);$record.probeRetiredAfterKill=$child.WaitForExit(5000)}
        catch{$record.probeContainmentError=$_.Exception.Message}
    }
    # Preserve whatever the probe saved even when operation/cleanup validation fails.
    if($child -and $child.HasExited){
        if(-not $record.probeCompletedUtc){$record.probeCompletedUtc=[datetime]::UtcNow.ToString('o')}
        $record.probeExitCode=$child.ExitCode
    }
    Preserve-ProbeFiles
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
    }catch{$record.recoveryError=$_.Exception.Message;if(-not $record.error){$record.error=$_.Exception.Message}}
    $record.completed=($null -eq $record.error);$record.completedUtc=[datetime]::UtcNow.ToString('o');Save-Run
}
if($record.error){throw $record.error}
$result=& $python $validator --run $ContextDirectory --worker-sha256 $record.workerSha256 --probe-sha256 $record.probeSha256
$result|Set-Content -LiteralPath (Join-Path $ContextDirectory 'run-validation.json')
if($LASTEXITCODE -ne 0 -or ($result|ConvertFrom-Json).valid -ne $true){
    $record.completed=$false;$record.error='Final normal-token/trace/recovery validation failed';Save-Run;throw $record.error
}
$result
