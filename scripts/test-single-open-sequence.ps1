#requires -Version 7.5
param([switch]$Run,[string]$ResultDirectory='tests/results/local/single-open-sequence-01',[string]$ValidatedCaptureRun)
# One owner-approved elevation for the existing three independently gated tests.
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if($ResultDirectory -match '["\r\n]'){throw 'Invalid result path'}
if(-not [IO.Path]::IsPathRooted($ResultDirectory)){$ResultDirectory=Join-Path $root $ResultDirectory}
$ResultDirectory=[IO.Path]::GetFullPath($ResultDirectory)
if($ValidatedCaptureRun){
    if($ValidatedCaptureRun -match '["\r\n]'){throw 'Invalid prior capture path'}
    if(-not [IO.Path]::IsPathRooted($ValidatedCaptureRun)){$ValidatedCaptureRun=Join-Path $root $ValidatedCaptureRun}
    $ValidatedCaptureRun=[IO.Path]::GetFullPath($ValidatedCaptureRun)
}
if(Test-Path -LiteralPath $ResultDirectory){throw 'Choose a fresh sequence directory'}
if(-not $Run){
    [ordered]@{planOnly=$true;resultDirectory=$ResultDirectory
        steps=@($(if($ValidatedCaptureRun){'Revalidate supplied same-worker input capture'}else{'Bounded native input capture'}),'Bounded zero-PCM duplex using that same-worker capture',
                'One-second single-open zero-PCM bridge using the freshly observed rate')
        rateChanges=$false;driverChanges=$false;securityChanges=$false;asioRegistration=$false
        retries=0;stopOnFirstFailure=$true;deviceAccess=$false}|ConvertTo-Json -Depth 4
    return
}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
if(-not ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Run from an elevated terminal'}
if(-not (Confirm-SecureBootUEFI)){throw 'Secure Boot must remain enabled'}
if(@(Get-CimInstance Win32_Process -Filter "Name='sl3_usbdk.exe' OR Name='sl3_host_probe.exe'").Count){throw 'A prior native test process remains'}
$worker=Join-Path $root 'artifacts/build/native/Release/sl3_usbdk.exe'
$probe=Join-Path $root 'artifacts/build/native/Release/sl3_host_probe.exe'
$workerHash=(Get-FileHash -LiteralPath $worker).Hash
$probeHash=(Get-FileHash -LiteralPath $probe).Hash
$capture=if($ValidatedCaptureRun){$ValidatedCaptureRun}else{Join-Path $ResultDirectory 'capture-run'}
$duplex=Join-Path $ResultDirectory 'duplex-run'
$bridge=Join-Path $ResultDirectory 'bridge-run'
New-Item -ItemType Directory -Path $ResultDirectory|Out-Null
$record=[ordered]@{schema='sl3.single-open-sequence.v1';startedUtc=[datetime]::UtcNow.ToString('o')
    completed=$false;error=$null;phase='capture';workerSha256=$workerHash;probeSha256=$probeHash
    capturePassed=$false;duplexPassed=$false;bridgePassed=$false;expectedRateHz=$null
    suppliedCapture=[bool]$ValidatedCaptureRun;captureRunRecordSha256=$null
    rateChanges=$false;driverChanges=$false;securityChanges=$false;asioRegistration=$false;retries=0;scriptHashes=[ordered]@{}}
foreach($name in @('test-single-open-sequence.ps1','test-usbdk-traced.ps1','test-host-probe-traced.ps1','read-startup-journal.ps1')){
    $record.scriptHashes[$name]=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name)).Hash
}
function Save-Sequence{$record|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $ResultDirectory 'sequence.json')}
function Check-Binaries{
    if((Get-FileHash -LiteralPath $worker).Hash -ne $workerHash -or (Get-FileHash -LiteralPath $probe).Hash -ne $probeHash){throw 'Tested binaries changed during sequence'}
}
function Check-Run([string]$Folder){
    $report=Get-Content -LiteralPath (Join-Path $Folder 'run.json') -Raw|ConvertFrom-Json
    if(-not $report.completed -or $report.error -or -not $report.recoveryConfirmed -or -not $report.secureBootAfter){throw 'Scenario or selected-state recovery failed'}
}
Save-Sequence
try{
    Check-Binaries
    if($ValidatedCaptureRun){
        $validation=& (Join-Path $root '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'validate-usbdk-capture.py') $capture --expected-native-sha256 $workerHash
        if($LASTEXITCODE -ne 0 -or ($validation|ConvertFrom-Json).valid -ne $true){throw 'Supplied same-worker capture failed consistency checks'}
    }else{
        & (Join-Path $PSScriptRoot 'test-usbdk-traced.ps1') -Run -Mode Capture -ResultDirectory $capture|Out-Null
    }
    Check-Run $capture;$record.capturePassed=$true
    $record.captureRunRecordSha256=(Get-FileHash -LiteralPath (Join-Path $capture 'run.json')).Hash
    $captured=Get-Content -LiteralPath (Join-Path $capture 'capture/capture.json') -Raw|ConvertFrom-Json
    $rate=[int]$captured.reported_rate_hz
    if($rate -notin @(44100,48000)){throw 'Capture did not report a supported device rate'}
    $record.expectedRateHz=$rate;$record.phase='silent-duplex';Save-Sequence;Check-Binaries
    & (Join-Path $PSScriptRoot 'test-usbdk-traced.ps1') -Run -Mode DuplexSilence -ResultDirectory $duplex -ValidatedCaptureRun $capture|Out-Null
    Check-Run $duplex;$record.duplexPassed=$true;$record.phase='single-open-bridge';Save-Sequence;Check-Binaries
    & (Join-Path $PSScriptRoot 'test-host-probe-traced.ps1') -Run -SingleOpenRate $rate -ResultDirectory $bridge -ValidatedCaptureRun $capture -ValidatedDuplexRun $duplex|Out-Null
    Check-Run $bridge;$record.bridgePassed=$true;$record.phase='finished';$record.completed=$true
}catch{$record.error=$_.Exception.Message}
finally{$record.completedUtc=[datetime]::UtcNow.ToString('o');Save-Sequence}
if($record.error){throw $record.error}
$record|ConvertTo-Json -Depth 6
