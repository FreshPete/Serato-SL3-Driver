param([switch]$Install, [switch]$RiskAccepted)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$setup = Join-Path $root 'artifacts/extracted/rane-windows/RaneAsioSl3Setup.exe'
$archive = Join-Path $root 'artifacts/downloads/RaneAsioSl3Ver1.3.5f2.zip'
$expectedArchive = '6a21aeb31900a543b1a0ee08094af8067833fda79c701c6429cbd926606c2b12'
if ((Get-FileHash -LiteralPath $archive).Hash.ToLowerInvariant() -ne $expectedArchive) { throw 'Archive identity changed; re-inventory before installing.' }
$expectedSetup = '7c4dcfed4d64f42159cfe2a11adbb4cb125ed764fa4932ef72b535e673478f6b'
if ((Get-FileHash -LiteralPath $setup).Hash.ToLowerInvariant() -ne $expectedSetup) { throw 'Installer identity changed; re-inventory before installing.' }
$sig = Get-AuthenticodeSignature -LiteralPath $setup
if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'CN=Rane Corporation') { throw 'Original Rane signature did not verify.' }
& "$PSScriptRoot/collect-windows-state.ps1" -Output 'tests/results/local/before-original-driver.json'
if (-not $Install) { Write-Output 'Preflight passed. No installation requested.'; return }
if (-not $RiskAccepted) { throw 'Installation is explicit: pass -RiskAccepted after reviewing the test and recovery implications.' }
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { throw 'Run this installation test from an elevated PowerShell terminal.' }
$log = Join-Path $root 'tests/results/local/rane-original-install.log'
# Interactive vendor installer: no silent acceptance, firmware call, security change or automatic reboot.
$process = Start-Process -FilePath $setup -WindowStyle Normal -ArgumentList @('/LOG="'+$log+'"','/NORESTART') -PassThru -Wait
@{exitCode=$process.ExitCode;finishedUtc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json |
    Set-Content -LiteralPath 'tests/results/local/rane-original-exit.json'
& "$PSScriptRoot/collect-windows-state.ps1" -Output 'tests/results/local/after-original-driver.json'
Write-Output 'Return the install log and before/after JSON. If a restart is requested, restart at a convenient time and collect state again. Leave firmware-update controls untouched.'
