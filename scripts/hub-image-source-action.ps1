<# Internal bounded-child PLA action. Default is a plan; no device operations. #>
[CmdletBinding()]
param(
    [ValidateSet('Start','Cleanup')][string]$Action = 'Start',
    [Parameter(Mandatory)][string]$PreparationRecord,
    [Parameter(Mandatory)][string]$PreparationSha256,
    [Parameter(Mandatory)][string]$Output,
    [switch]$Run
)
$ErrorActionPreference = 'Stop'
function Compare-Sl3CommittedImageConfiguration {
    param([string]$ActualXml,[string]$ExpectedXml)
    # Pure comparison only: no COM, filesystem or logger operation.
    foreach ($text in @($ActualXml,$ExpectedXml)) {
        if ([string]::IsNullOrEmpty($text) -or $text.Length -gt 65536 -or $text -match '<!DOCTYPE|<!ENTITY') {
            throw 'Unbounded or unsafe collector XML.'
        }
    }
    $actual=[xml]$ActualXml; $expected=[xml]$ExpectedXml
    $differences=[Collections.Generic.List[string]]::new()
    foreach ($doc in @($actual,$expected)) {
        if (@($doc.SelectNodes('/DataCollectorSet')).Count -ne 1 -or
            @($doc.SelectNodes('/DataCollectorSet/*[contains(local-name(),"DataCollector")]')).Count -ne 1 -or
            @($doc.SelectNodes('/DataCollectorSet/TraceDataCollector')).Count -ne 1 -or
            @($doc.SelectNodes('/DataCollectorSet/TraceDataCollector/TraceDataProvider')).Count -ne 1) {
            throw 'Expected one trace collector and one provider.'
        }
    }
    $paths=@('Duration','SchedulesEnabled','StopOnCompletion','Segment','SegmentMaxDuration','SegmentMaxSize',
        'Subdirectory','Task','TaskArguments','DataManager/Enabled')
    $paths+=@('Name','FileName','DataCollectorType','FileNameFormat','FileNameFormatPattern','SessionName',
        'Guid','ExtendedModes','StreamMode','ClockType','BufferSize','FlushTimer','LogAppend','LogOverwrite',
        'LogCircular','ProcessMode','TraceDataProvider/Guid','TraceDataProvider/KeywordsAny/Value',
        'TraceDataProvider/KeywordsAll/Value','TraceDataProvider/Level/Value','TraceDataProvider/FilterEnabled',
        'TraceDataProvider/Properties/Value') | ForEach-Object { 'TraceDataCollector/'+$_ }
    $paths+='RootPath'
    foreach ($path in $paths) {
        $xpath='/DataCollectorSet/'+$path
        $left=@($actual.SelectNodes($xpath)); $right=@($expected.SelectNodes($xpath))
        if ($left.Count -ne 1 -or $right.Count -ne 1) { $differences.Add($path); continue }
        $leftValue=$left[0].InnerText; $rightValue=$right[0].InnerText
        if ($path -eq 'RootPath') {
            $same=[IO.Path]::GetFullPath($leftValue).TrimEnd('\') -eq [IO.Path]::GetFullPath($rightValue).TrimEnd('\')
        } elseif ($path -match '(^|/)Guid$') {
            $same=[guid]$leftValue -eq [guid]$rightValue
        } else { $same=$leftValue -ceq $rightValue }
        if (-not $same) { $differences.Add($path) }
    }
    [pscustomobject]@{configurationMatchesExpected=($differences.Count -eq 0);mismatches=@($differences)}
}
if (-not $Run) { [ordered]@{planOnly=$true;action=$Action;sourceStarted=$false;deviceAccess=$false} | ConvertTo-Json; exit 0 }
if (Test-Path -LiteralPath $Output) { throw 'Action output already exists.' }
if ((Get-Item -LiteralPath $PreparationRecord).Length -gt 131072 -or
    (Get-FileHash -LiteralPath $PreparationRecord -Algorithm SHA256).Hash.ToLowerInvariant() -cne $PreparationSha256) {
    throw 'Frozen preparation record changed.'
}
Import-Module (Join-Path $PSScriptRoot 'inspect-process.psm1')
$producer = Get-Sl3ProcessEvidence -ProcessId $PID -WithToken
if (-not $producer.tokenQueried -or -not $producer.elevated) { throw 'Requires an already elevated process; no elevation is requested.' }
$record = Get-Content -Raw -LiteralPath $PreparationRecord | ConvertFrom-Json
if ($record.sessionName -cnotmatch '^SL3Image-[a-f0-9]{32}$' -or
    [guid]$record.sessionGuid -in @([guid]::Empty,[guid]'9e814aad-3204-11d2-9a82-006008a86939')) { throw 'Invalid private source identity.' }
$name = '[Service]' + $record.sessionName
$result = [ordered]@{action=$Action;producer=$producer;collectorName=$name;sourceCommitted=$false;
    startRequested=$false;stopRequested=$false;collectorDeleted=$false;collectorAlreadyAbsent=$false;successful=$false;error=$null;
    preparationSha256=$PreparationSha256;sourceSha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()}
try {
    if ($Action -eq 'Start') {
        # Reuse the full XML and validation-only policy immediately before creation.
        $preflight = $Output + '.preflight.json'
        & (Join-Path $PSScriptRoot 'validate-hub-image-source.ps1') -PreparationRecord $PreparationRecord -Output $preflight | Out-Null
        $validated = Get-Content -Raw -LiteralPath $preflight | ConvertFrom-Json
        if (-not $validated.valid -or $validated.preparationRecordSha256 -cne $PreparationSha256) { throw 'Preflight did not validate this exact input.' }
        $set = New-Object -ComObject Pla.DataCollectorSet
        $parsed = $set.SetXml($record.xml)
        if ($parsed.Count -ne 0) { throw 'Unexpected XML validation entries.' }
        # Persist admission before Commit: a killed child must not authorize
        # cleanup of a set which failed the absence preflight.
        $intent=[ordered]@{preparationSha256=$PreparationSha256;collectorName=$name;absenceValidated=$true}
        $intentPath=$Output+'.intent.json'
        $intentStream=[IO.File]::Open($intentPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try { $intentBytes=[Text.UTF8Encoding]::new($false).GetBytes(($intent | ConvertTo-Json)); $intentStream.Write($intentBytes,0,$intentBytes.Length) }
        finally { $intentStream.Dispose() }
        $items = $set.Commit($name,$null,1) # plaCreateNew only; never modify/update a prior collector.
        $result.sourceCommitted = $true
        for ($index=0; $index -lt $items.Count; $index++) {
            $item=$items.Item($index)
            $code=[uint32]([long]$item.Value -band 0xffffffffL)
            if ($code -ne 0x00300100 -or [string]$item.Key -cnotin @('TaskArguments','SubdirectoryFormatPattern')) {
                throw 'Unexpected persistent-commit validation entry.'
            }
        }
        # Query a fresh service object rather than echoing the submitted object's XML.
        # Save before Start: a timed-out child must not lose the pre-start observation.
        $snapshot=[ordered]@{scope='Persisted service configuration before Start; not native live properties';
            collectorName=$name;preparationSha256=$PreparationSha256;
            queryStartedUtc=[DateTime]::UtcNow.ToString('o');queryFinishedUtc=$null;
            querySucceeded=$false;status=$null;xml=$null;xmlCharacters=$null;configurationMatchesExpected=$false;
            mismatches=@();error=$null;sourceStarted=$false;readinessAdmission=$false}
        try {
            $persisted=New-Object -ComObject Pla.DataCollectorSet
            $persisted.Query($name,$null)
            $snapshot.querySucceeded=$true
            $snapshot.status=[int]$persisted.Status
            $actualXml=[string]$persisted.Xml
            $snapshot.xmlCharacters=$actualXml.Length
            if ($actualXml.Length -gt 65536) { throw 'Committed collector XML exceeds size bound.' }
            $snapshot.xml=$actualXml
            $comparison=Compare-Sl3CommittedImageConfiguration -ActualXml $actualXml -ExpectedXml $record.xml
            $snapshot.mismatches=@($comparison.mismatches)
            $snapshot.configurationMatchesExpected=$comparison.configurationMatchesExpected -and $snapshot.status -eq 0
            if ($snapshot.status -ne 0) { $snapshot.mismatches+= 'Status' }
        } catch { $snapshot.error=$_.Exception.Message }
        $snapshot.queryFinishedUtc=[DateTime]::UtcNow.ToString('o')
        $snapshotPath=$Output+'.committed.json'
        $snapshotStream=[IO.File]::Open($snapshotPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try {
            $snapshotBytes=[Text.UTF8Encoding]::new($false).GetBytes(($snapshot | ConvertTo-Json -Depth 5)+[Environment]::NewLine)
            $snapshotStream.Write($snapshotBytes,0,$snapshotBytes.Length)
        } finally { $snapshotStream.Dispose() }
        $result.committedConfiguration=[ordered]@{file=[IO.Path]::GetFileName($snapshotPath);
            sha256=(Get-FileHash -LiteralPath $snapshotPath -Algorithm SHA256).Hash.ToLowerInvariant();
            configurationMatchesExpected=$snapshot.configurationMatchesExpected}
        if (-not $snapshot.configurationMatchesExpected -or $snapshot.error) {
            throw 'Committed service configuration was not accepted; Start was not requested.'
        }
        if (-not (Test-Path -LiteralPath $record.prospectiveRootPath)) {
            $null=New-Item -ItemType Directory -Path $record.prospectiveRootPath
        }
        $result.startRequested=$true
        $set.Start($false) # asynchronous service start; supervisor observes ETW separately.
    } else {
        $intentPath=Join-Path ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Output))) 'start.json.intent.json'
        if (-not (Test-Path -LiteralPath $intentPath) -or (Get-Item -LiteralPath $intentPath).Length -gt 4096) { throw 'Cleanup has no bounded prior admission record.' }
        $intent=Get-Content -Raw -LiteralPath $intentPath | ConvertFrom-Json
        if ($intent.preparationSha256 -cne $PreparationSha256 -or $intent.collectorName -cne $name -or
            $intent.absenceValidated -isnot [bool] -or -not $intent.absenceValidated) { throw 'Cleanup admission differs.' }
        $set = New-Object -ComObject Pla.DataCollectorSet
        $absent=$false
        try { $set.Query($name,$null) }
        catch {
            $failure=$_.Exception
            while ($failure.InnerException) { $failure=$failure.InnerException }
            # L keeps this high-bit HRESULT positive for the unsigned comparison.
            if ([uint32]([long]$failure.HResult -band 0xffffffffL) -ne 0x80300002L) { throw }
            $absent=$true
        }
        if ($absent) { $result.collectorAlreadyAbsent=$true }
        else {
            $actual=[xml]$set.Xml
            $trace=$actual.DataCollectorSet.TraceDataCollector
            if (@($actual.DataCollectorSet.TraceDataCollector).Count -ne 1 -or
                $trace.SessionName -cne $record.sessionName -or [guid]$trace.Guid -ne [guid]$record.sessionGuid -or
                [IO.Path]::GetFullPath([string]$actual.DataCollectorSet.RootPath).TrimEnd('\') -ne
                    [IO.Path]::GetFullPath([string]$record.prospectiveRootPath).TrimEnd('\')) {
                throw 'Cleanup refuses a collector with different identity or output ownership.'
            }
            if ([int]$set.Status -ne 0) { $result.stopRequested=$true; $set.Stop($true) }
            $set.Delete()
            $result.collectorDeleted=$true
        }
    }
    $result.successful=$true
} catch { $result.error=$_.Exception.Message }
finally {
    $stream=[IO.File]::Open($Output,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try { $bytes=[Text.UTF8Encoding]::new($false).GetBytes(($result | ConvertTo-Json -Depth 8)+[Environment]::NewLine); $stream.Write($bytes,0,$bytes.Length) }
    finally { $stream.Dispose() }
}
if (-not $result.successful) { exit 1 }
