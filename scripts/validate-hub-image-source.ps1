<# PLA validation-only preflight. Never saves or starts a data collector set. #>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$PreparationRecord,
    [Parameter(Mandatory)][string]$Output
)
$ErrorActionPreference = 'Stop'
$Output = [IO.Path]::GetFullPath($Output)
if ((Test-Path -LiteralPath $Output) -or -not (Test-Path -LiteralPath ([IO.Path]::GetDirectoryName($Output)) -PathType Container)) {
    throw 'Expected a new report in an existing directory.'
}
$PreparationRecord = [IO.Path]::GetFullPath($PreparationRecord)
if ((Get-Item -LiteralPath $PreparationRecord).Length -gt 131072) { throw 'Preparation record exceeds size bound.' }
$record = Get-Content -Raw -LiteralPath $PreparationRecord | ConvertFrom-Json
$preparer = Join-Path $PSScriptRoot 'prepare-hub-image-source.ps1'
if ($record.sourceSha256 -ne (Get-FileHash -LiteralPath $preparer -Algorithm SHA256).Hash.ToLowerInvariant() -or
    $record.configurationValidated -isnot [bool] -or -not $record.configurationValidated -or
    $record.sourceCommitted -isnot [bool] -or $record.sourceCommitted -or
    $record.sourceStarted -isnot [bool] -or $record.sourceStarted -or
    $record.xml -isnot [string] -or $record.xml.Length -gt 65536 -or $record.xml -match '<!DOCTYPE|<!ENTITY' -or
    $record.sessionName -cnotmatch '^SL3Image-[a-f0-9]{32}$') { throw 'Unrecognized preparation record.' }
