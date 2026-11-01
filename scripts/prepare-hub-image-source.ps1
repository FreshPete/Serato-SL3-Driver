<# Validate an uncommitted PLA image-source configuration. Never starts tracing. #>
[CmdletBinding()]
param(
    [ValidateRange(1,120)][int]$DurationSeconds = 5,
    [string]$Output
)
$ErrorActionPreference = 'Stop'
if($DurationSeconds -gt 60 -and $DurationSeconds -ne 120){throw 'Duration must be 1..60 seconds or the fixed 120-second scope window.'}
if ($Output) {
    $Output = [IO.Path]::GetFullPath($Output)
    if ((Test-Path -LiteralPath $Output) -or -not (Test-Path -LiteralPath ([IO.Path]::GetDirectoryName($Output)) -PathType Container)) {
        throw 'Expected a new report in an existing directory.'
    }
}
$identity = [guid]::NewGuid()
$session = 'SL3Image-' + [guid]::NewGuid().ToString('N')
$futureOutput = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $PSScriptRoot) ('tests/results/local/' + $session)))
if (Test-Path -LiteralPath $futureOutput) { throw 'Prospective capture directory already exists.' }
$set = New-Object -ComObject Pla.DataCollectorSet
$set.RootPath = $futureOutput
$set.Duration = $DurationSeconds
$set.SchedulesEnabled = $false
$set.StopOnCompletion = $true
$set.Segment = $false
$set.SegmentMaxDuration = 0
$set.SegmentMaxSize = 64
$collector = $set.DataCollectors.CreateDataCollector(1)
$draft = [xml]$collector.Xml
$draft.TraceDataCollector.Name = 'SL3Image'
$draft.TraceDataCollector.FileName = 'images'
$draft.TraceDataCollector.SessionName = $session
# Set GUID through documented XML serialization: the native GUID property does
# not marshal directly through PowerShell's automation adapter on this host.
$draft.TraceDataCollector.Guid = $identity.ToString('B')
$draft.TraceDataCollector.ExtendedModes = '33554432' # EVENT_TRACE_SYSTEM_LOGGER_MODE
$draft.TraceDataCollector.BufferSize = '64'
$draft.TraceDataCollector.FlushTimer = '1'
$draft.TraceDataCollector.ClockType = '1' # QPC
$provider = $draft.CreateElement('TraceDataProvider')
$provider.InnerXml = '<Guid>{151f55dc-467d-471f-83b5-5f889d46ff66}</Guid><KeywordsAny><Value>4096</Value></KeywordsAny><Level><Value>0</Value></Level>'
$null = $draft.DocumentElement.AppendChild($provider)
$validation = $collector.SetXml($draft.OuterXml)
if ($validation.Count -ne 0) { throw 'PLA reported configuration validation entries.' }
$set.DataCollectors.Add($collector)
$roundTrip = [xml]$set.Xml
$root = $roundTrip.DataCollectorSet
$trace = $root.TraceDataCollector
if ([int]$root.Duration -ne $DurationSeconds -or [int]$root.SchedulesEnabled -ne 0 -or
    [IO.Path]::GetFullPath([string]$root.RootPath).TrimEnd('\') -ne $futureOutput -or
    [int]$root.StopOnCompletion -eq 0 -or [int]$root.Segment -ne 0 -or [int]$root.SegmentMaxSize -ne 64 -or
    [guid]$trace.Guid -ne $identity -or $trace.SessionName -ne $session -or
    [uint32]$trace.ExtendedModes -ne 0x02000000 -or [int]$trace.StreamMode -ne 1 -or
    [int]$trace.ClockType -ne 1 -or [int]$trace.LogAppend -ne 0 -or [int]$trace.LogOverwrite -ne 0 -or
    [guid]$trace.TraceDataProvider.Guid -ne [guid]'151f55dc-467d-471f-83b5-5f889d46ff66' -or
    [uint64]$trace.TraceDataProvider.KeywordsAny.Value -ne 4096 -or $collector.IsKernelTrace) {
    throw 'PLA changed a required source-ownership, timing or provider field.'
}
$result = [ordered]@{
    scope = 'Actual uncommitted PLA configuration round-trip; no trace or persistent collector created'
    configurationValidated = $true
    producerPid = $PID
    durationSeconds = $DurationSeconds
    sessionName = $session
    sessionGuid = $identity.ToString()
    prospectiveRootPath = $futureOutput
    prospectiveRootCreated = [bool](Test-Path -LiteralPath $futureOutput)
    providerGuid = '151f55dc-467d-471f-83b5-5f889d46ff66'
    providerKeywordsAny = 4096
    extendedModes = 0x02000000
    plaLegacyKernelClassification = [bool]$collector.IsKernelTrace
    sourceCommitted = $false
    sourceStarted = $false
    runtimeFlagForwardingVerified = $false
    independentStopValidated = $false
    imageRundownObserved = $false
    readinessAdmission = $false
    sourceSha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    xml = $set.Xml
}
if ($result.prospectiveRootCreated) { throw 'Unexpected prospective capture directory creation.' }
$json = $result | ConvertTo-Json -Depth 6
if ($Output) {
    $stream = [IO.File]::Open($Output, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes($json + [Environment]::NewLine)
        $stream.Write($bytes, 0, $bytes.Length)
    } finally { $stream.Dispose() }
}
$json
