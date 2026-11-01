#requires -Version 7.5
param([switch]$Run,[ValidateSet(0,44100,48000)][int]$ExpectedRate=0,
      [string]$ResultDirectory='tests/results/local/retained-host-traced-01',
      [string]$ValidatedCaptureRun,[string]$ValidatedDuplexRun)
# One acquired device, two one-second zero-output sessions, then final release.
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
function Full-Path([string]$Value){
    if($Value -match '["\r\n]'){throw 'Invalid path'}
    if(-not [IO.Path]::IsPathRooted($Value)){$Value=Join-Path $root $Value}
    [IO.Path]::GetFullPath($Value)
}
function Quoted([string]$Value){'"'+$Value+'"'}
$ResultDirectory=Full-Path $ResultDirectory
if(Test-Path -LiteralPath $ResultDirectory){throw 'Choose a fresh evidence directory'}
if(-not $Run){
    [ordered]@{planOnly=$true;expectedRateHz=$ExpectedRate;deviceAccess=$false;streams=2;streamMilliseconds=1000
        intervals=8;bankFrames=128;outputPayload='zero PCM only';driverChanges=$false;securityChanges=$false
        asioRegistration=$false;latencyProfileCreated=$false;automaticRetry=$false;redirectsRequested=1;redirectMayReenumerate=$true
        resultDirectory=$ResultDirectory;prerequisites=@('Owner present; elevated PowerShell; Secure Boot enabled; reviewed driver running',
            'Explicit expected rate; current tested native worker/probe; validated same-worker capture then silent duplex',
            'No remaining device-test process; complete USB trace; one final release and independent ownership retirement')}
        |ConvertTo-Json -Depth 5
    return
}
if(-not $ExpectedRate -or -not $ValidatedCaptureRun -or -not $ValidatedDuplexRun){throw 'Explicit ExpectedRate and same-worker capture/duplex records are required'}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
if(-not ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'An elevated terminal is required'}
if(-not (Confirm-SecureBootUEFI)){throw 'Secure Boot must remain enabled'}
if(@(Get-CimInstance Win32_Process -Filter "Name='sl3_usbdk.exe' OR Name='sl3_host_probe.exe' OR Name='sl3_host_probe_simulated.exe'").Count){throw 'A prior device-test process remains; do not reopen'}
$ValidatedCaptureRun=Full-Path $ValidatedCaptureRun;$ValidatedDuplexRun=Full-Path $ValidatedDuplexRun
$preflight=& (Join-Path $PSScriptRoot 'preflight-usbdk.ps1')|ConvertFrom-Json
if(@($preflight.installedDriver|Where-Object State -eq 'Running').Count -ne 1){throw 'Reviewed UsbDk must be running'}
$build=Get-Content -LiteralPath (Join-Path $root 'artifacts/build/native/native-build-Release.json') -Raw|ConvertFrom-Json
$probe=Join-Path $root 'artifacts/build/native/Release/sl3_host_probe.exe'
$worker=Join-Path $root 'artifacts/build/native/Release/sl3_usbdk.exe'
$helper=Join-Path $root 'artifacts/extracted/usbdk-msi/UsbDkHelper.dll10'
$python=Join-Path $root '.venv/Scripts/python.exe'
$validator=Join-Path $PSScriptRoot 'validate-retained-host-probe.py'
if(-not $build.hostProbe.retained.simulatedLifecyclePassed -or $build.hostProbe.retained.physicalLifecycleTested -or
   (Get-FileHash -LiteralPath $probe).Hash -ne $build.hostProbe.executableSha256 -or
   (Get-FileHash -LiteralPath $validator).Hash -ne $build.hostProbe.retained.validatorSha256 -or
   (Get-FileHash -LiteralPath $PSCommandPath).Hash -ne $build.hostProbe.retained.runnerSha256 -or
   (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'test-retained-host-probe.py')).Hash -ne $build.hostProbe.retained.testScriptSha256){throw 'Retained probe/validator/runner is not the reviewed tested build'}
