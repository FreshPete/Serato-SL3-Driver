#requires -Version 7.5
param([switch]$Run,[switch]$InspectOnly,[ValidateSet(0,44100,48000)][int]$SingleOpenRate=0,[ValidateSet(8,64)][int]$BlockIntervals=64,[string]$ResultDirectory='tests/results/local/host-probe-traced-01',
      [string]$ValidatedCaptureRun,[string]$ValidatedDuplexRun)
# Explicit one-second zero-output bridge probe. No installation or registration.
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
function Full-Path([string]$Value){
    if($Value -match '["\r\n]'){throw 'Invalid path'}
    if(-not [IO.Path]::IsPathRooted($Value)){$Value=Join-Path $root $Value}
    [IO.Path]::GetFullPath($Value)
}
function Quoted([string]$Value){'"'+$Value+'"'}
$ResultDirectory=Full-Path $ResultDirectory
if($InspectOnly -and $SingleOpenRate){throw 'Inspection-only and single-open streaming are separate modes'}
if($BlockIntervals -ne 64 -and -not $SingleOpenRate){throw 'Eight-interval blocks require single-open streaming'}
if($InspectOnly -and ($ValidatedCaptureRun -or $ValidatedDuplexRun)){throw 'Inspection-only mode does not use prior audio evidence arguments'}
if(Test-Path -LiteralPath $ResultDirectory){throw 'Choose a fresh evidence directory'}
if(-not $Run){
    [ordered]@{planOnly=$true;inspectionOnly=[bool]$InspectOnly;singleOpenExpectedRateHz=$SingleOpenRate;streamMilliseconds=if($InspectOnly){0}else{1000};bankFrames=128;intervals=$BlockIntervals;outputPayload=if($InspectOnly){'no audio submitted'}else{'zero PCM only'}
        prerequisites=@('Owner present; elevated PowerShell; Secure Boot enabled; reviewed UsbDk running',
            $(if($InspectOnly){'Current tested Release probe/worker; exactly two clock inspections, no audio prerequisites'}else{'Current Release probe/worker builds; same-worker validated capture and silent duplex'}))
        resultDirectory=$ResultDirectory;deviceAccess=$false;driverChanges=$false;asioRegistration=$false
        latencyProfileCreated=$false}|ConvertTo-Json -Depth 5
    return
}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
if(-not ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'An elevated terminal is required'}
if(-not (Confirm-SecureBootUEFI)){throw 'Secure Boot must remain enabled'}
if(-not $InspectOnly -and (-not $ValidatedCaptureRun -or -not $ValidatedDuplexRun)){throw 'Capture and silent-duplex evidence are required'}
if(@(Get-CimInstance Win32_Process -Filter "Name='sl3_usbdk.exe' OR Name='sl3_host_probe.exe'").Count){throw 'A prior native test process remains; do not reopen the device'}
if(-not $InspectOnly){$ValidatedCaptureRun=Full-Path $ValidatedCaptureRun;$ValidatedDuplexRun=Full-Path $ValidatedDuplexRun}
$preflight=& (Join-Path $PSScriptRoot 'preflight-usbdk.ps1')|ConvertFrom-Json
if(@($preflight.installedDriver|Where-Object State -eq 'Running').Count -ne 1){throw 'Reviewed UsbDk must be running'}
$build=Get-Content -LiteralPath (Join-Path $root 'artifacts/build/native/native-build-Release.json') -Raw|ConvertFrom-Json
$probe=Join-Path $root 'artifacts/build/native/Release/sl3_host_probe.exe'
$worker=Join-Path $root 'artifacts/build/native/Release/sl3_usbdk.exe'
$helper=Join-Path $root 'artifacts/extracted/usbdk-msi/UsbDkHelper.dll10'
if(-not $build.hostProbe.planAndSimulatedLifecyclePassed -or
    (Get-FileHash -LiteralPath $probe).Hash -ne $build.hostProbe.executableSha256){throw 'Probe is not the reviewed tested build'}
