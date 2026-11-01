<# Exercise the production cleanup catch handler; no Start/Stop/Commit/Delete. #>
[CmdletBinding()]
param([Parameter(Mandatory)][string]$Output)
$ErrorActionPreference='Stop'
if (Test-Path -LiteralPath $Output) { throw 'Report already exists.' }
$source=Join-Path $PSScriptRoot 'hub-image-source-action.ps1'
$tokens=$null; $parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($source,[ref]$tokens,[ref]$parseErrors)
if ($parseErrors.Count) { throw 'Production script does not parse.' }
$clauses=@($ast.FindAll({param($node) $node -is [Management.Automation.Language.CatchClauseAst] -and
    $node.Extent.Text.Contains('0x80300002L')},$true))
if ($clauses.Count -ne 1) { throw 'Expected exactly one owned-collector absence handler.' }
# Extract the actual production body, rather than duplicating its comparison.
$body=$clauses[0].Body.Extent.Text
$handler=[scriptblock]::Create($body.Substring(1,$body.Length-2))
$name='[Service]SL3Image-'+[guid]::NewGuid().ToString('N')
$set=New-Object -ComObject Pla.DataCollectorSet
$absent=$false
$observed=$null
try { $set.Query($name,$null); throw 'Unexpected existing collector.' }
catch {
    $observed='0x{0:X8}' -f ([uint32]([long]$_.Exception.HResult -band 0xffffffffL))
    . $handler
}
if (-not $absent) { throw 'Actual absent collector was not recognized.' }
$foreignRejected=$false
try {
    try { throw [UnauthorizedAccessException]::new('Synthetic access-denied handler test') }
    catch { . $handler }
} catch { $foreignRejected=$true }
if (-not $foreignRejected) { throw 'Foreign HRESULT was accepted as absence.' }
$nestedRecognized=$false
$absent=$false
try { throw [Exception]::new('Synthetic wrapper',[Runtime.InteropServices.COMException]::new('Synthetic absent result',[int]-2144337918)) }
catch { . $handler; $nestedRecognized=$absent }
if (-not $nestedRecognized) { throw 'Nested HRESULT was not recognized.' }
$legacyBody=$body.Substring(1,$body.Length-2).Replace('0x80300002L','0x80300002')
$legacyHandler=[scriptblock]::Create($legacyBody)
$legacyRejectedAbsent=$false
try {
    try { $set.Query($name,$null); throw 'Unexpected existing collector.' }
    catch { . $legacyHandler }
} catch { $legacyRejectedAbsent=$true }
if (-not $legacyRejectedAbsent) { throw 'Regression check did not reproduce the original signed-literal defect.' }
$result=[ordered]@{scope='Actual read-only missing-collector query and extracted production error-handler tests';
    actualQueryName=$name;actualAbsentRecognized=$true;outerObservedHresult=$observed;foreignErrorRejected=$foreignRejected;
    nestedErrorRecognized=$nestedRecognized;legacyHandlerRejectedActualAbsent=$legacyRejectedAbsent;casesPassed=4;parseErrors=0;sourceStarted=$false;sourceStopped=$false;
    sourceCommitted=$false;collectorDeleted=$false;readinessAdmission=$false;
    sourceSha256=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant();
    testSourceSha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()}
$stream=[IO.File]::Open($Output,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try { $bytes=[Text.UTF8Encoding]::new($false).GetBytes(($result | ConvertTo-Json -Depth 5)+[Environment]::NewLine);$stream.Write($bytes,0,$bytes.Length) }
finally { $stream.Dispose() }
$result | ConvertTo-Json -Depth 5
