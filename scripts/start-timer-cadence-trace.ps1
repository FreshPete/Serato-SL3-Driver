# One ordinary-user timer diagnostic and one separately elevated passive trace.
param([Parameter(Mandatory)][string]$Plan,[switch]$Run,[switch]$SilentStream,[switch]$Tone,
      [switch]$StereoMarkers,[switch]$RetainedKeepalive,[switch]$HostLoopback)
$ErrorActionPreference='Stop'
if($SilentStream -and $Tone){throw 'Choose one playback mode'}
if($StereoMarkers -and -not $Tone){throw 'Stereo markers require tone mode'}
if(($RetainedKeepalive -or $HostLoopback) -and ($Tone -or $SilentStream -or ($RetainedKeepalive -and $HostLoopback))){throw 'Choose one retained or standalone test'}
$root=Split-Path -Parent $PSScriptRoot
$settings=Get-Content -LiteralPath $Plan -Raw | ConvertFrom-Json
$scenario=if($HostLoopback){'host-callback-loopback-20261104'}elseif($RetainedKeepalive){'retained-keepalive-20261104'}elseif($StereoMarkers){'timer-stereo-markers-20261104'}elseif($Tone){'timer-tone-20261104'}elseif($SilentStream){'timer-silent-stream-20261104'}else{'timer-cadence-20261104'}
$buildName=if($RetainedKeepalive -or $HostLoopback){'windows-post-loopback-20261104'}else{$scenario}
$build=Join-Path $root "artifacts/build/$buildName"
$worker=Join-Path $build 'Release/sl3_usbdk.exe'
$helper=Join-Path $root 'artifacts/extracted/usbdk-msi/UsbDkHelper.dll10'
$base=Join-Path $root "tests/results/local/$scenario"
$traceDirectory="$base-usb"
if($settings.worker -ine $worker -or $settings.helper -ine $helper -or
   $settings.resultDirectory -ine $base -or $settings.traceDirectory -ine $traceDirectory -or
   (-not ($RetainedKeepalive -or $HostLoopback) -and $settings.challenge -cnotmatch '^[0-9a-f]{16}$')){throw 'Unexpected cadence plan'}
$attemptPath="$base-attempted.json"
if((Test-Path -LiteralPath $base) -or (Test-Path -LiteralPath $traceDirectory) -or
   (Test-Path -LiteralPath $attemptPath)){throw 'Cadence packet already used'}
$manifest=Get-Content -LiteralPath (Join-Path $build 'native-build-Release.json') -Raw | ConvertFrom-Json
if($settings.workerSha256 -ne $manifest.usbdk.executableSha256 -or
   (Get-FileHash -LiteralPath $worker).Hash -ne $settings.workerSha256 -or
   (Get-FileHash -LiteralPath $helper).Hash -ne $settings.helperSha256){throw 'Cadence runtime hash differs'}
