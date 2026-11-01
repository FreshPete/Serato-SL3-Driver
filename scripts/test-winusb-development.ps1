#requires -Version 7.0
param(
    [switch]$Install, [switch]$DevelopmentTrustApproved,
    [string]$ResultDirectory = 'tests/results/local',
    [string]$TraceRecord
)
# Dry-run by default. Installation is reserved for explicit owner approval of
# adding this exact prepared development certificate to machine trust stores.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$stage = Join-Path $root 'artifacts/build/sl3winusb-development'
$manifest = Get-Content -LiteralPath (Join-Path $stage 'development-package.json') -Raw | ConvertFrom-Json
foreach($file in @('sl3winusb.inf','sl3winusb.cat','sl3-winusb-development.cer')) {
    if ((Get-FileHash -LiteralPath (Join-Path $stage $file)).Hash -ne $manifest.files.$file) { throw "Prepared file changed: $file" }
}
$cert = [Security.Cryptography.X509Certificates.X509Certificate2]::new((Join-Path $stage 'sl3-winusb-development.cer'))
if ($cert.Thumbprint -ne $manifest.thumbprint -or $cert.NotAfter -le (Get-Date)) { throw 'Unexpected or expired development certificate.' }
if ($cert.Subject -ne 'CN=SL3 WinUSB Local Development Only') { throw 'Unexpected certificate subject.' }
Add-Type -AssemblyName System.Security.Cryptography.Pkcs
$cms = [Security.Cryptography.Pkcs.SignedCms]::new()
$cms.Decode([IO.File]::ReadAllBytes((Join-Path $stage 'sl3winusb.cat')))
$cms.CheckSignature($true) # Verify cryptographic integrity only; no trust import.
if ((Get-AuthenticodeSignature -LiteralPath (Join-Path $stage 'sl3winusb.cat')).SignerCertificate.Thumbprint -ne $cert.Thumbprint) { throw 'Unexpected catalogue signer.' }
$devices = @(Get-PnpDevice -PresentOnly | Where-Object InstanceId -like 'USB\VID_1CC5&PID_0001\*')
if ($devices.Count -ne 1) { throw 'Exactly one connected SL3 is required.' }
$device = $devices[0]
$originalInf = (Get-PnpDeviceProperty -InstanceId $device.InstanceId -KeyName DEVPKEY_Device_DriverInfPath).Data
if ($originalInf -notmatch '^oem\d+\.inf$') { throw 'Expected original OEM driver binding before the test.' }
$originalPath = Join-Path $env:SystemRoot "INF/$originalInf"
$originalText = Get-Content -LiteralPath $originalPath -Raw
if ($originalText -notmatch 'Rane Corporation' -or $originalText -notmatch 'USB\\VID_1CC5&PID_0001') { throw 'Current OEM package is not the original Rane SL3 package.' }
$plan = [ordered]@{certificateSubject=$cert.Subject;thumbprint=$cert.Thumbprint;expiresUtc=$cert.NotAfter.ToUniversalTime().ToString('o');stores=@('LocalMachine/Root','LocalMachine/TrustedPublisher');deviceInstanceId=$device.InstanceId;originalInf=$originalInf;originalInfSha256=(Get-FileHash -LiteralPath $originalPath).Hash;action='Stage and bind only the SL3-specific WinUSB INF; no boot-policy change, firmware request or automatic reboot.'}
if (-not $Install) { $plan | ConvertTo-Json -Depth 4; exit }
if (-not $DevelopmentTrustApproved) { throw 'Explicit approval of local development certificate trust is required.' }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'An elevated terminal is required.' }
if (-not [IO.Path]::IsPathRooted($ResultDirectory)) { $ResultDirectory=Join-Path $root $ResultDirectory }
$resultPath = Join-Path $ResultDirectory 'winusb-development-test.json'
if (Test-Path -LiteralPath $resultPath) { throw 'A development test record already exists; inspect it before repeating or use cleanup.' }
New-Item -ItemType Directory -Force -Path (Split-Path $resultPath) | Out-Null
Start-Transcript -Path (Join-Path $ResultDirectory 'winusb-development-test.log') | Out-Null
$record = [ordered]@{startedUtc=[DateTime]::UtcNow.ToString('o');plan=$plan;addedStores=@();phase='before trust';publishedInf=$null;needReboot=$false}
function Save-Record { $record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $resultPath -Encoding utf8 }
function Assert-TraceRecording {
    if (-not $TraceRecord) { return }
    $stream=[IO.FileStream]::new($TraceRecord,[IO.FileMode]::Open,[IO.FileAccess]::Read,([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
    $reader=[IO.StreamReader]::new($stream)
    try { $trace=$reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
    if ($trace.status -ne 'recording' -or $trace.session -notmatch '^SL3Startup-[0-9a-f]{32}$') { throw 'Expected USB startup trace is not recording.' }
    # PowerShell 7 may deserialize ISO timestamps directly into DateTime objects.
    # Avoid converting them to a locale-dependent string and parsing it again.
    $traceStart=if($trace.startedUtc -is [DateTime]){$trace.startedUtc.ToUniversalTime()}else{[DateTimeOffset]::Parse([string]$trace.startedUtc,[Globalization.CultureInfo]::InvariantCulture).UtcDateTime}
    $elapsed=([DateTime]::UtcNow-$traceStart).TotalSeconds
    if ($elapsed -gt ($trace.plan.durationSeconds-10)) { throw 'Too little trace time remains to begin binding.' }
    $query=@(& logman.exe query $trace.session -ets 2>&1)
    if ($LASTEXITCODE -ne 0) { throw 'USB ETW session is not running.' }
    $record.traceSession=$trace.session
    $record.traceCheckedUtc=[DateTime]::UtcNow.ToString('o')
    Save-Record
}
Save-Record
try {
    $record.secureBootBefore=Confirm-SecureBootUEFI
    if (-not $record.secureBootBefore) { throw 'Secure Boot is not enabled; this test will not alter it.' }
    Save-Record
    Assert-TraceRecording
    & (Join-Path $PSScriptRoot 'collect-windows-state.ps1') -Output (Join-Path $ResultDirectory 'before-winusb-development.json')
    foreach($store in @('Cert:\LocalMachine\Root','Cert:\LocalMachine\TrustedPublisher')) {
        if (-not (Test-Path -LiteralPath "$store\$($cert.Thumbprint)")) {
            Import-Certificate -FilePath (Join-Path $stage 'sl3-winusb-development.cer') -CertStoreLocation $store | Out-Null
            $record.addedStores += $store
            Save-Record
        }
    }
    $record.phase='trust imported'; Save-Record
    $signature = Get-AuthenticodeSignature -LiteralPath (Join-Path $stage 'sl3winusb.cat')
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Thumbprint -ne $cert.Thumbprint) { throw "Catalogue not trusted after import: $($signature.Status)" }
    Assert-TraceRecording
    $record.bindingRequestedUtc=[DateTime]::UtcNow.ToString('o'); Save-Record
    & pnputil.exe /add-driver (Join-Path $stage 'sl3winusb.inf') /install
    if ($LASTEXITCODE -notin @(0,3010)) { throw "PnPUtil failed with exit $LASTEXITCODE" }
    if ($LASTEXITCODE -eq 3010) { $record.needReboot=$true }
    $record.phase='package staged'; Save-Record
    $service = (Get-PnpDeviceProperty -InstanceId $device.InstanceId -KeyName DEVPKEY_Device_Service).Data
    if ($service -ne 'WINUSB') {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class Sl3ExactDriverUpdate {
 [DllImport("newdev.dll",CharSet=CharSet.Unicode,SetLastError=true)]
 public static extern bool UpdateDriverForPlugAndPlayDevicesW(IntPtr parent,string hardwareId,string fullInfPath,uint flags,out bool needReboot);
}
'@
        $restart=$false
        if (-not [Sl3ExactDriverUpdate]::UpdateDriverForPlugAndPlayDevicesW([IntPtr]::Zero,'USB\VID_1CC5&PID_0001',(Join-Path $stage 'sl3winusb.inf'),1,[ref]$restart)) {
            throw [ComponentModel.Win32Exception]::new([Runtime.InteropServices.Marshal]::GetLastWin32Error())
        }
        $record.needReboot=$record.needReboot -or $restart
    }
    $record.publishedInf=(Get-PnpDeviceProperty -InstanceId $device.InstanceId -KeyName DEVPKEY_Device_DriverInfPath).Data
    $record.service=(Get-PnpDeviceProperty -InstanceId $device.InstanceId -KeyName DEVPKEY_Device_Service).Data
    & (Join-Path $PSScriptRoot 'collect-windows-state.ps1') -Output (Join-Path $ResultDirectory 'after-winusb-development.json')
    $present=@(Get-PnpDevice -PresentOnly | Where-Object InstanceId -eq $device.InstanceId)
    $node=Get-PnpDevice -InstanceId $device.InstanceId
    $record.devicePresent=($present.Count -eq 1)
    $record.problemCode=[int]$node.Problem
    $record.pnpStatus=$node.Status
    $record.startSucceeded=($record.devicePresent -and $record.problemCode -eq 0 -and $record.service -eq 'WINUSB')
    $record.phase=if($record.startSucceeded){'started; endpoint probing is a separate test'}else{'configured; device did not start or is absent'}
    $record.secureBootAfter=Confirm-SecureBootUEFI
    Save-Record
} catch {
    $record.error=$_.Exception.Message
    $record.phase='failed; inspect record and transcript; use targeted cleanup'
    Save-Record
    throw
} finally { Stop-Transcript | Out-Null }
Get-Content -LiteralPath $resultPath
