#requires -Version 7.0
param([switch]$Run, [switch]$DevelopmentTrustApproved, [switch]$ActivateAudioAlternates, [switch]$QueryClock, [switch]$CaptureAudio,
      [string]$ResultDirectory='tests/results/local/winusb-traced-01')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if (@(@($ActivateAudioAlternates,$QueryClock,$CaptureAudio)|Where-Object {$_}).Count -gt 1) { throw 'Run one bounded experiment at a time.' }
if (-not [IO.Path]::IsPathRooted($ResultDirectory)) { $ResultDirectory=Join-Path $root $ResultDirectory }
$ResultDirectory=[IO.Path]::GetFullPath($ResultDirectory)
if (Test-Path -LiteralPath $ResultDirectory) { throw 'Choose a new result directory; prior tests are never overwritten.' }
if (-not $Run) {
    [ordered]@{resultDirectory=$ResultDirectory;activateAudioAlternates=[bool]$ActivateAudioAlternates;queryClock=[bool]$QueryClock;captureAudio=[bool]$CaptureAudio;action='One traced binding, initial probe, selected bounded experiment, then targeted cleanup. Capture mode is 32 ms IN only; clock mode sends only 0x30. No firmware, audio OUT or boot-policy changes.'} | ConvertTo-Json
    return
}
if (-not $DevelopmentTrustApproved) { throw 'Development certificate trust approval is required.' }
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'An elevated PowerShell 7 process is required.' }
New-Item -ItemType Directory -Path $ResultDirectory | Out-Null
$captureDir=Join-Path $ResultDirectory 'trace'
$captureRecord=Join-Path $captureDir 'capture.json'
$runPath=Join-Path $ResultDirectory 'run.json'
$record=[ordered]@{startedUtc=[DateTime]::UtcNow.ToString('o');phase='before capture';error=$null}
function Save-Run { $record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $runPath -Encoding utf8 }
function Read-TraceRecord {
    $stream=[IO.FileStream]::new($captureRecord,[IO.FileMode]::Open,[IO.FileAccess]::Read,([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
    $reader=[IO.StreamReader]::new($stream)
    try { $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
}
Save-Run
Start-Transcript -Path (Join-Path $ResultDirectory 'run.log') | Out-Null
$captureProcess=$null
try {
    if (-not (Confirm-SecureBootUEFI)) { throw 'Secure Boot must remain enabled.' }
    $record.secureBootBefore=$true; Save-Run
    $pwsh=(Get-Process -Id $PID).Path
    $arguments=@('-NoProfile','-File',('"{0}"' -f (Join-Path $PSScriptRoot 'capture-usb-startup.ps1')),
                 '-Capture','-DurationSeconds','60','-OutputDirectory',('"{0}"' -f $captureDir))
    $captureProcess=Start-Process -FilePath $pwsh -WindowStyle Hidden -ArgumentList $arguments -PassThru `
        -RedirectStandardOutput (Join-Path $ResultDirectory 'capture-output.txt') -RedirectStandardError (Join-Path $ResultDirectory 'capture-error.txt')
    $ready=$false
    for($i=0;$i -lt 100;$i++) {
        if ($captureProcess.HasExited) { throw 'Trace recorder exited before readiness.' }
        if (Test-Path -LiteralPath $captureRecord) {
            # The recorder may be writing the JSON when this read occurs.
            $trace=try { Read-TraceRecord } catch { $null }
            if ($trace.status -eq 'recording') { $ready=$true; break }
        }
        Start-Sleep -Milliseconds 200
    }
    if (-not $ready) { throw 'USB trace did not become ready within 20 seconds.' }
    $record.phase='trace recording; beginning one binding attempt'; Save-Run
    & (Join-Path $PSScriptRoot 'test-winusb-development.ps1') -Install -DevelopmentTrustApproved -ResultDirectory $ResultDirectory -TraceRecord $captureRecord
    $installed=Get-Content -LiteralPath (Join-Path $ResultDirectory 'winusb-development-test.json') -Raw | ConvertFrom-Json
    $record.installPhase=$installed.phase
    if (-not $installed.startSucceeded) { throw 'WinUSB did not start; endpoint and alternate-setting experiments were not attempted.' }
    if ($installed.startSucceeded) {
        $record.phase='started; descriptor-only probe'; Save-Run
        & (Join-Path $root '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'probe-winusb.py') (Join-Path $ResultDirectory 'probe.json')
        $record.probeExitCode=$LASTEXITCODE
        if ($record.probeExitCode -ne 0) { throw 'Initial read-only probe failed; do not change alternate settings.' }
        if ($ActivateAudioAlternates -or $QueryClock -or $CaptureAudio) {
            $trace=Read-TraceRecord
            $traceStart=if($trace.startedUtc -is [DateTime]){$trace.startedUtc.ToUniversalTime()}else{[DateTimeOffset]::Parse([string]$trace.startedUtc,[Globalization.CultureInfo]::InvariantCulture).UtcDateTime}
            if ($trace.status -ne 'recording' -or ([DateTime]::UtcNow-$traceStart).TotalSeconds -gt ($trace.plan.durationSeconds-25)) { throw 'Insufficient live trace window for the bounded alternate-setting experiment.' }
            $traceQuery=@(& logman.exe query $trace.session -ets 2>&1)
            if ($LASTEXITCODE -ne 0) { throw 'Trace session stopped before alternate selection.' }
            if($CaptureAudio){
                $build=Get-Content -LiteralPath (Join-Path $root 'artifacts/build/native/native-build-Release.json') -Raw|ConvertFrom-Json
                $experimentExe=Join-Path $root 'artifacts/build/native/Release/sl3_capture.exe'
                if((Get-FileHash -LiteralPath $experimentExe).Hash -ne $build.executableSha256 -or -not $build.coreTestsPassed -or -not $build.planOnlyPassed){throw 'Native capture build identity/verification changed'}
                foreach($inputFile in $build.inputs.PSObject.Properties){
                    if((Get-FileHash -LiteralPath (Join-Path $root $inputFile.Name)).Hash -ne $inputFile.Value){throw 'Native capture source differs from tested build; rebuild first'}
                }
                $experimentStem='native-capture'
                $experimentArgs=@('--capture','--output',('"{0}"' -f (Join-Path $ResultDirectory $experimentStem)))
                $record.phase='bounded native IN-only capture; no audio output'
            }else{
                $experimentExe=Join-Path $root '.venv/Scripts/python.exe'
                $experimentScript=if($QueryClock){'test-winusb-clock-query.py'}else{'test-winusb-audio-alternates.py'}
                $experimentFlag=if($QueryClock){'--query-rate'}else{'--activate'}
                $experimentStem=if($QueryClock){'clock-query'}else{'audio-alternates'}
                $record.phase=if($QueryClock){'querying current clock rate; no rate change or audio transfers'}else{'activating audio alternate settings; no audio transfers'}
                $experimentArgs=@(('"{0}"' -f (Join-Path $PSScriptRoot $experimentScript)),
                                  $experimentFlag,('"{0}"' -f (Join-Path $ResultDirectory "$experimentStem.json")))
            }
            Save-Run
            $experiment=Start-Process -FilePath $experimentExe -WindowStyle Hidden -ArgumentList $experimentArgs -PassThru `
                -RedirectStandardOutput (Join-Path $ResultDirectory "$experimentStem-output.txt") -RedirectStandardError (Join-Path $ResultDirectory "$experimentStem-error.txt")
            if (-not $experiment.WaitForExit(20000)) {
                $experiment.Kill($true)
                $record.alternateTestTimedOut=$true; Save-Run
                throw 'Experiment exceeded its 20-second deadline; targeted driver cleanup follows.'
            }
            if($CaptureAudio){$record.nativeCaptureExitCode=$experiment.ExitCode}elseif($QueryClock){$record.clockQueryExitCode=$experiment.ExitCode}else{$record.alternateTestExitCode=$experiment.ExitCode}
            if ($experiment.ExitCode -ne 0) { throw 'Bounded experiment reported a failure; inspect its record.' }
        }
    }
    $record.phase='binding attempt complete; waiting for trace'; Save-Run
} catch {
    $record.error=$_.Exception.Message
    $record.phase='binding/capture error; cleanup pending'; Save-Run
} finally {
    if ($captureProcess -and -not $captureProcess.HasExited) {
        # Recorder has its own 60-second timeout; bounded waits keep the log live.
        while (-not $captureProcess.WaitForExit(1000)) { }
    }
    $record.traceFinishedUtc=[DateTime]::UtcNow.ToString('o'); Save-Run
    try {
        if (Test-Path -LiteralPath (Join-Path $ResultDirectory 'winusb-development-test.json')) {
            & (Join-Path $PSScriptRoot 'cleanup-winusb-development.ps1') -Restore -ResultDirectory $ResultDirectory
            $record.cleanup='completed'
        } else { $record.cleanup='no installation record; no binding or trust import attempted' }
    } catch { $record.cleanup='failed'; $record.cleanupError=$_.Exception.Message }
    $record.secureBootAfter=Confirm-SecureBootUEFI
    $record.completedUtc=[DateTime]::UtcNow.ToString('o')
    $record.phase='finished; inspect trace and recovery state'; Save-Run
    Stop-Transcript | Out-Null
}
$record | ConvertTo-Json -Depth 8