$python=Join-Path $root '.venv/Scripts/python.exe'
if(-not $InspectOnly){
$validation=& $python (Join-Path $PSScriptRoot 'validate-usbdk-capture.py') $ValidatedCaptureRun --expected-native-sha256 $preflight.nativeSha256
if($LASTEXITCODE -ne 0 -or ($validation|ConvertFrom-Json).valid -ne $true){throw 'Prior capture failed consistency checks'}
$duplexRun=Get-Content -LiteralPath (Join-Path $ValidatedDuplexRun 'run.json') -Raw|ConvertFrom-Json
$duplexPath=Join-Path $ValidatedDuplexRun 'duplex/duplex.json'
$duplex=Get-Content -LiteralPath $duplexPath -Raw|ConvertFrom-Json
if($duplexRun.mode -ne 'DuplexSilence' -or -not $duplexRun.completed -or -not $duplexRun.recoveryConfirmed -or
    -not $duplexRun.secureBootAfter -or $duplexRun.nativeSha256 -ne $preflight.nativeSha256 -or
    (Get-FileHash -LiteralPath $duplexPath).Hash -ne $duplexRun.nativeRecordSha256 -or
    -not $duplex.duplex_succeeded -or -not $duplex.transfers_succeeded -or -not $duplex.buffer_cleanup_complete -or
    -not $duplex.redirect_and_alternates_cleanup_succeeded -or $duplex.output_payload -ne 'zero PCM only'){throw 'Prior silent-duplex gate failed'}
}
$plan=& $probe --plan|ConvertFrom-Json
if($LASTEXITCODE -ne 0 -or -not $plan.plan_only -or $plan.simulated -or $plan.device_access){throw 'Expected a native plan-only probe'}
New-Item -ItemType Directory -Path $ResultDirectory|Out-Null
$preflight|ConvertTo-Json -Depth 10|Set-Content -LiteralPath (Join-Path $ResultDirectory 'preflight.json')
$record=[ordered]@{schema='sl3.host-probe.traced-run.v1';startedUtc=[datetime]::UtcNow.ToString('o')
    completed=$false;error=$null;probeExitCode=$null;traceExitCode=$null;traceCleanupConfirmed=$false;secureBootBefore=$true;secureBootAfter=$false
    workerSha256=$preflight.nativeSha256;probeSha256=(Get-FileHash -LiteralPath $probe).Hash
    inspectionOnly=[bool]$InspectOnly
    singleOpenExpectedRateHz=$SingleOpenRate
    blockIntervals=$BlockIntervals
    priorCaptureRunSha256=if($InspectOnly){$null}else{(Get-FileHash -LiteralPath (Join-Path $ValidatedCaptureRun 'run.json')).Hash}
    priorDuplexRunSha256=if($InspectOnly){$null}else{(Get-FileHash -LiteralPath (Join-Path $ValidatedDuplexRun 'run.json')).Hash}
    driverChanges=$false;asioRegistration=$false;latencyMeasured=$false}