$collector=Join-Path $PSScriptRoot 'capture-usb-startup.ps1'
$shell=(Get-Command pwsh).Source
$traceSeconds=40
if($HostLoopback){
    $traceSeconds=60
    $probe=Join-Path $build 'Release/sl3_input_record_probe.exe'
    $analyser=Join-Path $PSScriptRoot 'analyse-timer-loopback.py'
    $validator=Join-Path $PSScriptRoot 'validate-input-record-probe.py'
    $traceValidator=Join-Path $PSScriptRoot 'validate-usbdk-capture.py'
    $python=Join-Path $root '.venv/Scripts/python.exe'
    if((Get-FileHash -LiteralPath $probe).Hash -ne $settings.probeSha256 -or
       (Get-FileHash -LiteralPath $analyser).Hash -ne $settings.analyserSha256 -or
       (Get-FileHash -LiteralPath $validator).Hash -ne $settings.validatorSha256 -or
       (Get-FileHash -LiteralPath $traceValidator).Hash -ne $settings.traceValidatorSha256){throw 'Host loopback probe, analyser or validator hash differs'}
    $preview=& $probe --plan-loopback | ConvertFrom-Json
    if($LASTEXITCODE -or $preview.planOnly -ne $true -or $preview.deviceAccess -ne $false -or
       $preview.expectedRateHz -ne 44100 -or ($preview.markerHz -join ',') -cne '997,1301' -or
       $preview.markerFirstFrame -ne 8192 -or $preview.markerDurationMilliseconds -ne 650 -or
       $preview.bankFrames -ne 128){throw 'Unexpected host loopback preview'}
    & $python -c 'import numpy'
    if($LASTEXITCODE){throw 'Host loopback analysis environment unavailable'}
}elseif($RetainedKeepalive){
    $traceSeconds=60
    $probe=Join-Path $build 'Release/sl3_host_probe.exe'
    $validator=Join-Path $PSScriptRoot 'validate-retained-host-probe.py'
    if((Get-FileHash -LiteralPath $probe).Hash -ne $manifest.hostProbe.executableSha256 -or
       (Get-FileHash -LiteralPath $validator).Hash -ne $manifest.hostProbe.retained.validatorSha256){
        throw 'Retained probe or validator hash differs'
    }
    $preview=& $probe --plan | ConvertFrom-Json
    if($LASTEXITCODE -or $preview.plan_only -ne $true -or $preview.device_access -ne $false -or
       $preview.simulated -ne $false -or $preview.retained_lifecycle.streams -ne 2){throw 'Unexpected retained preview'}
}else{
$workerMode=@('--timer-cadence')
$validationMode=@('--cadence')
if($SilentStream){$workerMode+='--timer-silent-stream';$validationMode+='--silent-stream'}
if($Tone){$workerMode+='--timer-tone';$validationMode+='--tone'}
if($StereoMarkers){$workerMode+='--timer-stereo-markers'}
$preview=& $worker --plan @workerMode --challenge $settings.challenge | ConvertFrom-Json
if($LASTEXITCODE -or $preview.plan_only -ne $true -or $preview.device_access -ne $false -or
   $preview.maximum_writes -ne 10 -or $preview.audio_submissions -ne 0 -or
   [bool]$preview.silent_stream -ne [bool]$SilentStream){throw 'Unexpected cadence preview'}
if($Tone -and ($preview.tone_hz -ne 997 -or $preview.tone_duration_ms -ne 650 -or
   $preview.routing_setters -ne 0)){throw 'Unexpected tone preview'}
if($StereoMarkers -and ($preview.stereo_marker_hz -join ',') -cne '997,1301'){throw 'Unexpected stereo marker preview'}
}
$tracePlan=& $shell -NoProfile -File $collector -WithUsbDkLifecycle -DurationSeconds $traceSeconds -OutputDirectory $traceDirectory
if($LASTEXITCODE){throw 'USB/WPP preflight failed'}
if(-not $Run){$tracePlan;return}

Import-Module (Join-Path $PSScriptRoot 'inspect-process.psm1')
if((Get-Sl3ProcessEvidence -ProcessId $PID -WithToken).elevated -ne $false){throw 'Start under the ordinary user token'}
$device=Get-PnpDevice -PresentOnly -InstanceId 'USB\VID_1CC5&PID_0001\SL3.01.00'
if($device.Problem -ne 'CM_PROB_DRIVER_FAILED_LOAD' -or
   (Get-Process 'Serato DJ Pro',sl3_usbdk,sl3_host_probe,sl3_input_record_probe -ErrorAction SilentlyContinue)){throw 'SL3 resting state differs'}
$scriptHash=(Get-FileHash -LiteralPath $collector).Hash
$attempt=[IO.File]::Open($attemptPath,[IO.FileMode]::CreateNew)
try{
    $record=@{planSha256=(Get-FileHash -LiteralPath $Plan).Hash;utc=[datetime]::UtcNow.ToString('o')}
    $bytes=[Text.Encoding]::UTF8.GetBytes(($record | ConvertTo-Json))
    $attempt.Write($bytes,0,$bytes.Length)
}finally{$attempt.Dispose()}
$admin=Start-Process -FilePath $shell -Verb RunAs -WindowStyle Hidden -PassThru -ArgumentList @(
    '-NoProfile','-File',('"{0}"' -f $collector),'-Capture','-WithUsbDkLifecycle','-DurationSeconds',([string]$traceSeconds),
    '-OutputDirectory',('"{0}"' -f $traceDirectory))
