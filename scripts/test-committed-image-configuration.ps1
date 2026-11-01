<# Test extracted production XML comparison only; no COM/logger/device calls. #>
[CmdletBinding()]
param([Parameter(Mandatory)][string]$PreparationRecord,[Parameter(Mandatory)][string]$Output)
$ErrorActionPreference='Stop'
if (Test-Path -LiteralPath $Output) { throw 'Report already exists.' }
$source=Join-Path $PSScriptRoot 'hub-image-source-action.ps1'
$tokens=$null;$parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($source,[ref]$tokens,[ref]$parseErrors)
if ($parseErrors.Count) { throw 'Production script does not parse.' }
$functions=@($ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -ceq 'Compare-Sl3CommittedImageConfiguration'},$true))
if ($functions.Count -ne 1) { throw 'Expected one production comparison.' }
. ([scriptblock]::Create($functions[0].Extent.Text))
$original=[string](Get-Content -Raw -LiteralPath $PreparationRecord | ConvertFrom-Json).xml
$outcomes=[Collections.Generic.List[object]]::new()
function Test-Comparison([string]$Name,[scriptblock]$Edit,[string]$ExpectedMismatch,[bool]$Throws=$false) {
    $xml=[xml]$original
    & $Edit $xml
    $failure=$null;$value=$null
    try { $value=Compare-Sl3CommittedImageConfiguration -ActualXml $xml.OuterXml -ExpectedXml $original }
    catch { $failure=$_.Exception.Message }
    if ($Throws) {
        if (-not $failure) { throw "Expected rejection: $Name" }
    } elseif ($failure) { throw "Unexpected comparison failure: $Name : $failure" }
    elseif ($ExpectedMismatch) {
        if ($value.configurationMatchesExpected -or $ExpectedMismatch -cnotin $value.mismatches) { throw "Missing mismatch: $Name" }
    } elseif (-not $value.configurationMatchesExpected -or $value.mismatches.Count) { throw "Expected match: $Name" }
    $outcomes.Add([pscustomobject]@{name=$Name;passed=$true;rejected=[bool]($failure -or $ExpectedMismatch)})
}
Test-Comparison 'same configuration' {} ''
Test-Comparison 'GUID spelling normalization' {param($x) $x.DataCollectorSet.TraceDataCollector.Guid=([guid]$x.DataCollectorSet.TraceDataCollector.Guid).ToString('D').ToUpperInvariant()} ''
Test-Comparison 'foreign GUID' {param($x) $x.DataCollectorSet.TraceDataCollector.Guid='11111111-1111-1111-1111-111111111111'} 'TraceDataCollector/Guid'
Test-Comparison 'foreign root' {param($x) $x.DataCollectorSet.RootPath='C:\foreign'} 'RootPath'
Test-Comparison 'changed duration' {param($x) $x.DataCollectorSet.Duration='60'} 'Duration'
Test-Comparison 'removed size limit' {param($x) $x.DataCollectorSet.SegmentMaxSize='0'} 'SegmentMaxSize'
Test-Comparison 'circular mode' {param($x) $x.DataCollectorSet.TraceDataCollector.LogCircular='-1'} 'TraceDataCollector/LogCircular'
Test-Comparison 'changed provider keyword' {param($x) $x.DataCollectorSet.TraceDataCollector.TraceDataProvider.KeywordsAny.Value='8192'} 'TraceDataCollector/TraceDataProvider/KeywordsAny/Value'
Test-Comparison 'changed extended mode' {param($x) $x.DataCollectorSet.TraceDataCollector.ExtendedModes='0'} 'TraceDataCollector/ExtendedModes'
Test-Comparison 'duplicate GUID' {param($x) $null=$x.DataCollectorSet.TraceDataCollector.AppendChild($x.DataCollectorSet.TraceDataCollector.SelectSingleNode('Guid').CloneNode($true))} 'TraceDataCollector/Guid'
Test-Comparison 'missing timing property' {param($x) $null=$x.DataCollectorSet.RemoveChild($x.DataCollectorSet.SelectSingleNode('Duration'))} 'Duration'
Test-Comparison 'additional provider' {param($x) $null=$x.DataCollectorSet.TraceDataCollector.AppendChild($x.DataCollectorSet.TraceDataCollector.TraceDataProvider.CloneNode($true))} '' $true
Test-Comparison 'additional collector' {param($x) $null=$x.DataCollectorSet.AppendChild($x.DataCollectorSet.TraceDataCollector.CloneNode($true))} '' $true
foreach ($bad in @('<!DOCTYPE DataCollectorSet><DataCollectorSet/>',('x'*65537))) {
    $rejected=$false
    try { $null=Compare-Sl3CommittedImageConfiguration -ActualXml $bad -ExpectedXml $original }
    catch { $rejected=$true }
    if (-not $rejected) { throw 'Unsafe/oversized XML was accepted.' }
    $outcomes.Add([pscustomobject]@{name=if($bad.Length -gt 65536){'oversized XML'}else{'DTD XML'};passed=$true;rejected=$true})
}
$result=[ordered]@{scope='Extracted production pure XML comparison; no COM, source lifecycle or USB operation';
    casesPassed=$outcomes.Count;cases=@($outcomes);parseErrors=0;
    sourceSha256=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant();
    preparationSha256=(Get-FileHash -LiteralPath $PreparationRecord -Algorithm SHA256).Hash.ToLowerInvariant();
    testSourceSha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()}
$stream=[IO.File]::Open($Output,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try { $bytes=[Text.UTF8Encoding]::new($false).GetBytes(($result | ConvertTo-Json -Depth 5)+[Environment]::NewLine);$stream.Write($bytes,0,$bytes.Length) }
finally { $stream.Dispose() }
Write-Output "Passed $($outcomes.Count) pure comparison cases"
