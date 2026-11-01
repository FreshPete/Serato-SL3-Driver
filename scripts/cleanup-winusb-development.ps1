param([switch]$Restore, [string]$ResultDirectory = 'tests/results/local')
# Default reports the proposed cleanup. Restores the captured Rane binding and
# removes only the exact development package/certificate introduced by our test.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$stage = Join-Path $root 'artifacts/build/sl3winusb-development'
$manifest = Get-Content -LiteralPath (Join-Path $stage 'development-package.json') -Raw | ConvertFrom-Json
if (-not [IO.Path]::IsPathRooted($ResultDirectory)) { $ResultDirectory=Join-Path $root $ResultDirectory }
$testPath = Join-Path $ResultDirectory 'winusb-development-test.json'
if (-not (Test-Path -LiteralPath $testPath)) { throw 'No installation test record exists; no trust or binding cleanup is needed.' }
$test = Get-Content -LiteralPath $testPath -Raw | ConvertFrom-Json
if ($test.plan.thumbprint -ne $manifest.thumbprint) { throw 'Test and package identities differ.' }
$original = Join-Path $env:SystemRoot "INF/$($test.plan.originalInf)"
if ($test.plan.originalInf -notmatch '^oem\d+\.inf$' -or
    (Get-FileHash -LiteralPath $original).Hash -ne '7191f7c6fd5fda7503eb9eabee2522868a9d1f2ddd766fe6dc9145d6c69e8f76') { throw 'Original Rane package identity changed; stop and inspect.' }
$ours = @(Get-ChildItem -LiteralPath (Join-Path $env:SystemRoot 'INF') -Filter 'oem*.inf' -File |
    Where-Object { (Get-FileHash -LiteralPath $_.FullName).Hash -eq $manifest.files.'sl3winusb.inf' })
if ($ours.Count -gt 1) { throw 'Multiple matching development packages found; inspect before removal.' }
$plan = [ordered]@{originalInf=$test.plan.originalInf;removePackage=@($ours | ForEach-Object Name);removeCertificate=$manifest.thumbprint;onlyStoresAddedByTest=@($test.addedStores);signingIdentityPresent=(Test-Path -LiteralPath "Cert:\CurrentUser\My\$($manifest.thumbprint)");note='Original Rane driver was blocked before this experiment; restoring it is expected to restore code 39. No reboot is automated. This script does not delete a My-store signing key; identity retention is checked separately.'}
if (-not $Restore) { $plan | ConvertTo-Json -Depth 5; exit }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'An elevated terminal is required.' }
$devices = @(Get-PnpDevice -PresentOnly | Where-Object InstanceId -like 'USB\VID_1CC5&PID_0001\*')
if ($devices.Count -gt 1) { throw 'More than one SL3 is connected.' }
if ($devices.Count -eq 1) {
    $current=(Get-PnpDeviceProperty -InstanceId $devices[0].InstanceId -KeyName DEVPKEY_Device_DriverInfPath).Data
    $restart=$false
    if ($current -ne $test.plan.originalInf) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class Sl3OriginalDriverRestore {
 [DllImport("newdev.dll",CharSet=CharSet.Unicode,SetLastError=true)]
 public static extern bool UpdateDriverForPlugAndPlayDevicesW(IntPtr parent,string hardwareId,string fullInfPath,uint flags,out bool needReboot);
}
'@
        $ok=[Sl3OriginalDriverRestore]::UpdateDriverForPlugAndPlayDevicesW([IntPtr]::Zero,'USB\VID_1CC5&PID_0001',$original,1,[ref]$restart)
        $current=(Get-PnpDeviceProperty -InstanceId $devices[0].InstanceId -KeyName DEVPKEY_Device_DriverInfPath).Data
        if (-not $ok -and $current -ne $test.plan.originalInf) { throw 'Could not restore the original binding; development package/trust retained for inspection.' }
    }
    $plan.needReboot=$restart
}
# Also remove our GUID from the exact recorded devnode if startup made it absent.
$instance=if($test.plan.deviceInstanceId){$test.plan.deviceInstanceId}elseif($devices.Count -eq 1){$devices[0].InstanceId}else{$null}
if ($instance) {
    if ($instance -notlike 'USB\VID_1CC5&PID_0001\*') { throw 'Unexpected device identity in test record.' }
    $key="HKLM:\SYSTEM\CurrentControlSet\Enum\$instance\Device Parameters"
    $guids=@((Get-ItemProperty -LiteralPath $key -Name DeviceInterfaceGUIDs -ErrorAction SilentlyContinue).DeviceInterfaceGUIDs | Where-Object { $_ })
    $projectGuid='{45DFC124-470C-4C58-BA2B-BFF7614A64BC}'
    if ($guids -contains $projectGuid) {
        $remaining=@($guids | Where-Object { $_ -ne $projectGuid })
        if ($remaining.Count) {
            New-ItemProperty -LiteralPath $key -Name DeviceInterfaceGUIDs -PropertyType MultiString -Value $remaining -Force | Out-Null
        } else {
            Remove-ItemProperty -LiteralPath $key -Name DeviceInterfaceGUIDs
        }
        $plan.projectInterfaceGuidRemoved=$true
    }
}
foreach($inf in $ours) {
    & pnputil.exe /delete-driver $inf.Name /uninstall
    if ($LASTEXITCODE -notin @(0,3010)) { throw "Could not remove development package $($inf.Name); certificate retained." }
}
foreach($store in @($test.addedStores)) {
    if ($store -notin @('Cert:\LocalMachine\Root','Cert:\LocalMachine\TrustedPublisher')) { throw 'Unexpected trust store in test record.' }
    $path="$store\$($manifest.thumbprint)"
    if (Test-Path -LiteralPath $path) {
        $cert=Get-Item -LiteralPath $path
        if ($cert.Subject -ne 'CN=SL3 WinUSB Local Development Only') { throw 'Certificate identity changed.' }
        Remove-Item -LiteralPath $path
    }
}
$plan.completedUtc=[DateTime]::UtcNow.ToString('o')
$plan | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $ResultDirectory 'winusb-development-cleanup.json') -Encoding utf8
$plan | ConvertTo-Json -Depth 5