$capture=Join-Path $traceDirectory 'capture.json'
$deadline=[datetime]::UtcNow.AddSeconds(15)
try{
    do{
        try{$trace=Get-Content -LiteralPath $capture -Raw | ConvertFrom-Json}catch{$trace=$null}
        if($trace.status -eq 'recording'){break}
        Start-Sleep -Milliseconds 100
    }while(-not $admin.HasExited -and [datetime]::UtcNow -lt $deadline)
    if($trace.status -ne 'recording'){throw 'No fresh recording manifest'}
    $identity=Get-Sl3ProcessEvidence -ProcessId $admin.Id
    $age=([datetime]::UtcNow-([datetimeoffset]$trace.startedUtc).UtcDateTime).TotalSeconds
    $start=@($trace.commands | Where-Object {
        ($_.arguments -join ' ') -ceq "start -n $($trace.session)" -and $_.exitCode -eq 0
    })
    if(-not $identity.alive -or $trace.collectorPid -ne $admin.Id -or
       $identity.creationFileTimeUtc -ne $trace.collectorCreationFileTimeUtc -or
       $identity.imagePath -ine $trace.collectorImagePath -or $trace.producerSha256 -ne $scriptHash -or
       $age -lt 0 -or $age -gt 2 -or $start.Count -ne 1){throw 'Collector identity or freshness differs'}
    $admission=[ordered]@{collector=$identity;session=$trace.session;ageSeconds=$age;challenge=$settings.challenge;workerSha256=$settings.workerSha256}
    if($HostLoopback){
        $admission.probeSha256=$settings.probeSha256
        $admission.analyserSha256=$settings.analyserSha256
        $admission.validatorSha256=$settings.validatorSha256
        $admission.traceValidatorSha256=$settings.traceValidatorSha256
        $admission.helperSha256=$settings.helperSha256
    }
    $admission | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $traceDirectory 'timer-admission.json')
    $python=Join-Path $root '.venv/Scripts/python.exe'
    if($HostLoopback){
        $probeError=$null
        $probeExitCode=$null
        try{
            $probeStarted=[datetimeoffset]::UtcNow
            try{
                & $probe --run-loopback --worker $worker --worker-sha256 $settings.workerSha256 --helper $helper --output $base --expected-rate 44100
                $probeExitCode=$LASTEXITCODE
            }finally{$probeCompleted=[datetimeoffset]::UtcNow}
            if($probeExitCode){throw "Host loopback probe exited $probeExitCode"}
            & $python $analyser $base --host-callback --worker-sha256 $settings.workerSha256 --output (Join-Path $base 'loopback-analysis.json')
            if($LASTEXITCODE){throw 'Host loopback analysis failed'}
        }catch{$probeError=$_}
    }elseif($RetainedKeepalive){
        & $probe --retained-keepalive-44100 --worker $worker --worker-sha256 $settings.workerSha256 --helper $helper --output $base
        if($LASTEXITCODE){throw 'Retained probe failed; preserve its records'}
        & $python $validator --probe $base --worker-sha256 $settings.workerSha256 --expected-rate 44100 --keepalive
        if($LASTEXITCODE){throw 'Retained keepalive record rejected'}
    }else{
    & $worker --timer-query @workerMode --challenge $settings.challenge --helper $helper --output $base
    if($LASTEXITCODE){throw 'Cadence worker failed; preserve its records'}
    $validated=& $python (Join-Path $PSScriptRoot 'validate-driver-timer.py') (Join-Path $base 'timer.json') --challenge $settings.challenge @validationMode
    if($LASTEXITCODE){throw 'Cadence record rejected'}
    if($StereoMarkers -and ((($validated | ConvertFrom-Json).stereoMarkerHz) -join ',') -cne '997,1301'){
        throw 'Cadence record missing stereo markers'
    }
    $validated
    }
}finally{
    if(-not $admin.WaitForExit(70000)){throw 'Collector still active after observation window'}
    if($admin.ExitCode){throw 'Collector failed; inspect its final trace record'}
}
$final=Get-Content -LiteralPath $capture -Raw | ConvertFrom-Json
$deleted=@($final.commands | Where-Object {
    ($_.arguments -join ' ') -ceq "delete -n $($trace.session)" -and $_.exitCode -eq 0
})
if($final.status -ne 'window completed' -or $final.session -cne $trace.session -or
   $final.cleanupError -or $deleted.Count -ne 1){throw 'Trace cleanup requires inspection'}
