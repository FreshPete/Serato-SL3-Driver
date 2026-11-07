# Sample ordinary Windows process/module metadata during a manual application launch.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Application,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$ApplicationSha256,
    [Parameter(Mandatory)][string]$Module,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$ModuleSha256,
    [ValidateRange(1,120)][int]$TimeoutSeconds = 30,
    [ValidateRange(0,15)][int]$FollowUpSeconds = 0
)

$ErrorActionPreference = 'Stop'
if (-not [Environment]::Is64BitProcess) { throw 'Run from 64-bit PowerShell' }
Import-Module (Join-Path $PSScriptRoot 'inspect-process.psm1')
if ((Get-Sl3ProcessEvidence -ProcessId $PID -WithToken).elevated) {
    throw 'Run from the ordinary desktop account'
}

function Confirm-File([string]$Path, [string]$ExpectedSha256) {
    if (-not [IO.Path]::IsPathFullyQualified($Path)) { throw 'Use an absolute path' }
    $file = Get-Item -LiteralPath $Path
    if ($file.PSIsContainer -or $file.FullName -ne $Path -or
        (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ne $ExpectedSha256) {
        throw "Reviewed file identity differs for $Path"
    }
}

Confirm-File $Application $ApplicationSha256
Confirm-File $Module $ModuleSha256
$name = [IO.Path]::GetFileNameWithoutExtension($Application)
$armedUtc = [DateTime]::UtcNow
$armedFileTime = $armedUtc.ToFileTimeUtc()
$clock = [Diagnostics.Stopwatch]::StartNew()
$observed = $null
$modulePath = $null
$firstModuleSampleMs = 0L
$samples = 0
$followUpSamples = 0
$disappearanceSampled = $false
$queryErrors = 0
[Console]::Error.WriteLine('Module observer armed. Launch the application normally.')

do {
    foreach ($process in [Diagnostics.Process]::GetProcessesByName($name)) {
        try {
            try {
                $before = Get-Sl3ProcessEvidence -ProcessId $process.Id -WithToken
                if (-not $before.alive -or $before.elevated -or $before.imagePath -ne $Application -or
                    [long]$before.creationFileTimeUtc -lt $armedFileTime) { continue }
                if ($observed -and ($before.pid -ne $observed.pid -or
                    $before.creationFileTimeUtc -ne $observed.creationFileTimeUtc)) {
                    throw [InvalidOperationException]::new('More than one new matching application instance')
                }
                $observed = $before
                $match = $process.Modules | Where-Object FileName -EQ $Module | Select-Object -First 1
                $after = Get-Sl3ProcessEvidence -ProcessId $process.Id
                if (-not $after.alive -or $after.creationFileTimeUtc -ne $before.creationFileTimeUtc -or
                    $after.imagePath -ne $before.imagePath) { continue }
                $samples++
                if ($modulePath) {
                    $followUpSamples++
                    if (-not $match) { $disappearanceSampled = $true }
                } elseif ($match) {
                    $modulePath = $match.FileName
                    $firstModuleSampleMs = $clock.ElapsedMilliseconds
                }
            } catch [ComponentModel.Win32Exception], [Management.Automation.MethodInvocationException],
                    [Management.Automation.GetValueInvocationException] {
                $queryErrors++
            }
        } finally {
            $process.Dispose()
        }
    }
    if ($clock.Elapsed.TotalSeconds -ge $TimeoutSeconds -or
        ($modulePath -and $clock.ElapsedMilliseconds - $firstModuleSampleMs -ge $FollowUpSeconds * 1000)) { break }
    Start-Sleep -Milliseconds 250
} while ($clock.Elapsed.TotalSeconds -lt $TimeoutSeconds)

Confirm-File $Application $ApplicationSha256
Confirm-File $Module $ModuleSha256
[ordered]@{
    schema = 'sl3.asio-module-observation.v1'
    armedUtc = $armedUtc.ToString('o')
    finishedUtc = [DateTime]::UtcNow.ToString('o')
    applicationSha256 = $ApplicationSha256.ToLowerInvariant()
    moduleFileSha256 = $ModuleSha256.ToLowerInvariant()
    process = $observed
    completedModuleSamples = $samples
    followUpModuleSamples = $followUpSamples
    moduleDisappearanceSampled = $disappearanceSampled
    queryErrors = $queryErrors
    modulePathObserved = $modulePath
    asioCallsObserved = $false
    moduleAbsenceProved = $false
} | ConvertTo-Json -Depth 4
