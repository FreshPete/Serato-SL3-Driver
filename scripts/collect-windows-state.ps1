param([string]$Output = 'tests/results/local/windows-state.json')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not [IO.Path]::IsPathRooted($Output)) { $Output = Join-Path $root $Output }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Output) | Out-Null
$devices = @(Get-PnpDevice -PresentOnly | Where-Object {
    $_.InstanceId -match '^USB\\VID_1CC5&PID_0001' -or $_.FriendlyName -match '^Rane.*SL.?3$|^SL 3$'
})
$deviceRows = @(foreach ($device in $devices) {
    [ordered]@{
        device = $device | Select-Object Status,Class,FriendlyName,InstanceId,Problem
        properties = @(Get-PnpDeviceProperty -InstanceId $device.InstanceId | Where-Object {
            $_.KeyName -match 'HardwareIds|CompatibleIds|ProblemCode|DriverInfPath|DriverVersion|Service|MatchingDeviceId'
        } | Select-Object KeyName,Data)
    }
})
$secureBoot = try { Confirm-SecureBootUEFI } catch { 'Unavailable: ' + $_.Exception.Message }
$deviceGuard = try {
    Get-CimInstance -Namespace root\Microsoft\Windows\DeviceGuard -ClassName Win32_DeviceGuard |
        Select-Object VirtualizationBasedSecurityStatus,SecurityServicesConfigured,SecurityServicesRunning
} catch { @{error=$_.Exception.Message} }
$hvci = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity' -ErrorAction SilentlyContinue
$app = Get-Item 'C:\Program Files\Serato\Serato DJ Pro\Serato DJ Pro.exe' -ErrorAction SilentlyContinue
$asio = foreach ($key in @('HKLM:\SOFTWARE\ASIO\Rane SL 3', 'HKLM:\SOFTWARE\WOW6432Node\ASIO\Rane SL 3')) {
    if (Test-Path $key) { Get-ItemProperty $key | Select-Object PSPath,CLSID,Description }
}
$events = @(Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-CodeIntegrity/Operational'; StartTime=(Get-Date).AddHours(-2)} -ErrorAction SilentlyContinue |
    Where-Object Message -match 'strmdrv|RaneAsio|Rane SL' | Select-Object TimeCreated,Id,LevelDisplayName,Message)
[ordered]@{
    collectedUtc = [DateTime]::UtcNow.ToString('o')
    os = Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,OSArchitecture
    cpu = Get-CimInstance Win32_Processor | Select-Object Name,Architecture
    secureBoot = $secureBoot
    deviceGuard = $deviceGuard
    hvciRegistry = if($hvci) { $hvci | Select-Object Enabled,Locked } else { 'Key absent; use DeviceGuard running services to determine runtime state' }
    devices = $deviceRows
    asio = @($asio)
    application = if($app) { @{path=$app.FullName;version=$app.VersionInfo.FileVersion;sha256=(Get-FileHash -LiteralPath $app.FullName).Hash} } else { $null }
    codeIntegrityEvents = $events
} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $Output -Encoding utf8
Write-Output $Output