$after=Get-PnpDevice -PresentOnly -InstanceId $device.InstanceId -ErrorAction SilentlyContinue
$restored=$null -ne $after -and $after.Problem -eq $device.Problem
if(-not $HostLoopback -and -not $restored){throw 'SL3 resting state differs after the test'}
if($HostLoopback){
    $covered=$probeStarted -ge [datetimeoffset]$final.startedUtc -and $probeCompleted -le [datetimeoffset]$final.stoppedUtc
    $etls=@(Get-ChildItem -LiteralPath $traceDirectory -Filter '*.etl' -File)
    $recorded=@($final.files)
    if($etls.Count -ne 1 -or $recorded.Count -ne 1 -or $etls[0].Name -cne $recorded[0].name -or
       $etls[0].Length -le 0 -or $etls[0].Length -ge 64MB -or $etls[0].Length -ne $recorded[0].bytes -or
       (Get-FileHash -LiteralPath $etls[0].FullName).Hash -ne $recorded[0].sha256){
        throw 'Loopback ETL differs from the collector record'
    }
    $xml=Join-Path $traceDirectory 'events.xml'
    $decoder=Start-Process -FilePath (Join-Path $env:SystemRoot 'System32/tracerpt.exe') -WindowStyle Hidden -PassThru -ArgumentList @(
        ('"{0}"' -f $etls[0].FullName),'-o',('"{0}"' -f $xml),'-of','XML','-y')
    if(-not $decoder.WaitForExit(45000)){
        $decoder.Kill()
        $decoder.WaitForExit()
        throw 'USB trace decoder timed out'
    }
    if($decoder.ExitCode){throw 'USB trace decode failed'}
    $stats=& $python $traceValidator --trace-xml $xml
    if($LASTEXITCODE){throw 'USB trace statistics unavailable'}
    $summary=$stats | ConvertFrom-Json
    if($summary.eventsLost -ne 0 -or $summary.buffersLost -ne 0 -or $summary.session -cne $final.session){
        throw 'USB trace is lossy or belongs to another session'
    }
    [ordered]@{etlSha256=$recorded[0].sha256;probeStartedUtc=$probeStarted.ToString('o');
        probeCompletedUtc=$probeCompleted.ToString('o');probeExitCode=$probeExitCode;
        probeError=$probeError.Exception.Message;coversProbe=$covered;restingStateRestored=$restored;
        problemBefore=[string]$device.Problem;problemAfter=[string]$after.Problem;traceStats=$summary} |
        ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $traceDirectory 'loopback-trace-summary.json')
    if(-not $restored){throw 'SL3 resting state differs after the test'}
    if(-not $covered){throw 'Trace does not cover the complete loopback probe'}
    if($probeError){throw $probeError}
    $result=Get-Content -LiteralPath (Join-Path $base 'loopback-analysis.json') -Raw | ConvertFrom-Json
    if($result.schema -cne 'sl3.host-loopback-analysis.v2' -or $result.bothMarkersAccepted -ne $true){
        throw 'The complete stereo return did not qualify. Inspect the saved analysis for each channel.'
    }
    $result.markerReturns | Select-Object streamChannel,frequencyHz,acceptedOffsetFrames
}
