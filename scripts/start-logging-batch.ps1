<# One Windows approval for one frozen source-only batch. No persistent server/task. #>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Plan,
    [switch]$Run,
    [switch]$Execute,
    [string]$ExpectedSha256,
    [string]$LaunchId
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$python=Join-Path $root '.venv\Scripts\python.exe'
$runner=Join-Path $PSScriptRoot 'logging-batch.py'
$Plan=[IO.Path]::GetFullPath($Plan)
if ($Execute) {
    if ($Run -or $ExpectedSha256 -cnotmatch '^[0-9a-f]{64}$' -or $LaunchId -cnotmatch '^[0-9a-f]{32}$') {
        throw 'Invalid internal execution role.'
    }
    $directory=[IO.Path]::GetDirectoryName($Plan)
    if ([IO.Path]::GetFileName($Plan) -cne 'batch.json' -or
        [IO.Path]::GetDirectoryName($directory) -ne [IO.Path]::GetFullPath((Join-Path $root 'analysis')) -or
        [IO.Path]::GetFileName($directory) -cnotmatch '^logging-batch-[a-zA-Z0-9-]{1,64}$') { throw 'Unexpected child output location.' }
    foreach($location in @((Join-Path $root 'analysis'),$directory,$Plan)){
        if((Get-Item -LiteralPath $location -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Child output location cannot use reparse points.'}
    }
    $outputPath=Join-Path $directory ('child-'+$LaunchId+'.log')
    $exitPath=Join-Path $directory ('child-'+$LaunchId+'-exit.json')
    if(Test-Path -LiteralPath $exitPath){throw 'Child attempt already completed.'}
    $outputStream=[IO.File]::Open($outputPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    $writer=[IO.StreamWriter]::new($outputStream,[Text.UTF8Encoding]::new($false))
    $exitCode=1;$wrapperError=$null
    try {
        if((Get-FileHash -LiteralPath $Plan -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ExpectedSha256){throw 'Plan changed before child execution.'}
        & $python $runner --plan $Plan --execute --expected-sha256 $ExpectedSha256 2>&1 |
            ForEach-Object {$writer.WriteLine([string]$_)}
        $exitCode=$LASTEXITCODE
    } catch {
        $wrapperError=$_.Exception.Message
        $writer.WriteLine(($_ | Out-String))
    } finally {
        $writer.Dispose()
        $child=[ordered]@{launchId=$LaunchId;planSha256=$ExpectedSha256;pid=$PID;exitCode=$exitCode;
            completedUtc=[DateTime]::UtcNow.ToString('o');wrapperError=$wrapperError;
            executionMarkerPresent=(Test-Path -LiteralPath (Join-Path $directory 'execution-started.json'));
            batchResultPresent=(Test-Path -LiteralPath (Join-Path $directory 'batch-result.json'));readinessAdmission=$false}
        $stream=[IO.File]::Open($exitPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try{$bytes=[Text.UTF8Encoding]::new($false).GetBytes(($child | ConvertTo-Json)+[Environment]::NewLine);$stream.Write($bytes,0,$bytes.Length)}
        finally{$stream.Dispose()}
    }
    exit $exitCode
}
if($ExpectedSha256 -or $LaunchId){throw 'Internal child arguments are not accepted by the launcher.'}
& $python $runner --plan $Plan
if ($LASTEXITCODE) { throw 'Batch validation failed; no administrator launch.' }
if (-not $Run) { exit 0 }
$hash=(Get-FileHash -LiteralPath $Plan -Algorithm SHA256).Hash.ToLowerInvariant()
$launchId=[guid]::NewGuid().ToString('N')
$attempt=Join-Path ([IO.Path]::GetDirectoryName($Plan)) ('launch-'+$launchId+'.json')
$record=[ordered]@{planSha256=$hash;requestedUtc=[DateTime]::UtcNow.ToString('o');
    launchId=$launchId;childOutputFile=('child-'+$launchId+'.log');childExitFile=('child-'+$launchId+'-exit.json');
    status='not_launched';pid=$null;error=$null;sourceStarted=$false}
try {
    $arguments=@('-NoProfile','-File',('"'+$PSCommandPath+'"'),'-Plan',('"'+$Plan+'"'),'-Execute','-ExpectedSha256',$hash,'-LaunchId',$launchId)
    $process=Start-Process -FilePath (Get-Command pwsh).Source -Verb RunAs -WindowStyle Hidden -PassThru -ErrorAction Stop -ArgumentList $arguments
    $record.status='launched'
    $record.pid=$process.Id
    $record.sourceStarted=$null # A process launch is not an observed source start.
} catch {
    $record.error=$_.Exception.Message
    $failure=$_.Exception
    while($failure.InnerException){$failure=$failure.InnerException}
    $record.status=if($failure -is [ComponentModel.Win32Exception] -and $failure.NativeErrorCode -eq 1223){'administrator_launch_cancelled'}else{'launch_failed'}
} finally {
    $stream=[IO.File]::Open($attempt,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try{$bytes=[Text.UTF8Encoding]::new($false).GetBytes(($record | ConvertTo-Json)+[Environment]::NewLine);$stream.Write($bytes,0,$bytes.Length)}
    finally{$stream.Dispose()}
}
$record | ConvertTo-Json
if($record.status -ne 'launched'){exit 1}
