#requires -Version 7.5
# Plan by default. Requires an already installed/running UsbDk; never installs or changes trust.
param([switch]$Run, [ValidateSet('List','Capture','DuplexSilence','Rate')][string]$Mode='List',
      [string]$ResultDirectory='tests/results/local/usbdk-traced-01', [string]$ValidatedCaptureRun,
      [ValidateSet(0,44100,48000)][int]$TargetRate=0)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if(($Mode -eq 'Rate') -ne ($TargetRate -ne 0)){throw 'Rate mode requires an explicit TargetRate of 44100 or 48000; other modes do not accept it'}
if($ValidatedCaptureRun -and $Mode -notin @('DuplexSilence','Rate')){throw 'A prior capture argument is used only by DuplexSilence or Rate mode'}
function Full-Path([string]$Value) {
    if($Value -match '["\r\n]'){throw 'Paths must not contain quotes or newlines'}
    if(-not [IO.Path]::IsPathRooted($Value)){$Value=Join-Path $root $Value}
    [IO.Path]::GetFullPath($Value)
}
function Quoted([string]$Value) { '"' + $Value + '"' }
$ResultDirectory=Full-Path $ResultDirectory
if(Test-Path -LiteralPath $ResultDirectory){throw 'Choose a fresh result directory; evidence is never overwritten'}
$exe=Join-Path $root 'artifacts/build/native/Release/sl3_usbdk.exe'
$helper=Join-Path $root 'artifacts/extracted/usbdk-msi/UsbDkHelper.dll10'
$validator=Join-Path $PSScriptRoot 'validate-usbdk-capture.py'
$rateValidator=Join-Path $PSScriptRoot 'validate-usbdk-rate.py'
$python=Join-Path $root '.venv/Scripts/python.exe'
$flag=@{List='--list';Capture='--capture';DuplexSilence='--duplex-silence';Rate='--select-rate'}[$Mode]
$stem=if($Mode -eq 'Capture'){'capture'}elseif($Mode -eq 'DuplexSilence'){'duplex'}elseif($Mode -eq 'Rate'){'rate'}else{'list'}
$nativeArgs=@($flag)
if($Mode -eq 'Rate'){$nativeArgs+=@([string]$TargetRate)}
$nativeArgs+=@('--helper',(Quoted $helper))
if($Mode -ne 'List'){$nativeArgs+=@('--output',(Quoted (Join-Path $ResultDirectory $stem)))}
if(-not $Run){
    [ordered]@{planOnly=$true;mode=$Mode;resultDirectory=$ResultDirectory;executable=$exe;arguments=$nativeArgs
        prerequisites=@('Owner present; already elevated PowerShell 7.5+','Unchanged UsbDk already running under Secure Boot',
            'Tested source/binary identities; full USB trace','DuplexSilence and Rate require a validated capture from the same build',
            'Rate: close audio clients; explicit target may persist; no automatic restoration or retry')
        driverChanges=$false;helperLoaded=$false;audioSubmissions=0
        targetRate=$TargetRate;rateRestorationAttempted=$false
        action='One bounded traced scenario; no install, trust, security, firmware, reset or automatic retry'}|ConvertTo-Json -Depth 5
    return
}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
if(-not ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
    throw 'Run from an already elevated PowerShell 7.5+ terminal; this script does not request elevation'
}
if(-not (Confirm-SecureBootUEFI)){throw 'Secure Boot must remain enabled'}
$preflight=& (Join-Path $PSScriptRoot 'preflight-usbdk.ps1')|ConvertFrom-Json
if(@($preflight.installedDriver|Where-Object State -eq 'Running').Count -ne 1){throw 'UsbDk must already be installed and running; no installation attempted'}
if($Mode -in @('DuplexSilence','Rate')){
    if(-not $ValidatedCaptureRun){throw 'A prior traced Capture run is required before silent output or a rate test'}
    $ValidatedCaptureRun=Full-Path $ValidatedCaptureRun
    $prior=& $python $validator $ValidatedCaptureRun --expected-native-sha256 $preflight.nativeSha256
    if($LASTEXITCODE -ne 0){throw "Prior capture evidence failed: $prior"}
    $prior=$prior|ConvertFrom-Json
    if($prior.valid -ne $true){throw 'Prior capture evidence was not validated'}
}
New-Item -ItemType Directory -Path $ResultDirectory|Out-Null
$preflight|ConvertTo-Json -Depth 10|Set-Content -LiteralPath (Join-Path $ResultDirectory 'preflight.json') -Encoding utf8
if($Mode -in @('DuplexSilence','Rate')){$prior|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $ResultDirectory 'prior-capture-validation.json') -Encoding utf8}
$tracePath=Join-Path $ResultDirectory 'trace/capture.json'
$record=[ordered]@{schema='sl3.usbdk.traced-run.v1';mode=$Mode;startedUtc=[DateTime]::UtcNow.ToString('o')
    completed=$false;error=$null;nativeSha256=$preflight.nativeSha256;secureBootBefore=$true;secureBootAfter=$false
    nativeExitCode=$null;traceExitCode=$null;traceCleanupConfirmed=$false;driverChanges=$false}
