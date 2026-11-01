<# Extract the production launch handler; Start-Process is mocked, never elevated. #>
[CmdletBinding()]
param([Parameter(Mandatory)][string]$Output)
$ErrorActionPreference='Stop'
if(Test-Path -LiteralPath $Output){throw 'Report already exists'}
$source=Join-Path $PSScriptRoot 'start-logging-batch.ps1'
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($source,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'Production launcher failed parsing'}
$handlers=@($ast.FindAll({param($node) $node -is [Management.Automation.Language.TryStatementAst] -and
    $node.Extent.Text.Contains('$process=Start-Process')},$true))
if($handlers.Count -ne 1){throw 'Expected one production launch handler'}
$handler=[scriptblock]::Create($handlers[0].Extent.Text)
$temporary=Join-Path ([IO.Path]::GetTempPath()) ('sl3-launch-test-'+[guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory -Path $temporary
$script:launchCalls=0;$script:failureCode=0
function Start-Process {
    [CmdletBinding()]
    param($FilePath,$Verb,$WindowStyle,[switch]$PassThru,$ArgumentList)
    $script:launchCalls++
    if($Verb -ne 'RunAs' -or $WindowStyle -ne 'Hidden' -or -not $PassThru -or '-Execute' -notin $ArgumentList -or
        '-LaunchId' -notin $ArgumentList -or $ArgumentList[-1] -cnotmatch '^[0-9a-f]{32}$'){throw 'Launch contract differs'}
    if($script:failureCode){throw [ComponentModel.Win32Exception]::new($script:failureCode)}
    [pscustomobject]@{Id=4321}
}
$outcomes=@()
foreach($case in @(@{code=0;status='launched';pid=4321},@{code=1223;status='administrator_launch_cancelled';pid=$null},@{code=5;status='launch_failed';pid=$null})){
    $script:failureCode=$case.code
    $before=$script:launchCalls
    $Plan=Join-Path $temporary 'batch.json';$hash='0'*64;$launchId='a'*32
    $attempt=Join-Path $temporary ('attempt-'+$case.code+'.json')
    $record=[ordered]@{status='not_launched';pid=$null;error=$null;sourceStarted=$false}
    . $handler
    $saved=Get-Content -Raw -LiteralPath $attempt | ConvertFrom-Json
    if($script:launchCalls -ne $before+1 -or $saved.status -cne $case.status -or $saved.pid -ne $case.pid){throw 'Incorrect launch outcome or retry'}
    if(($case.code -eq 0 -and $null -ne $saved.sourceStarted) -or ($case.code -ne 0 -and ($saved.sourceStarted -isnot [bool] -or $saved.sourceStarted))){throw 'Launch uncertainty was not preserved'}
    $outcomes+=[pscustomobject]@{nativeError=$case.code;status=$saved.status;passed=$true}
}
$result=[ordered]@{scope='Extracted production launch handler with mocked Start-Process; no UAC/source/device operation';casesPassed=$outcomes.Count;cases=$outcomes;parseErrors=0;
    sourceSha256=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()}
$stream=[IO.File]::Open($Output,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try{$bytes=[Text.UTF8Encoding]::new($false).GetBytes(($result | ConvertTo-Json -Depth 5)+[Environment]::NewLine);$stream.Write($bytes,0,$bytes.Length)}
finally{$stream.Dispose()}
Write-Output 'Passed three mocked launch-handler cases; no elevation requested'
