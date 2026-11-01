<# One normal-user control probe and one administrator collector; no persistent broker. #>
[CmdletBinding()]
param([Parameter(Mandatory)][string]$Plan,[switch]$Run,[switch]$Execute,[string]$ExpectedSha256,[string]$LaunchId)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$python=Join-Path $root '.venv/Scripts/python.exe'
$runner=Join-Path $PSScriptRoot 'collect-controls-with-images.py'
$Plan=[IO.Path]::GetFullPath($Plan)
$directory=[IO.Path]::GetDirectoryName($Plan)
if([IO.Path]::GetFileName($Plan) -cne 'controls-image.json' -or
   [IO.Path]::GetDirectoryName($directory) -ne [IO.Path]::GetFullPath((Join-Path $root 'analysis')) -or
   [IO.Path]::GetFileName($directory) -cnotmatch '^logging-batch-[a-zA-Z0-9-]{1,64}$'){throw 'Unexpected collector plan location.'}
foreach($location in @((Join-Path $root 'analysis'),$directory,$Plan)){
    if((Get-Item -LiteralPath $location -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Collector plan cannot use reparse points.'}
}
function Write-NewJson([string]$Path,$Value){
    $stream=[IO.File]::Open($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    try{$bytes=[Text.UTF8Encoding]::new($false).GetBytes(($Value|ConvertTo-Json -Depth 8)+[Environment]::NewLine);$stream.Write($bytes,0,$bytes.Length)}
    finally{$stream.Dispose()}
}
if($Execute){
    if($Run -or $ExpectedSha256 -cnotmatch '^[0-9a-f]{64}$' -or $LaunchId -cnotmatch '^[0-9a-f]{32}$'){throw 'Invalid collector child role.'}
    $log=Join-Path $directory ('controls-child-'+$LaunchId+'.log')
    $exitPath=Join-Path $directory ('controls-child-'+$LaunchId+'-exit.json')
    if(Test-Path -LiteralPath $exitPath){throw 'Collector child already completed.'}
    $stream=[IO.File]::Open($log,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    $writer=[IO.StreamWriter]::new($stream,[Text.UTF8Encoding]::new($false))
    $code=1;$failure=$null
    try{
        if((Get-FileHash -LiteralPath $Plan).Hash.ToLowerInvariant() -cne $ExpectedSha256){throw 'Plan changed before collector child execution.'}
        & $python $runner --plan $Plan --execute --expected-sha256 $ExpectedSha256 2>&1|ForEach-Object {$writer.WriteLine([string]$_)}
        $code=$LASTEXITCODE
    }catch{$failure=$_.Exception.Message;$writer.WriteLine(($_|Out-String))}
    finally{
        $writer.Dispose()
        Write-NewJson $exitPath ([ordered]@{launchId=$LaunchId;pid=$PID;exitCode=$code;error=$failure;planSha256=$ExpectedSha256;
            completedUtc=[DateTime]::UtcNow.ToString('o');readinessAdmission=$false})
    }
    exit $code
}
if($ExpectedSha256 -or $LaunchId){throw 'Internal collector arguments require the child role.'}
$checked=& $python $runner --plan $Plan
if($LASTEXITCODE){throw 'Collector preflight failed; no process launched.'}
if(-not $Run){$checked;exit 0}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
if(([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
    throw 'Start this launcher from the normal user session so the probe does not inherit elevation.'
}
$settings=$checked|ConvertFrom-Json
$hash=(Get-FileHash -LiteralPath $Plan).Hash.ToLowerInvariant()
$id=[guid]::NewGuid().ToString('N')
$record=[ordered]@{launchId=$id;planSha256=$hash;requestedUtc=[DateTime]::UtcNow.ToString('o');
    normalProbePid=$null;collectorWrapperPid=$null;status='launching';error=$null;readinessAdmission=$false}
$launchPath=Join-Path $directory 'controls-image-launch.json'
# Claim the entire attempt before either process. A cancelled UAC needs a new
# plan/context, preventing two waiting normal probes from sharing one trace.
Write-NewJson $launchPath $record
try{
    $normalArgs=@('-NoProfile','-File',('"'+(Join-Path $PSScriptRoot 'test-controls-user-probe.ps1')+'"'),
                  '-Run','-TraceSeconds',([string]$settings.traceSeconds),'-ContextDirectory',('"'+$settings.contextDirectory+'"'))
    if($settings.schema -ceq 'sl3.scope-image-collector.v1'){$normalArgs+=@('-Scenario','Scope')}
    $normal=Start-Process -FilePath $settings.runtime.loggingRuntime.powershell -ArgumentList $normalArgs -WindowStyle Hidden -PassThru -ErrorAction Stop `
        -RedirectStandardOutput (Join-Path $directory ('controls-normal-'+$id+'.out')) `
        -RedirectStandardError (Join-Path $directory ('controls-normal-'+$id+'.err'))
    $record.normalProbePid=$normal.Id
    $arguments=@('-NoProfile','-File',('"'+$PSCommandPath+'"'),'-Plan',('"'+$Plan+'"'),'-Execute','-ExpectedSha256',$hash,'-LaunchId',$id)
    $admin=Start-Process -FilePath $settings.runtime.loggingRuntime.powershell -Verb RunAs -WindowStyle Hidden -PassThru -ErrorAction Stop -ArgumentList $arguments
    $record.collectorWrapperPid=$admin.Id;$record.status='launched'
}catch{
    $record.error=$_.Exception.Message;$failure=$_.Exception
    while($failure.InnerException){$failure=$failure.InnerException}
    $record.status=if($failure -is [ComponentModel.Win32Exception] -and $failure.NativeErrorCode -eq 1223){'administrator_launch_cancelled'}else{'launch_failed'}
    # The normal role owns its 90-second wait. No collector admission means no
    # device launch. Never kill a role that might already own USB cleanup.
}finally{
    Write-NewJson (Join-Path $directory 'controls-image-launch-result.json') $record
}
$record|ConvertTo-Json
if($record.status -ne 'launched'){exit 1}