if($Mode -eq 'Rate'){
    $record.targetRate=$TargetRate;$record.rateRestorationAttempted=$false
    $record.deviceRateEffectUnknown=$true;$record.lastKnownDeviceMayHaveChanged=$null;$record.lastIoRetired=$null
    $record.priorCaptureValidationSha256=(Get-FileHash -LiteralPath (Join-Path $ResultDirectory 'prior-capture-validation.json')).Hash
}
$record.runnerInputs=[ordered]@{}
foreach($name in @('test-usbdk-traced.ps1','capture-usb-startup.ps1','preflight-usbdk.ps1','collect-windows-state.ps1','validate-usbdk-capture.py','validate-usbdk-rate.py')){
    $record.runnerInputs[$name]=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name)).Hash
}
function Save-Run { $record|ConvertTo-Json -Depth 12|Set-Content -LiteralPath (Join-Path $ResultDirectory 'run.json') -Encoding utf8 }
function Read-Trace {
    $stream=[IO.FileStream]::new($tracePath,[IO.FileMode]::Open,[IO.FileAccess]::Read,([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
    $reader=[IO.StreamReader]::new($stream)
    try{$reader.ReadToEnd()|ConvertFrom-Json -DateKind String}finally{$reader.Dispose()}
}
function Child([string]$File,[string[]]$Arguments,[string]$Name) {
    Start-Process -FilePath $File -ArgumentList $Arguments -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $ResultDirectory "$Name-output.txt") -RedirectStandardError (Join-Path $ResultDirectory "$Name-error.txt")
}
function Wait-Bounded($Process,[int]$Milliseconds) {
    if($Process.WaitForExit($Milliseconds)){return}
    $record.timedOutProcessId=$Process.Id
    $Process.Kill($true)
    $record.timedOutProcessExited=$Process.WaitForExit(5000)
    throw 'Child exceeded its deadline; test failed. Inspect process teardown and device recovery before another attempt'
}
function State-Contract($State) {
    [ordered]@{secureBoot=$State.secureBoot;deviceGuard=$State.deviceGuard;hvciRegistry=$State.hvciRegistry
        devices=@($State.devices|Sort-Object {$_.device.InstanceId}|ForEach-Object {
            [ordered]@{device=$_.device;properties=@($_.properties|Sort-Object KeyName)}
        });asio=$State.asio;application=$State.application}|ConvertTo-Json -Depth 12 -Compress
}
$traceProcess=$null
Save-Run
try {
    & (Join-Path $PSScriptRoot 'collect-windows-state.ps1') -Output (Join-Path $ResultDirectory 'before-state.json')|Out-Null
    $baseline=Get-Content -LiteralPath (Join-Path $ResultDirectory 'before-state.json') -Raw|ConvertFrom-Json
    if(@($baseline.devices).Count -ne 1 -or $baseline.secureBoot -ne $true){throw 'One SL3 and Secure Boot must be confirmed in the recovery baseline before device access'}
    $pwsh=(Get-Process -Id $PID).Path
    $traceProcess=Child $pwsh @('-NoProfile','-File',(Quoted (Join-Path $PSScriptRoot 'capture-usb-startup.ps1')),
        '-Capture','-DurationSeconds','60','-OutputDirectory',(Quoted (Join-Path $ResultDirectory 'trace'))) 'trace'
    $ready=$false
    for($i=0;$i -lt 100;$i++){
        if($traceProcess.HasExited){throw 'Trace exited before readiness'}
        $trace=try{Read-Trace}catch{$null}
        if($trace.status -eq 'recording'){$ready=$true;break}
        Start-Sleep -Milliseconds 200
    }
    if(-not $ready){throw 'Trace was not ready within 20 seconds'}
    $traceStart=[DateTimeOffset]::Parse($trace.startedUtc).UtcDateTime
    if(([DateTime]::UtcNow-$traceStart).TotalSeconds -gt 35){throw 'Insufficient remaining trace window'}
    $null=& logman.exe query $trace.session -ets 2>&1
    if($LASTEXITCODE -ne 0){throw 'Trace session is not live'}
    # Recheck executable immediately before launch; native code pins/locks its dependencies.
    if((Get-FileHash -LiteralPath $exe).Hash -ne $record.nativeSha256){throw 'Native binary changed after preflight'}
    $record.nativeStartedUtc=[DateTime]::UtcNow.ToString('o')
    $native=Child $exe $nativeArgs 'native'
    Wait-Bounded $native 20000
    $record.nativeCompletedUtc=[DateTime]::UtcNow.ToString('o')
    $record.nativeExitCode=$native.ExitCode
    if($Mode -eq 'Rate'){
        $nativeRecord=Join-Path $ResultDirectory 'rate/rate.json'
        if(Test-Path -LiteralPath $nativeRecord){
            $record.nativeRecordSha256=(Get-FileHash -LiteralPath $nativeRecord).Hash
            if((Get-Item -LiteralPath $nativeRecord).Length -le 1MB){
                $last=Get-Content -LiteralPath $nativeRecord -Raw|ConvertFrom-Json
                if($last.device_may_have_changed -is [bool]){$record.lastKnownDeviceMayHaveChanged=$last.device_may_have_changed}
                if($last.last_io_retired -is [bool]){$record.lastIoRetired=$last.last_io_retired}
            }
        }
        # Failure preserves the last native progress and unknown-effect state.
        if($native.ExitCode -ne 0){throw 'Native rate scenario failed; preserve its progress and do not automatically retry or restore'}
        $nativeValidation=& $python $rateValidator --native-record $nativeRecord --expected-target $TargetRate
        if($LASTEXITCODE -ne 0){throw "Native rate result was not confirmed: $nativeValidation"}
        $record.deviceRateEffectUnknown=$false
    }
    if($native.ExitCode -ne 0){throw 'Native scenario failed; inspect its record'}
    if($Mode -eq 'List'){
        $listing=Get-Content -LiteralPath (Join-Path $ResultDirectory 'native-output.txt') -Raw|ConvertFrom-Json
        if($listing.matched_sl3 -ne 1 -or $listing.descriptor_fixture_matches -ne $true -or $listing.high_speed -ne $true -or $listing.device_redirected -ne $false){throw 'Descriptor-only SL3 result was not confirmed'}
    }elseif($Mode -ne 'Rate'){
        $nativeRecord=Join-Path $ResultDirectory "$stem/$stem.json"
        $result=Get-Content -LiteralPath $nativeRecord -Raw|ConvertFrom-Json
        $success=if($Mode -eq 'Capture'){$result.capture_succeeded}else{$result.duplex_succeeded}
        if($success -ne $true -or $result.transfers_succeeded -ne $true -or $result.buffer_cleanup_complete -ne $true -or $result.redirect_and_alternates_cleanup_succeeded -ne $true){throw 'Native transfer/cleanup was not confirmed'}
        $record.nativeRecordSha256=(Get-FileHash -LiteralPath $nativeRecord).Hash
    }
}catch{$record.error=$_.Exception.Message}
finally {
    if($Mode -eq 'Rate'){
        try{
            # Also retain evidence when the child timed out before Wait-Bounded
            # returned. Unknown effects are never reset to false on this path.
            $nativeRecord=Join-Path $ResultDirectory 'rate/rate.json'
            if(Test-Path -LiteralPath $nativeRecord){
                $record.nativeRecordSha256=(Get-FileHash -LiteralPath $nativeRecord).Hash
                if((Get-Item -LiteralPath $nativeRecord).Length -le 1MB){
                    $last=Get-Content -LiteralPath $nativeRecord -Raw|ConvertFrom-Json
                    if($last.device_may_have_changed -is [bool]){$record.lastKnownDeviceMayHaveChanged=$last.device_may_have_changed}
                    if($last.last_io_retired -is [bool]){$record.lastIoRetired=$last.last_io_retired}
                }
            }
        }catch{$record.rateProgressError=$_.Exception.Message;$record.deviceRateEffectUnknown=$true}
    }
    try {
        if($traceProcess){
            # Normal recorder window is 60 seconds. No unbounded wait on a stuck child.
            $traceWait=[Diagnostics.Stopwatch]::StartNew()
            while(-not $traceProcess.HasExited -and $traceWait.ElapsedMilliseconds -lt 80000){$null=$traceProcess.WaitForExit(1000)}
            if(-not $traceProcess.HasExited){
                try{
                    $trace=Read-Trace
                    $ownedCreate=@($trace.commands|Where-Object {$_.exitCode -eq 0 -and $_.arguments[0] -eq 'create' -and $_.arguments[1] -eq 'trace' -and $_.arguments[3] -eq $trace.session})
                    if($trace.session -cmatch '^SL3Startup-[0-9a-f]{32}$' -and $ownedCreate.Count -eq 1){
                        $null=& logman.exe stop $trace.session -ets 2>&1
                        $record.emergencyTraceStopExit=$LASTEXITCODE
                        $null=& logman.exe delete $trace.session 2>&1
                        $record.emergencyTraceDeleteExit=$LASTEXITCODE
                    }
                }finally{
                    if(-not $traceProcess.HasExited){$traceProcess.Kill($true)}
                    $record.traceProcessExited=$traceProcess.WaitForExit(5000)
                }
                throw 'Recorder exceeded its bounded window; test failed even if targeted cleanup succeeded'
            }
            $record.traceExitCode=$traceProcess.ExitCode
            $trace=Read-Trace
            $record.traceStartedUtc=$trace.startedUtc
            $record.traceStoppedUtc=$trace.stoppedUtc
            $record.traceCleanupConfirmed=($traceProcess.ExitCode -eq 0 -and $trace.status -eq 'window completed' -and -not $trace.deleteError)
            if(-not $record.traceCleanupConfirmed){throw 'Trace cleanup was not confirmed'}
            $etl=@(Get-ChildItem -LiteralPath (Join-Path $ResultDirectory 'trace') -Filter '*.etl' -File)
            if($etl.Count -ne 1 -or $etl[0].Length -gt 65MB){throw 'Expected one bounded ETL file'}
            $record.etlSha256=(Get-FileHash -LiteralPath $etl[0].FullName).Hash
            $decoder=Child (Join-Path $env:SystemRoot 'System32/tracerpt.exe') @((Quoted $etl[0].FullName),'-o',
                (Quoted (Join-Path $ResultDirectory 'events.xml')),'-of','XML','-y') 'decode'
            Wait-Bounded $decoder 45000
            if($decoder.ExitCode -ne 0){throw 'Trace decoding failed'}
            $stats=& $python $validator --trace-xml (Join-Path $ResultDirectory 'events.xml')
            if($LASTEXITCODE -ne 0){throw "Trace statistics failed: $stats"}
            $record.traceStats=$stats|ConvertFrom-Json
            if($record.traceStats.eventsLost -ne 0 -or $record.traceStats.buffersLost -ne 0 -or $record.traceStats.session -ne $trace.session){throw 'Trace is lossy or belongs to a different session'}
        }
    }catch{$record.traceError=$_.Exception.Message;if(-not $record.error){$record.error=$record.traceError}}
    try{
        $record.secureBootAfter=[bool](Confirm-SecureBootUEFI)
        & (Join-Path $PSScriptRoot 'collect-windows-state.ps1') -Output (Join-Path $ResultDirectory 'after-state.json')|Out-Null
        $record.beforeStateSha256=(Get-FileHash -LiteralPath (Join-Path $ResultDirectory 'before-state.json')).Hash
        $record.afterStateSha256=(Get-FileHash -LiteralPath (Join-Path $ResultDirectory 'after-state.json')).Hash
        if(-not $record.secureBootAfter){throw 'Secure Boot after-state was not confirmed'}
        $before=Get-Content -LiteralPath (Join-Path $ResultDirectory 'before-state.json') -Raw|ConvertFrom-Json
        $after=Get-Content -LiteralPath (Join-Path $ResultDirectory 'after-state.json') -Raw|ConvertFrom-Json
        $record.recoveryConfirmed=(@($before.devices).Count -eq 1 -and (State-Contract $before) -ceq (State-Contract $after))
        if(-not $record.recoveryConfirmed){throw 'Device, driver, security, ASIO registration or application state differs from the recorded baseline'}
    }catch{$record.recoveryError=$_.Exception.Message;if(-not $record.error){$record.error=$record.recoveryError}}
    $record.completed=($null -eq $record.error -and $record.nativeExitCode -eq 0 -and $record.traceCleanupConfirmed -and $record.secureBootAfter)
    $record.completedUtc=[DateTime]::UtcNow.ToString('o')
    Save-Run
}
if(-not $record.completed){throw "Traced scenario failed: $($record.error)"}
if($Mode -eq 'Capture'){
    $validation=& $python $validator $ResultDirectory --expected-native-sha256 $record.nativeSha256
    $validation|Set-Content -LiteralPath (Join-Path $ResultDirectory 'capture-validation.json') -Encoding utf8
    if($LASTEXITCODE -ne 0){throw 'Capture recorded but prerequisite validation failed; inspect evidence before proceeding'}
}
if($Mode -eq 'Rate'){
    $validation=& $python $rateValidator $ResultDirectory --expected-native-sha256 $record.nativeSha256 --expected-target $TargetRate
    $validation|Set-Content -LiteralPath (Join-Path $ResultDirectory 'rate-validation.json') -Encoding utf8
    if($LASTEXITCODE -ne 0){
        $record.completed=$false;$record.error='Rate recorded but evidence consistency validation failed';Save-Run
        throw 'Rate result was not validated; preserve evidence and inspect device state before another test'
    }
}
$record|ConvertTo-Json -Depth 12