foreach($entry in $build.hostProbe.retained.scriptInputs.PSObject.Properties){
    if((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $entry.Name)).Hash -ne $entry.Value){throw "Reviewed probe script/dependency changed: $($entry.Name)"}
}
$prerequisites=& $python $validator --prerequisites $ValidatedCaptureRun $ValidatedDuplexRun --worker-sha256 $preflight.nativeSha256 --expected-rate $ExpectedRate
if($LASTEXITCODE -ne 0 -or ($prerequisites|ConvertFrom-Json).valid -ne $true){throw 'Same-worker capture/zero-duplex prerequisites failed'}
$plan=& $probe --plan|ConvertFrom-Json
if($LASTEXITCODE -ne 0 -or -not $plan.plan_only -or $plan.simulated -or $plan.device_access -or
   $plan.retained_lifecycle.streams -ne 2 -or $plan.retained_lifecycle.stream_ms -ne 1000 -or
   $plan.retained_lifecycle.intervals -ne 8 -or $plan.retained_lifecycle.bank_frames -ne 128){throw 'Expected the tested native retained plan'}
New-Item -ItemType Directory -Path $ResultDirectory|Out-Null
$preflight|ConvertTo-Json -Depth 10|Set-Content -LiteralPath (Join-Path $ResultDirectory 'preflight.json')
$prerequisites|Set-Content -LiteralPath (Join-Path $ResultDirectory 'prerequisite-validation.json')
$record=[ordered]@{schema='sl3.retained-host.traced-run.v1';startedUtc=[datetime]::UtcNow.ToString('o')
    completed=$false;error=$null;probeExitCode=$null;traceExitCode=$null;traceCleanupConfirmed=$false;secureBootBefore=$true;secureBootAfter=$false
    workerSha256=$preflight.nativeSha256;probeSha256=(Get-FileHash -LiteralPath $probe).Hash;expectedRateHz=$ExpectedRate
    priorCaptureRunSha256=(Get-FileHash -LiteralPath (Join-Path $ValidatedCaptureRun 'run.json')).Hash
    priorDuplexRunSha256=(Get-FileHash -LiteralPath (Join-Path $ValidatedDuplexRun 'run.json')).Hash
    prerequisiteValidationSha256=(Get-FileHash -LiteralPath (Join-Path $ResultDirectory 'prerequisite-validation.json')).Hash
    driverChanges=$false;asioRegistration=$false;latencyMeasured=$false;automaticRetry=$false}
$record.runnerInputs=[ordered]@{}
foreach($name in @('test-retained-host-traced.ps1','validate-retained-host-probe.py','test-retained-host-probe.py','read-startup-journal.ps1',
                  'capture-usb-startup.ps1','preflight-usbdk.ps1','collect-windows-state.ps1','export-usbdk-physical-checkpoint.py','validate-usbdk-capture.py','analyse-callback-timing.py')){
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
    $probeArguments=@(('--retained-'+$ExpectedRate),'--worker',(Quoted $worker),'--worker-sha256',$record.workerSha256,
        '--helper',(Quoted $helper),'--output',(Quoted (Join-Path $ResultDirectory 'probe')))
    $child=Child $probe $probeArguments 'probe'
    if(-not $child.WaitForExit(55000)){
        $record.probeTimedOut=$true;$child.Kill($true);$record.probeExitedAfterContainment=$child.WaitForExit(5000)
        throw 'Retained probe exceeded its deadline; cleanup is unproven'
    }
    $record.probeExitCode=$child.ExitCode;$record.probeCompletedUtc=[datetime]::UtcNow.ToString('o')
    $probeRecord=Join-Path $ResultDirectory 'probe/probe.json'
    $record.probeRecordSha256=(Get-FileHash -LiteralPath $probeRecord).Hash
    if($child.ExitCode -ne 0){throw 'Retained lifecycle failed; inspect per-stream records and startup journal'}
    $validation=& $python $validator --probe (Join-Path $ResultDirectory 'probe') --worker-sha256 $record.workerSha256 --expected-rate $ExpectedRate
    if($LASTEXITCODE -ne 0 -or ($validation|ConvertFrom-Json).valid -ne $true){throw 'Retained lifecycle/journal consistency gate failed'}
    $validation|Set-Content -LiteralPath (Join-Path $ResultDirectory 'probe-validation.json')
    $record.probeValidationSha256=(Get-FileHash -LiteralPath (Join-Path $ResultDirectory 'probe-validation.json')).Hash
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
