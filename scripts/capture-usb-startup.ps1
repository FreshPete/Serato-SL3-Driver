param(
    [switch]$Capture,
    [switch]$WithUsbDkLifecycle,
    [switch]$WithStateObserver,
    [ValidateRange(5,60)][int]$DurationSeconds = 30,
    [string]$OutputDirectory = 'tests/results/local/usb-startup-trace'
)
# Passive ETW only. Never installs a driver, restarts a device, imports trust,
# issues USB requests, changes power policy, or starts a hardware scenario.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if($OutputDirectory -match '["\r\n]' -or $OutputDirectory.StartsWith('\\')){throw 'Local capture path without quotes/newlines required'}
if($WithStateObserver -and -not $WithUsbDkLifecycle){throw 'State observation requires the reviewed shared USB/WPP mode'}
$providers = @('Microsoft-Windows-USB-USBHUB3','Microsoft-Windows-USB-UCX','Microsoft-Windows-USB-USBXHCI')
$keywords = '0x281' # Default | PartialDataBusTrace | StateMachine
$metadata = foreach ($provider in $providers) {
    $result = @(& logman.exe query providers $provider 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "USB trace provider unavailable: $provider" }
    foreach ($entry in @(@('Default','0000000000000001'),@('PartialDataBusTrace','0000000000000080'),@('StateMachine','0000000000000200'))) {
        if (($result -join "`n") -notmatch "0x$($entry[1])\s+$($entry[0])\b") { throw "Provider keyword mismatch: $($entry[0]) : $provider" }
    }
    [ordered]@{name=$provider;description=($result -join "`n")}
}
$plan = [ordered]@{
    durationSeconds=$DurationSeconds; maximumFileMiB=64; keywords=$keywords
    logFormat='bin'; circularOverwriteAllowed=$false; failAtFileCapacity=$true
    providers=$providers; scope='All devices on the USB 3 host stack; keep raw trace local. Includes limited transfer payload.'
    action='Record a bounded passive USB trace only. A separately authorized startup scenario must occur during the capture window.'
}
$lifecycle=$null
if($WithUsbDkLifecycle){
    $python=Join-Path $root '.venv/Scripts/python.exe'
    $prepare=Join-Path $PSScriptRoot 'prepare-usbdk-lifecycle-trace.py'
    $checked=& $python $prepare
    if($LASTEXITCODE -ne 0){throw 'Pinned UsbDk lifecycle source/decoder check failed'}
    $lifecycle=$checked|ConvertFrom-Json
    $plan.lifecycle=[ordered]@{provider=$lifecycle.providerGuid;flags=$lifecycle.flags;level=$lifecycle.level
        driverSha256=$lifecycle.driverSha256;selectedTmfSha256=$lifecycle.selectedTmfSha256;emissionVerified=$false}
}
$plan.withUsbDkLifecycle=[bool]$WithUsbDkLifecycle
$plan.withStateObserver=[bool]$WithStateObserver
$plan.realTimeDelivery=[bool]$WithStateObserver
if (-not $Capture) { $plan | ConvertTo-Json -Depth 5; return }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'An elevated terminal is required to record USB ETW.'
}
if($WithUsbDkLifecycle){
    if(-not (Confirm-SecureBootUEFI)){throw 'Secure Boot must remain enabled'}
    $drivers=@(Get-CimInstance Win32_SystemDriver -Filter "Name='UsbDk'")
    if($drivers.Count -ne 1 -or $drivers[0].State -ne 'Running'){throw 'Reviewed UsbDk must already be running'}
    $installed=[Environment]::ExpandEnvironmentVariables($drivers[0].PathName.Trim('"'))
    if($installed -match '^\\\?\?\\[A-Za-z]:\\'){$installed=$installed.Substring(4)}
    if($installed.StartsWith('\SystemRoot\')){$installed=Join-Path $env:SystemRoot $installed.Substring(12)}
    if(-not [IO.Path]::IsPathRooted($installed) -or (Get-FileHash -LiteralPath $installed).Hash -ne $lifecycle.driverSha256){
        throw 'Running-service driver differs from reviewed lifecycle image'
    }
}
$observerContract=$null
if($WithStateObserver){
    $observerValidator=Join-Path $PSScriptRoot 'validate-usb-state-capture.py'
    $contractText=& $python $observerValidator --preflight
    if($LASTEXITCODE -ne 0){throw "Reviewed observer unavailable: $contractText"}
    $observerContract=$contractText|ConvertFrom-Json
    Import-Module (Join-Path $PSScriptRoot 'inspect-process.psm1')
}
if (-not [IO.Path]::IsPathRooted($OutputDirectory)) { $OutputDirectory = Join-Path $root $OutputDirectory }
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Choose a new output directory; existing captures are never overwritten.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$session = 'SL3Startup-' + [Guid]::NewGuid().ToString('N')
$record = [ordered]@{plan=$plan;session=$session;startedUtc=$null;stoppedUtc=$null;status='preparing';providers=$metadata;commands=@()}
$collector=Get-Process -Id $PID
$record.collectorPid=$PID
$record.collectorCreationFileTimeUtc=$collector.StartTime.ToFileTimeUtc().ToString()
$record.collectorImagePath=$collector.Path
$record.producerSha256=(Get-FileHash -LiteralPath $PSCommandPath).Hash
$manifest = Join-Path $OutputDirectory 'capture.json'
function Save-Record {
    $json=$record | ConvertTo-Json -Depth 8
    for($attempt=0;$attempt -lt 10;$attempt++) {
        try { [IO.File]::WriteAllText($manifest,$json,[Text.UTF8Encoding]::new($false)); return }
        catch [IO.IOException] { if($attempt -eq 9){throw}; Start-Sleep -Milliseconds 50 }
    }
}
function Invoke-Logman([string[]]$Arguments) {
    $lines = @(& logman.exe @Arguments 2>&1)
    $code = $LASTEXITCODE
    $record.commands += [ordered]@{arguments=$Arguments;exitCode=$code;output=($lines -join "`n")}
    Save-Record
    if ($code -ne 0) { throw "USB trace command failed with exit $code : $($Arguments -join ' ')" }
}
function Get-Sl3Nodes {
    @(Get-PnpDevice -PresentOnly | Where-Object {
        $_.InstanceId -like 'USB\VID_1CC5&PID_0001\*' -or $_.InstanceId -like 'USB\VID_0000&PID_0002\*'
    } | Select-Object InstanceId,FriendlyName,Status,Problem)
}
function Hub-Image{
    $path=Join-Path $env:SystemRoot 'System32/drivers/USBHUB3.SYS';$item=Get-Item -LiteralPath $path
    $signature=Get-AuthenticodeSignature -LiteralPath $path
    [ordered]@{path=$item.FullName;sha256=(Get-FileHash -LiteralPath $path).Hash;fileVersion=$item.VersionInfo.FileVersion
        signatureStatus=$signature.Status.ToString();signer=$signature.SignerCertificate.Subject;loadedImageIdentityVerified=$false}
}
$observer=$null
$created=$false
$started=$false
try {
    $hubBefore=$null;if($WithStateObserver){$hubBefore=Hub-Image}
    if($WithUsbDkLifecycle){
        $decoder=Join-Path $OutputDirectory 'lifecycle-decoder'
        $null=& $python $prepare --prepare $decoder
        if($LASTEXITCODE -ne 0){throw 'Lifecycle decoder preparation failed'}
        $record.lifecycleDecoder=[ordered]@{sourceSha256=(Get-FileHash -LiteralPath $prepare).Hash
            planSha256=(Get-FileHash -LiteralPath (Join-Path $decoder 'plan.json')).Hash
            tmfSha256=(Get-FileHash -LiteralPath (Join-Path $decoder 'lifecycle.tmf')).Hash}
        if($record.lifecycleDecoder.tmfSha256 -ne $lifecycle.selectedTmfSha256){throw 'Prepared lifecycle decoder differs'}
    }
    $record.beforeNodes=Get-Sl3Nodes
    Save-Record
    $createArgs=@('create','trace','-n',$session,'-o',(Join-Path $OutputDirectory 'usb-startup.etl'),'-f','bin','-max','64','-nb','16','64','-bs','128','-rf',([TimeSpan]::FromSeconds($DurationSeconds).ToString('hh\:mm\:ss')))
    if($WithStateObserver){$createArgs+=@('-rt','-ft','00:00:01')}
    Invoke-Logman -Arguments $createArgs
    $created=$true
    foreach ($provider in $providers) { Invoke-Logman -Arguments @('update','trace','-n',$session,'-p',$provider,$keywords,'5') }
    if($WithUsbDkLifecycle){
        Invoke-Logman -Arguments @('update','trace','-n',$session,'-p',('{'+$lifecycle.providerGuid+'}'),$lifecycle.flags,([string]$lifecycle.level))
    }
    $record.startRequestedUtc=[DateTime]::UtcNow.ToString('o'); Save-Record
    Invoke-Logman -Arguments @('start','-n',$session)
    $started=$true
    $record.startedUtc=[DateTime]::UtcNow.ToString('o')
    $window=[Diagnostics.Stopwatch]::StartNew()
    if($WithStateObserver){
        $record.status='starting state consumer'
        $record.stateObserver=[ordered]@{buildManifestSha256=$observerContract.buildManifestSha256
            observerManifestSha256=$observerContract.observerManifestSha256;executableSha256=$observerContract.executableSha256
            consumerAttemptVerified=$false;readinessAdmission=$false;startedUtc=[datetime]::UtcNow.ToString('o');hubImageBefore=$hubBefore}
        Save-Record
        $observerOutput=Join-Path $OutputDirectory 'state-observer.ndjson'
        $observer=Start-Process -FilePath $observerContract.executable -ArgumentList @('--session',$session,'--seconds',[string]$DurationSeconds,'--output',('"'+$observerOutput+'"')) -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $OutputDirectory 'observer-output.txt') -RedirectStandardError (Join-Path $OutputDirectory 'observer-error.txt')
        $record.stateObserver.process=Get-Sl3ProcessEvidence -ProcessId $observer.Id -WithToken
        $end=[datetime]::UtcNow.AddSeconds(2);$header=$null
        do{
            if($observer.HasExited){throw 'State consumer exited before the capture admission window'}
            try{
                $stream=[IO.File]::Open($observerOutput,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
                try{$bytes=[byte[]]::new(4096);$count=$stream.Read($bytes,0,$bytes.Length);$text=[Text.Encoding]::UTF8.GetString($bytes,0,$count)
                    $newline=$text.IndexOf("`n");if($newline -ge 0){$header=$text.Substring(0,$newline)|ConvertFrom-Json}
                }finally{$stream.Dispose()}
            }catch{$header=$null}
            if($header){break};Start-Sleep -Milliseconds 20
        }while([datetime]::UtcNow -lt $end)
        if(-not $header -or $header.mode -ne 'session' -or $header.sourceSession -ne $session -or $header.pid -ne $observer.Id -or
           $header.tokenQueried -ne $true -or $header.elevated -ne $true){throw 'Consumer attempt/header could not be verified'}
        # A header is not evidence that ProcessTrace received an event.
        $record.stateObserver.consumerAttemptVerified=$true
    }
    $record.status='recording'; Save-Record
    Write-Host "USB trace recording for $DurationSeconds seconds. No device action is performed by this script."
    if($WithStateObserver){$remaining=[math]::Max(0,$DurationSeconds*1000-$window.ElapsedMilliseconds);Start-Sleep -Milliseconds $remaining}
    else{Start-Sleep -Seconds $DurationSeconds}
    $record.status='window completed'
} catch {
    $record.status='failed'
    $record.error=$_.Exception.Message
    throw
} finally {
    # Stop/delete only the uniquely named session created by this invocation.
    # The -rf setting also bounds capture if this process is interrupted.
    # A manifest write can fail after logman creates the session but before the
    # caller sets its flag. The recorded successful create still proves ownership.
    $created=$created -or (@($record.commands | Where-Object { $_.arguments[0] -eq 'create' -and $_.exitCode -eq 0 }).Count -gt 0)
    if ($started) {
        try { Invoke-Logman -Arguments @('stop','-n',$session) }
        catch { $record.stopNote=$_.Exception.Message } # May already have hit -rf.
    }
    if ($created) {
        try { Invoke-Logman -Arguments @('delete','-n',$session) }
        catch { $record.deleteError=$_.Exception.Message; $record.status='cleanup requires attention' }
    }
    if($observer){
        try{
            if(-not $observer.WaitForExit(5000)){
                $record.stateObserver.containmentRequested=$true;$observer.Kill($true);$null=$observer.WaitForExit(5000)
                throw 'State consumer failed its bounded drain; source capture is preserved'
            }
            $observer.WaitForExit();$record.stateObserver.exitCode=$observer.ExitCode
            $record.stateObserver.completedUtc=[datetime]::UtcNow.ToString('o')
            $record.stateObserver.outputSha256=(Get-FileHash -LiteralPath $observerOutput).Hash
            $record.stateObserver.hubImageAfter=Hub-Image
            if($observer.ExitCode -ne 0){throw 'Live state consumer failed; do not infer readiness'}
        }catch{$record.observerError=$_.Exception.Message;$record.status='failed';if(-not $record.error){$record.error=$_.Exception.Message}}
    }
    $record.stoppedUtc=[DateTime]::UtcNow.ToString('o')
    $record.afterNodes=Get-Sl3Nodes
    $record.files=@(Get-ChildItem -LiteralPath $OutputDirectory -Filter '*.etl' | ForEach-Object {
        [ordered]@{name=$_.Name;bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName).Hash}
    })
    if(@($record.files | Where-Object {$_.bytes -ge 64*1024*1024}).Count){
        $record.status='failed'
        $record.error='Trace reached its file capacity; full-window evidence is not established'
    }
    Save-Record
}
if($record.status -eq 'failed'){throw $record.error}
if($WithStateObserver){
    if($record.status -ne 'window completed'){throw 'State observer/source capture did not complete cleanly'}
    $checked=& $python $observerValidator --capture $OutputDirectory
    $checked|Set-Content -LiteralPath (Join-Path $OutputDirectory 'state-observer-validation.json')
    if($LASTEXITCODE -ne 0){$record.status='failed';$record.error='State-consumer consistency validation failed';Save-Record;throw $record.error}
    $record.stateObserver.validationSha256=(Get-FileHash -LiteralPath (Join-Path $OutputDirectory 'state-observer-validation.json')).Hash;Save-Record
}
$record | ConvertTo-Json -Depth 8