$record.runnerInputs=[ordered]@{}
foreach($name in @('test-host-probe-traced.ps1','read-startup-journal.ps1','capture-usb-startup.ps1','preflight-usbdk.ps1','collect-windows-state.ps1')){
    $record.runnerInputs[$name]=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name)).Hash
}
function Save-Run{$record|ConvertTo-Json -Depth 12|Set-Content -LiteralPath (Join-Path $ResultDirectory 'run.json')}
function Child([string]$File,[string[]]$Arguments,[string]$Name){
    Start-Process -FilePath $File -ArgumentList $Arguments -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $ResultDirectory "$Name-output.txt") -RedirectStandardError (Join-Path $ResultDirectory "$Name-error.txt")
}
function Trace-Record{
    try{Get-Content -LiteralPath (Join-Path $ResultDirectory 'trace/capture.json') -Raw|ConvertFrom-Json -DateKind String}catch{$null}
}
function Contract($State){
    [ordered]@{secureBoot=$State.secureBoot;deviceGuard=$State.deviceGuard;hvciRegistry=$State.hvciRegistry
        devices=@($State.devices|Sort-Object {$_.device.InstanceId}|ForEach-Object {
            [ordered]@{device=$_.device;properties=@($_.properties|Sort-Object KeyName)}})
        asio=$State.asio;application=$State.application}|ConvertTo-Json -Depth 12 -Compress
}
$traceProcess=$null;Save-Run
try{
    & (Join-Path $PSScriptRoot 'collect-windows-state.ps1') -Output (Join-Path $ResultDirectory 'before-state.json')|Out-Null
    $before=Get-Content -LiteralPath (Join-Path $ResultDirectory 'before-state.json') -Raw|ConvertFrom-Json
    if(@($before.devices).Count -ne 1 -or $before.secureBoot -ne $true){throw 'One SL3 and enabled Secure Boot required'}
    $traceProcess=Child (Get-Process -Id $PID).Path @('-NoProfile','-File',(Quoted (Join-Path $PSScriptRoot 'capture-usb-startup.ps1')),
        '-Capture','-DurationSeconds','60','-OutputDirectory',(Quoted (Join-Path $ResultDirectory 'trace'))) 'trace'
    $ready=$false
    for($i=0;$i -lt 100;$i++){
        if($traceProcess.HasExited){throw 'Trace exited before readiness'}
        $trace=Trace-Record
        if($trace.status -eq 'recording'){$ready=$true;break}
        Start-Sleep -Milliseconds 200
    }
    if(-not $ready -or ([datetime]::UtcNow-[datetime]$trace.startedUtc).TotalSeconds -gt 10){throw 'Trace is not ready with enough remaining time'}
    $null=& logman.exe query $trace.session -ets 2>&1
    if($LASTEXITCODE -ne 0){throw 'Trace is not live'}
    if((Get-FileHash -LiteralPath $probe).Hash -ne $record.probeSha256 -or
       (Get-FileHash -LiteralPath $worker).Hash -ne $record.workerSha256){throw 'Tested executables changed'}
    $record.probeStartedUtc=[datetime]::UtcNow.ToString('o');Save-Run
    $mode=if($InspectOnly){'--inspect-reopen'}elseif($SingleOpenRate){'--single-open-'+$SingleOpenRate}else{'--run'}
    $probeArguments=@($mode,'--worker',(Quoted $worker),'--worker-sha256',$record.workerSha256,
        '--helper',(Quoted $helper),'--output',(Quoted (Join-Path $ResultDirectory 'probe')))
    if($SingleOpenRate){$probeArguments+=@('--intervals',[string]$BlockIntervals)}
    $child=Child $probe $probeArguments 'probe'
    if(-not $child.WaitForExit(40000)){
        $record.probeTimedOut=$true;$child.Kill($true);$record.probeExitedAfterContainment=$child.WaitForExit(5000)
        throw 'Private probe exceeded its deadline; cleanup is unproven'
    }
    $record.probeExitCode=$child.ExitCode;$record.probeCompletedUtc=[datetime]::UtcNow.ToString('o')
    $probeRecord=Join-Path $ResultDirectory 'probe/probe.json'
    $record.probeRecordSha256=(Get-FileHash -LiteralPath $probeRecord).Hash
    $result=Get-Content -LiteralPath $probeRecord -Raw|ConvertFrom-Json
    if($child.ExitCode -ne 0 -or -not $result.successful -or -not $result.finished -or $result.simulated -or
       -not $result.io_retired -or -not $result.device_released -or -not $result.audio_thread_retired -or
       -not $result.worker_exited -or -not $result.private_job_empty -or $result.forced_termination -or
       $result.inspect_only -ne [bool]$InspectOnly){throw 'Native diagnostic failed or did not retire within its deadline'}
    if($InspectOnly){
        if($result.output_payload -ne 'no audio submitted' -or $result.completed_inspections -ne 2 -or
           $result.callbacks -ne 0 -or $result.stream_started -or $result.input_frames -ne 0 -or
           $result.output_submissions -ne 0){throw 'Inspection-only contract mismatch'}
    }elseif($result.output_payload -ne 'zero PCM only'){throw 'Silent-output contract mismatch'}
    if($result.single_open -ne ($SingleOpenRate -ne 0)){throw 'Single-open mode mismatch'}
    if($result.intervals -ne $BlockIntervals){throw 'USB block shape differs from the explicit request'}
    if($SingleOpenRate -and ($result.expected_rate_hz -ne $SingleOpenRate -or $result.reported_rate_hz -ne $SingleOpenRate -or
        $result.completed_inspections -ne 0 -or $result.inspection_succeeded)){throw 'Single-open verified clock contract mismatch'}
}catch{$record.error=$_.Exception.Message}
finally{
    try{
        $record.startupJournals=@(Get-ChildItem -LiteralPath (Join-Path $ResultDirectory 'probe') -Filter 'worker-*.tsv' -File -ErrorAction SilentlyContinue|ForEach-Object {
            & (Join-Path $PSScriptRoot 'read-startup-journal.ps1') -Path $_.FullName|ConvertFrom-Json
        })
    }catch{$record.journalError=$_.Exception.Message;if(-not $record.error){$record.error=$record.journalError}}
    try{
        if($traceProcess){
            if(-not $traceProcess.WaitForExit(75000)){throw 'Trace process did not finish; inspect its owned session'}
            $record.traceExitCode=$traceProcess.ExitCode;$trace=Trace-Record
            if($traceProcess.ExitCode -ne 0 -or $trace.status -ne 'window completed' -or $trace.deleteError){throw 'Trace cleanup failed'}
            $record.traceCleanupConfirmed=$true
            $record.traceStartedUtc=$trace.startedUtc;$record.traceStoppedUtc=$trace.stoppedUtc
            if(-not $record.probeStartedUtc -or -not $record.probeCompletedUtc -or
               [datetimeoffset]$record.probeStartedUtc -lt [datetimeoffset]$trace.startedUtc -or
               [datetimeoffset]$record.probeCompletedUtc -gt [datetimeoffset]$trace.stoppedUtc){throw 'Trace does not cover the complete private probe'}
            $etls=@(Get-ChildItem -LiteralPath (Join-Path $ResultDirectory 'trace') -Filter '*.etl' -File)
            if($etls.Count -ne 1 -or $etls[0].Length -gt 65MB){throw 'Unexpected trace files'}
            $record.etlSha256=(Get-FileHash -LiteralPath $etls[0].FullName).Hash
            $decoder=Child (Join-Path $env:SystemRoot 'System32/tracerpt.exe') @((Quoted $etls[0].FullName),'-o',
                (Quoted (Join-Path $ResultDirectory 'events.xml')),'-of','XML','-y') 'decode'
            if(-not $decoder.WaitForExit(45000)){$decoder.Kill($true);throw 'Trace decoder timed out'}
            if($decoder.ExitCode -ne 0){throw 'Trace decode failed'}
            $stats=& $python (Join-Path $PSScriptRoot 'validate-usbdk-capture.py') --trace-xml (Join-Path $ResultDirectory 'events.xml')
            if($LASTEXITCODE -ne 0){throw 'Trace statistics unavailable'}
            $record.traceStats=$stats|ConvertFrom-Json
            if($record.traceStats.eventsLost -ne 0 -or $record.traceStats.buffersLost -ne 0 -or $record.traceStats.session -ne $trace.session){throw 'Trace is lossy or session differs'}
        }
    }catch{$record.traceError=$_.Exception.Message;if(-not $record.error){$record.error=$record.traceError}}
    try{
        & (Join-Path $PSScriptRoot 'collect-windows-state.ps1') -Output (Join-Path $ResultDirectory 'after-state.json')|Out-Null
        $after=Get-Content -LiteralPath (Join-Path $ResultDirectory 'after-state.json') -Raw|ConvertFrom-Json
        $record.secureBootAfter=$after.secureBoot -eq $true
        $record.recoveryConfirmed=($before -and (Contract $before) -ceq (Contract $after))
        $record.beforeStateSha256=(Get-FileHash -LiteralPath (Join-Path $ResultDirectory 'before-state.json')).Hash
        $record.afterStateSha256=(Get-FileHash -LiteralPath (Join-Path $ResultDirectory 'after-state.json')).Hash
        if(-not $record.secureBootAfter -or -not $record.recoveryConfirmed){throw 'Security/device recovery differs'}
    }catch{$record.recoveryError=$_.Exception.Message;if(-not $record.error){$record.error=$record.recoveryError}}
    $record.completed=($record.error -eq $null);$record.completedUtc=[datetime]::UtcNow.ToString('o');Save-Run
}
if($record.error){throw $record.error}
$record|ConvertTo-Json -Depth 12