$xml = [xml]$record.xml
$root = $xml.DataCollectorSet
$trace = $root.TraceDataCollector
$expectedRoot = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $PSScriptRoot) ('tests/results/local/' + $record.sessionName)))
if (@($root.TraceDataCollector).Count -ne 1 -or @($trace.TraceDataProvider).Count -ne 1 -or
    [guid]$trace.Guid -ne [guid]$record.sessionGuid -or [guid]$trace.Guid -in @([guid]::Empty,[guid]'9e814aad-3204-11d2-9a82-006008a86939') -or
    $trace.SessionName -cne $record.sessionName -or [int]$root.Duration -ne $record.durationSeconds -or
    [int]$root.Duration -lt 1 -or [int]$root.Duration -gt 60 -or
    [IO.Path]::GetFullPath([string]$root.RootPath).TrimEnd('\') -ne $expectedRoot -or
    [int]$root.SchedulesEnabled -ne 0 -or [int]$root.Segment -ne 0 -or
    [int]$root.SegmentMaxDuration -ne 0 -or -not [string]::IsNullOrEmpty([string]$root.Subdirectory) -or
    [int]$root.StopOnCompletion -eq 0 -or [int]$root.SegmentMaxSize -ne 64 -or
    $trace.Name -cne 'SL3Image' -or $trace.FileName -cne 'images' -or [int]$trace.DataCollectorType -ne 1 -or
    [int]$trace.FileNameFormat -ne 0 -or -not [string]::IsNullOrEmpty([string]$trace.FileNameFormatPattern) -or
    [uint32]$trace.ExtendedModes -ne 0x02000000 -or [int]$trace.StreamMode -ne 1 -or [int]$trace.ClockType -ne 1 -or
    [int]$trace.LogAppend -ne 0 -or [int]$trace.LogOverwrite -ne 0 -or [int]$trace.LogCircular -ne 0 -or [int]$trace.ProcessMode -ne 0 -or
    [guid]$trace.TraceDataProvider.Guid -ne [guid]'151f55dc-467d-471f-83b5-5f889d46ff66' -or
    [uint64]$trace.TraceDataProvider.KeywordsAny.Value -ne 4096 -or
    [uint64]$trace.TraceDataProvider.KeywordsAll.Value -ne 0 -or [int]$trace.TraceDataProvider.Level.Value -ne 0 -or
    [int]$trace.TraceDataProvider.FilterEnabled -ne 0 -or [uint64]$trace.TraceDataProvider.Properties.Value -ne 0 -or
    -not [string]::IsNullOrEmpty([string]$root.Task) -or [int]$root.DataManager.Enabled -ne 0 -or
    (Test-Path -LiteralPath $expectedRoot)) { throw 'Preparation XML ownership, timing, provider or output fields differ.' }

Import-Module (Join-Path $PSScriptRoot 'inspect-process.psm1')
function Get-PlaError($failure) {
    $detail = $failure.Exception
    while ($detail.InnerException) { $detail = $detail.InnerException }
    [pscustomobject]@{ hresult=('0x{0:X8}' -f ([uint32]([long]$detail.HResult -band 0xffffffffL))); message=$detail.Message }
}
$name = '[Service]' + $record.sessionName
function Read-PlaName {
    $probe = New-Object -ComObject Pla.DataCollectorSet
    try { $null = $probe.Query($name,$null); [pscustomobject]@{ querySucceeded=$true; error=$null } }
    catch { [pscustomobject]@{ querySucceeded=$false; error=(Get-PlaError $_) } }
}
$before = Read-PlaName
if ($before.querySucceeded -or $before.error.hresult -ne '0x80300002') { throw 'Collector absence is not established.' }
$set = New-Object -ComObject Pla.DataCollectorSet
$parsed = $set.SetXml($record.xml)
if ($parsed.Count -ne 0) { throw 'Unexpected XML validation entries.' }
$items = @()
$failureInfo = $null
$callSucceeded = $false
try {
    # plaValidateOnly = 0x1000. No create/modify/update/flush bits are combined.
    $validation = $set.Commit($name,$null,0x1000)
    $callSucceeded = $true
    for ($index = 0; $index -lt $validation.Count; $index++) {
        $item = $validation.Item($index)
        $items += [pscustomobject]@{ key=[string]$item.Key; code=('0x{0:X8}' -f ([uint32]([long]$item.Value -band 0xffffffffL))); description=[string]$item.Description }
    }
} catch { $failureInfo = Get-PlaError $_ }
$after = Read-PlaName
$warningsAccepted = $true
$seen = @{}
foreach ($item in $items) {
    $allowed = $item.code -eq '0x00300100' -and -not $seen.ContainsKey($item.key) -and (
        ($item.key -ceq 'TaskArguments' -and [string]::IsNullOrEmpty([string]$root.TaskArguments)) -or
        ($item.key -ceq 'SubdirectoryFormatPattern' -and [int]$root.SubdirectoryFormat -eq 0 -and
            [string]::IsNullOrEmpty([string]$root.SubdirectoryFormatPattern)))
    if (-not $allowed) { $warningsAccepted = $false }
    $seen[$item.key] = $true
}
$directoryExists = [bool](Test-Path -LiteralPath $expectedRoot)
$producer = Get-Sl3ProcessEvidence -ProcessId $PID -WithToken
$valid = $callSucceeded -and $null -eq $failureInfo -and $warningsAccepted -and
    -not $after.querySucceeded -and $after.error.hresult -eq '0x80300002' -and -not $directoryExists -and $producer.tokenQueried
$result = [ordered]@{
    scope='PLA validation-only preflight; no persistent commit or trace start requested'
    valid=[bool]$valid
    producer=$producer
    collectorName=$name
    commitMode=0x1000
    before=$before
    validationCallSucceeded=$callSucceeded
    validationItems=$items
    knownInactiveWarningsAccepted=$warningsAccepted
    error=$failureInfo
    after=$after
    prospectiveDirectoryExists=$directoryExists
    sourceStarted=$false
    runtimeFlagForwardingVerified=$false
    independentStopValidated=$false
    readinessAdmission=$false
    preparationRecordSha256=(Get-FileHash -LiteralPath $PreparationRecord -Algorithm SHA256).Hash.ToLowerInvariant()
    preparerSha256=(Get-FileHash -LiteralPath $preparer -Algorithm SHA256).Hash.ToLowerInvariant()
    processInspectorSha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'inspect-process.psm1') -Algorithm SHA256).Hash.ToLowerInvariant()
    sourceSha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
}
$stream = [IO.File]::Open($Output,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try { $data = [Text.UTF8Encoding]::new($false).GetBytes(($result | ConvertTo-Json -Depth 8) + [Environment]::NewLine); $stream.Write($data,0,$data.Length) }
finally { $stream.Dispose() }
[pscustomobject]$result | Select-Object valid,collectorName,commitMode,validationCallSucceeded,knownInactiveWarningsAccepted,sourceStarted,readinessAdmission | ConvertTo-Json
if (-not $valid) { exit 1 }
