#requires -Version 7.5
param([Parameter(Mandatory)][string]$Plan,[switch]$Run,[switch]$Execute,[string]$ExpectedSha256,[string]$LaunchId)
$ErrorActionPreference='Stop';$root=Split-Path -Parent $PSScriptRoot
$python=Join-Path $root '.venv/Scripts/python.exe';$planner=Join-Path $PSScriptRoot 'prepare-rate-trace.py'
if($Plan -match '["\r\n]'){throw 'Invalid rate plan path'}
$Plan=[IO.Path]::GetFullPath($Plan);$directory=[IO.Path]::GetDirectoryName($Plan)
if([IO.Path]::GetFileName($Plan) -cne 'rate-trace.json' -or
   [IO.Path]::GetDirectoryName($directory) -ne [IO.Path]::GetFullPath((Join-Path $root 'analysis')) -or
   [IO.Path]::GetFileName($directory) -cnotmatch '^rate-trace-[A-Za-z0-9-]{1,64}$'){throw 'Unexpected rate plan location'}
function Write-New([string]$Path,$Value){
    $stream=[IO.File]::Open($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    try{$bytes=[Text.UTF8Encoding]::new($false).GetBytes(($Value|ConvertTo-Json -Depth 8));$stream.Write($bytes,0,$bytes.Length)}finally{$stream.Dispose()}
}
function Q([string]$Value){'"'+$Value+'"'}
if($Execute){
    if($Run -or $ExpectedSha256 -cnotmatch '^[0-9a-f]{64}$' -or $LaunchId -cnotmatch '^[0-9a-f]{32}$'){throw 'Invalid rate collector role'}
    $log=Join-Path $directory ('collector-'+$LaunchId+'.log');$exitPath=Join-Path $directory ('collector-'+$LaunchId+'-exit.json')
    $stream=[IO.File]::Open($log,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    $writer=[IO.StreamWriter]::new($stream,[Text.UTF8Encoding]::new($false));$code=1;$failure=$null
    try{
        $identity=[Security.Principal.WindowsIdentity]::GetCurrent()
        if(-not ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Collector role requires elevation'}
        $checked=& $python $planner --collector-check $Plan --expected-sha256 $ExpectedSha256 --launch-id $LaunchId
        if($LASTEXITCODE){throw 'Rate collector plan rejected'};$settings=$checked|ConvertFrom-Json
        Import-Module (Join-Path $PSScriptRoot 'inspect-process.psm1')
        $normal=Get-Content -LiteralPath (Join-Path $directory 'normal-started.json') -Raw|ConvertFrom-Json
        $observed=Get-Sl3ProcessEvidence -ProcessId $normal.process.pid
        if(-not $observed.alive -or $observed.creationFileTimeUtc -ne $normal.process.creationFileTimeUtc -or
           $observed.imagePath -ine $normal.process.imagePath){throw 'Normal waiting role is no longer the same live process'}
        Write-New (Join-Path $directory 'collector-started.json') @{launchId=$LaunchId;planSha256=$ExpectedSha256;pid=$PID;utc=[datetime]::UtcNow.ToString('o')}
        & $settings.collectorRole.script -Run -WithStateObserver -TraceSeconds 60 -ContextDirectory $settings.contextDirectory 2>&1 |
            ForEach-Object {$writer.WriteLine([string]$_)}
        $code=0
    }catch{$failure=$_.Exception.Message;$writer.WriteLine(($_|Out-String))}
    finally{$writer.Dispose();Write-New $exitPath @{launchId=$LaunchId;planSha256=$ExpectedSha256;pid=$PID;exitCode=$code;error=$failure;completedUtc=[datetime]::UtcNow.ToString('o')}}
    exit $code
}
if($ExpectedSha256 -or $LaunchId){throw 'Internal arguments require collector role'}
$checked=& $python $planner --plan $Plan;if($LASTEXITCODE){throw 'Rate plan rejected; no child launched'}
if(-not $Run){$checked;return}
$settings=$checked|ConvertFrom-Json
Import-Module (Join-Path $PSScriptRoot 'inspect-process.psm1')
$parent=Get-Sl3ProcessEvidence -ProcessId $PID -WithToken
if($parent.elevated -ne $false){throw 'Launch from the ordinary user session so the probe cannot inherit elevation'}
$id=[guid]::NewGuid().ToString('N');$hash=(Get-FileHash -LiteralPath $Plan).Hash.ToLowerInvariant()
Write-New (Join-Path $directory 'attempted.json') @{launchId=$id;planSha256=$hash;parent=$parent;utc=[datetime]::UtcNow.ToString('o')}
$result=[ordered]@{launchId=$id;planSha256=$hash;status='launching';normalPid=$null;collectorPid=$null;error=$null}
try{
    $arguments=@('-NoProfile','-File',(Q $settings.normalRole.script),'-Run','-TargetHz',([string]$settings.targetHz),'-ExpectedInitialHz',([string]$settings.expectedInitialHz),'-ContextDirectory',(Q $settings.contextDirectory))
    $normal=Start-Process -FilePath $settings.runtime.powershell -ArgumentList $arguments -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $directory 'normal-output.txt') -RedirectStandardError (Join-Path $directory 'normal-error.txt')
    $result.normalPid=$normal.Id;$observed=Get-Sl3ProcessEvidence -ProcessId $normal.Id -WithToken
    if(-not $observed.alive -or $observed.elevated -ne $false){throw 'Normal waiting role token/query failed'}
    Write-New (Join-Path $directory 'normal-started.json') @{launchId=$id;planSha256=$hash;process=$observed;utc=[datetime]::UtcNow.ToString('o')}
    $collector=Start-Process -FilePath $settings.runtime.powershell -ArgumentList @('-NoProfile','-File',(Q $PSCommandPath),'-Execute','-Plan',(Q $Plan),'-ExpectedSha256',$hash,'-LaunchId',$id) -Verb RunAs -WindowStyle Hidden -PassThru
    $result.collectorPid=$collector.Id;$result.status='launched'
}catch{$result.error=$_.Exception.Message;$result.status='launch_failed'}
finally{Write-New (Join-Path $directory 'launch-result.json') $result}
$result|ConvertTo-Json
if($result.status -ne 'launched'){exit 1}
