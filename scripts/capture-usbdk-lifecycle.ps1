# Passive WPP sidecar only. Does not load the helper or launch a USB scenario.
# Existing reviewed USB-stack tracing remains separate and unchanged.
#requires -Version 7.5
param([switch]$Capture,[ValidateRange(5,60)][int]$DurationSeconds=30,
      [string]$OutputDirectory='tests/results/local/usbdk-lifecycle-trace')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$python=Join-Path $root '.venv/Scripts/python.exe'
$prepare=Join-Path $PSScriptRoot 'prepare-usbdk-lifecycle-trace.py'
$checked=& $python $prepare
if($LASTEXITCODE -ne 0){throw 'Pinned lifecycle decoder/source check failed'}
$checked=$checked|ConvertFrom-Json
if(-not [IO.Path]::IsPathRooted($OutputDirectory)){$OutputDirectory=Join-Path $root $OutputDirectory}
$OutputDirectory=[IO.Path]::GetFullPath($OutputDirectory)
if($OutputDirectory -match '["\r\n]'){throw 'Invalid output path'}
$plan=[ordered]@{planOnly=(-not $Capture);durationSeconds=$DurationSeconds;maximumFileMiB=64
    provider=$checked.providerGuid;flags=$checked.flags;level=$checked.level
    outputDirectory=$OutputDirectory;deviceAccess=$false;helperLoaded=$false
    startsAudio=$false;installsDriver=$false;securityChanges=$false
    decoderSourceCheck=$checked;scope='Passive UsbDk WPP sidecar; not a device test or readiness gate'}
if(-not $Capture){$plan|ConvertTo-Json -Depth 10;return}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
if(-not ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
    throw 'Run passive capture from an already elevated terminal; this script does not elevate itself'
}
if(-not (Confirm-SecureBootUEFI)){throw 'Secure Boot must remain enabled'}
$driver=@(Get-CimInstance Win32_SystemDriver -Filter "Name='UsbDk'")
if($driver.Count -ne 1 -or $driver[0].State -ne 'Running'){throw 'Reviewed UsbDk must already be running'}
$installed=[Environment]::ExpandEnvironmentVariables($driver[0].PathName.Trim('"'))
if($installed.StartsWith('\SystemRoot\')){$installed=Join-Path $env:SystemRoot $installed.Substring(12)}
if(-not [IO.Path]::IsPathRooted($installed) -or (Get-FileHash -LiteralPath $installed).Hash -ne $checked.driverSha256){
    throw 'Running-service driver path/hash differs from reviewed signed image'
}
if(Test-Path -LiteralPath $OutputDirectory){throw 'Choose a fresh output directory'}
$null=& $python $prepare --prepare $OutputDirectory
if($LASTEXITCODE -ne 0){throw 'Decoder preparation failed'}
$session='SL3UsbDkLifecycle-'+[Guid]::NewGuid().ToString('N')
$record=[ordered]@{schema='sl3.usbdk-lifecycle-trace.v1';plan=$plan;session=$session
    status='preparing';commands=@();startedUtc=$null;stoppedUtc=$null;error=$null
    captureScriptSha256=(Get-FileHash -LiteralPath $PSCommandPath).Hash
    decoderScriptSha256=(Get-FileHash -LiteralPath $prepare).Hash}
$manifest=Join-Path $OutputDirectory 'capture.json'
function Save-Record {
    [IO.File]::WriteAllText($manifest,($record|ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
}
function Invoke-Logman([string[]]$Arguments){
    $lines=@(& logman.exe @Arguments 2>&1);$code=$LASTEXITCODE
    $record.commands+=@([ordered]@{arguments=$Arguments;exitCode=$code;output=($lines -join "`n")})
    Save-Record
    if($code -ne 0){throw "Lifecycle trace command failed: $($Arguments[0]), exit $code"}
}
$created=$false;$started=$false
Save-Record
try{
    Invoke-Logman @('create','trace','-n',$session,'-o',(Join-Path $OutputDirectory 'usbdk-lifecycle.etl'),
        '-f','bincirc','-max','64','-nb','16','64','-bs','128',
        '-rf',([TimeSpan]::FromSeconds($DurationSeconds).ToString('hh\:mm\:ss')))
    $created=$true
    Invoke-Logman @('update','trace','-n',$session,'-p',('{'+$checked.providerGuid+'}'),$checked.flags,([string]$checked.level))
    Invoke-Logman @('start','-n',$session)
    $started=$true;$record.startedUtc=[datetime]::UtcNow.ToString('o');$record.status='recording';Save-Record
    Start-Sleep -Seconds $DurationSeconds
    $record.status='window completed'
}catch{$record.error=$_.Exception.Message;$record.status='failed';throw}
finally{
    # A successful create must be cleaned even if the following manifest write failed.
    $created=$created -or (@($record.commands|Where-Object {$_.arguments[0] -eq 'create' -and $_.exitCode -eq 0}).Count -gt 0)
    $started=$started -or (@($record.commands|Where-Object {$_.arguments[0] -eq 'start' -and $_.exitCode -eq 0}).Count -gt 0)
    if($started){try{Invoke-Logman @('stop','-n',$session)}catch{$record.stopNote=$_.Exception.Message}}
    if($created){try{Invoke-Logman @('delete','-n',$session)}catch{$record.cleanupError=$_.Exception.Message;$record.status='cleanup requires attention'}}
    $record.stoppedUtc=[datetime]::UtcNow.ToString('o')
    $record.files=@(Get-ChildItem -LiteralPath $OutputDirectory -Filter '*.etl'|ForEach-Object {
        [ordered]@{name=$_.Name;bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName).Hash}
    })
    Save-Record
}
$record|ConvertTo-Json -Depth 12
