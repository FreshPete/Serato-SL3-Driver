#requires -Version 7.5
param(
    [ValidateSet('Plan','Run','Stage','Recover')][string]$Mode='Plan',
    [Parameter(Mandatory)][string]$SessionPlan,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedPlanSha256
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if ([Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture -ne [Runtime.InteropServices.Architecture]::X64) {
    throw 'The native x64 PowerShell process is required for the 64-bit registry view'
}
$root=Split-Path $PSScriptRoot
$leases=[Collections.Generic.List[IO.Stream]]::new()
$runnerProcess=$null
function Pin-Input([string]$Path,[string]$Expected) {
    if ($Expected -cnotmatch '^[0-9a-f]{64}$') { throw 'Expected lowercase SHA-256' }
    $stream=[IO.File]::Open($Path,'Open','Read','Read')
    $leases.Add($stream)
    if ([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($stream)).ToLowerInvariant() -cne $Expected) {
        throw "Reviewed input differs: $([IO.Path]::GetFileName($Path))"
    }
    $stream.Position=0
    return $stream
}
function Write-New([string]$Path,[string]$Text) {
    $stream=[IO.File]::Open($Path,'CreateNew','Write','None')
    try { $stream.Write([Text.Encoding]::UTF8.GetBytes($Text)); $stream.Flush($true) }
    finally { $stream.Dispose() }
}
function Read-RunOwner([string]$Path) {
    $stream=[IO.File]::Open($Path,'Open','Read','ReadWrite')
    $reader=[IO.StreamReader]::new($stream)
    try { return ($reader.ReadToEnd() | ConvertFrom-Json -AsHashtable) }
    finally { $reader.Dispose() }
}
try {
    $planStream=Pin-Input $SessionPlan $ExpectedPlanSha256
    $reader=[IO.StreamReader]::new($planStream,[Text.Encoding]::UTF8,$true,1024,$true)
    try { $plan=$reader.ReadToEnd() | ConvertFrom-Json -AsHashtable } finally { $reader.Dispose() }
    if ($plan.schema -cne 'sl3.serato-session-plan.v1' -or $plan.projectRoot -cne $root) { throw 'Session project binding differs' }
    foreach ($entry in $plan.sources.GetEnumerator()) {
        $path=[IO.Path]::GetFullPath((Join-Path $root $entry.Key))
        if (-not $path.StartsWith(($root+[IO.Path]::DirectorySeparatorChar),[StringComparison]::OrdinalIgnoreCase)) {
            throw 'Source path escaped the project'
        }
        $null=Pin-Input $path $entry.Value
    }
    $python=$plan.python.path
    $null=Pin-Input $python $plan.python.sha256
    foreach ($entry in $plan.runtimeFiles.GetEnumerator()) { $null=Pin-Input $entry.Key $entry.Value }
    & $python -I -B "$PSScriptRoot/prepare-serato-session-plan.py" --verify $SessionPlan --expected-plan-sha256 $ExpectedPlanSha256
    if ($LASTEXITCODE) { throw 'Complete session plan verification failed' }
    foreach ($artifact in @($plan.capsule,$plan.archiveSource,$plan.installerResource,$plan.launcher,$plan.application)) {
        $null=Pin-Input $artifact.path $artifact.sha256
    }
    $shimManifestPath=Join-Path $plan.preparedShim.path 'preparation.json'
    $null=Pin-Input $shimManifestPath $plan.preparedShim.sha256
    $shimManifest=Get-Content -LiteralPath $shimManifestPath -Raw | ConvertFrom-Json -AsHashtable
    $null=Pin-Input (Join-Path $plan.preparedShim.path 'startup-shim.js') $shimManifest.preparedScriptSha256
    $nativeManifestPath=Join-Path $plan.nativeBundle.path 'bundle-manifest.json'
    $null=Pin-Input $nativeManifestPath $plan.nativeBundle.sha256
    $nativeManifest=Get-Content -LiteralPath $nativeManifestPath -Raw | ConvertFrom-Json -AsHashtable
    foreach ($entry in $nativeManifest.files.GetEnumerator()) {
        $path=[IO.Path]::GetFullPath((Join-Path $plan.nativeBundle.path $entry.Key))
        if (-not $path.StartsWith(($plan.nativeBundle.path+[IO.Path]::DirectorySeparatorChar),[StringComparison]::OrdinalIgnoreCase)) {
            throw 'Native payload escaped its reviewed bundle'
        }
        $null=Pin-Input $path $entry.Value.sha256
    }
    . "$PSScriptRoot/serato-installer-resource-transaction.ps1"
    $exe=$plan.application.path
    $target=Join-Path (Split-Path $exe) 'userio_resources.bin'
    $bundle=Join-Path (Split-Path $exe) 'bundles/8c7758f23375cee18a9cf3be4a3acc15.bin'
    $permit=$plan.permitPath
    $capsulePath=$plan.capsule.path
    $capsuleHash=$plan.capsule.sha256
    $directory=Split-Path $capsulePath
    $receipt=Join-Path $directory 'install-receipt.json'
    $ready=Join-Path $directory 'resources-ready.txt'
    $release=Join-Path $directory 'release.txt'
    $final=Join-Path $directory 'session-final.json'
    $clean=Join-Path $directory 'broker-clean.json'
    $session=Join-Path $directory 'broker-session'
    $runLock=Join-Path $directory 'session-run.lock'
    $tx=New-Sl3ArchiveTransaction $target $plan.originalArchiveSha256 $plan.archiveSource.sha256
    function Assert-Stopped {
        if (Get-Process 'Serato DJ Pro' -ErrorAction SilentlyContinue) { throw 'Close Serato before changing resources' }
        foreach ($path in @($target,(Split-Path $target),(Split-Path $bundle))) { Assert-Sl3ArchiveProtectedPath $path }
    }
    function Test-RegistrationAbsent {
        if (Test-Path -LiteralPath $plan.nativeInstallation) { return $false }
        foreach ($entry in $plan.registryEntries) {
            if (Test-Path -LiteralPath ('Registry::HKEY_LOCAL_MACHINE\'+$entry.key)) { return $false }
        }
        return $true
    }
    function Invoke-Installer([string]$Action) {
        & $python -I -B "$PSScriptRoot/serato-session-installer.py" $Action --capsule $capsulePath --expected-capsule-sha256 $capsuleHash
        if ($LASTEXITCODE) { throw "Session installer failed: $Action" }
    }
    function Invoke-BrokerStop {
        & $python -I -B "$PSScriptRoot/serato-session-broker.py" stop --capsule $capsulePath --expected-capsule-sha256 $capsuleHash
        if ($LASTEXITCODE) { throw 'Broker retirement is unverified; preserve native files' }
    }
    function Rollback-OwnInstall {
        if (Test-Path -LiteralPath $receipt) {
            $result=Get-Content -LiteralPath $receipt -Raw | ConvertFrom-Json -AsHashtable
            if ($result -isnot [Collections.IDictionary] -or -not $result.Contains('successful') -or
                $result.successful -isnot [bool]) { throw 'Incomplete installation receipt; inspect its journal' }
            if ($result.Contains('stageResult') -and $result.stageResult -and
                $result.stageResult.Contains('stageRecordSha256') -and $result.stageResult.stageRecordSha256) { Invoke-Installer rollback }
        }
        if (-not (Test-RegistrationAbsent)) { throw 'Native stage or registration remains' }
    }
    if ((Get-FileHash -LiteralPath $exe).Hash.ToLowerInvariant() -cne $plan.application.sha256 -or
        (Get-AuthenticodeSignature -LiteralPath $exe).Status -ne 'Valid') { throw 'Original signed application required' }
    Assert-Stopped
    $identity=[Security.Principal.WindowsIdentity]::GetCurrent()
    try { $admin=[Security.Principal.WindowsPrincipal]::new($identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) }
    finally { $identity.Dispose() }
    $localAppData=[Environment]::GetFolderPath('LocalApplicationData')
    if (-not $localAppData) { throw 'Local AppData folder unavailable' }
    if ($Mode -eq 'Recover') {
        if (-not $admin) { throw 'Recovery requires explicit administrator elevation after ordinary-user broker stop' }
        if (Test-Path -LiteralPath $runLock) {
            $owner=Read-RunOwner $runLock
            foreach ($name in @('runner','stage')) {
                if (-not $owner.Contains($name)) { continue }
                $active=Get-Process -Id $owner[$name].pid -ErrorAction SilentlyContinue
                if ($active -and $active.StartTime.ToUniversalTime().ToFileTimeUtc().ToString() -ceq $owner[$name].created) {
                    throw 'An original session owner is still active; coordinate its shutdown before recovery'
                }
            }
        }
        if (Test-Path -LiteralPath $permit) { Invoke-Installer revoke }
        Rollback-OwnInstall
        $state=(Get-Sl3ArchiveTransactionState $tx).state
        if ($state -notin @('original','installed','rollback-staged','restored')) { throw 'Conflicting resource witnesses; preserve for review' }
        if ($state -in @('installed','rollback-staged')) { $null=Restore-Sl3ArchiveFile $tx ${function:Assert-Stopped} }
        $null=Clear-Sl3ArchiveWitnesses $tx ${function:Assert-Stopped}
        if (Test-Path -LiteralPath $bundle) {
            if ((Get-Sl3ArchiveHash $bundle) -cne $plan.installerResource.sha256) { throw 'Installer resource differs; preserve it' }
            Assert-Sl3ArchiveProtectedPath $bundle
            [IO.File]::Delete($bundle)
        }
        & $python -I -B "$PSScriptRoot/retire-serato-session-cache.py" --local-app-data $localAppData --expected-launcher-sha256 $plan.launcher.sha256 --retire
        if ($LASTEXITCODE) { throw 'Recovered resources but launcher cache retirement needs review' }
        'Owned session resources recovered'; return
    }
    Invoke-Installer plan
    if ((Get-Sl3ArchiveTransactionState $tx).state -ne 'original' -or -not (Test-RegistrationAbsent)) {
        throw 'Original resources and absent temporary native installation required'
    }
    foreach ($path in @($bundle,($bundle+'.sl3-pending'),$permit,$receipt,$ready,$release,$final,$clean,$session,$plan.pointerPath,
                        ($plan.pointerPath+'.pending'),($session+'.stdout'),($session+'.stderr'),
                        ($session+'.closed'),($session+'.lock'),($session+'.pointer.json'),
                        (Join-Path $directory 'broker-timing.txt'),(Join-Path $directory 'broker-input.conf'),
                        (Join-Path $directory 'broker-start-failure.json'),(Join-Path $directory 'broker-stop-failure.json'),
                        (Join-Path $directory 'output-capture'),$plan.hostOutput)) {
        if (Test-Path -LiteralPath $path) { throw "Fresh session state required: $([IO.Path]::GetFileName($path))" }
    }
    if ($Mode -in @('Plan','Run')) {
        if (Test-Path -LiteralPath $runLock) { throw 'A previous or active run owns this capsule; preserve its records' }
        $cache=& $python -I -B "$PSScriptRoot/retire-serato-session-cache.py" --local-app-data $localAppData --expected-launcher-sha256 $plan.launcher.sha256
        if ($LASTEXITCODE -or ($cache | ConvertFrom-Json).cachedLauncherPresent) { throw 'Review the existing launcher cache before a fresh run' }
    }
    if ($Mode -eq 'Plan') { 'Complete session plan passed; no application, broker or elevation started'; return }
    if ($Mode -eq 'Stage') {
        if (-not $admin) { throw 'Protected staging requires explicit administrator elevation' }
        $owner=Read-RunOwner $runLock
        $runnerProcess=Get-Process -Id $owner.runner.pid -ErrorAction Stop
        $null=$runnerProcess.Handle
        if ($runnerProcess.HasExited -or $runnerProcess.StartTime.ToUniversalTime().ToFileTimeUtc().ToString() -cne $owner.runner.created) {
            throw 'Original desktop runner identity is unavailable'
        }
        $supervisorState=@{permitIssued=$false;completed=$false}
        $report=@{restored=$false;registrationAbsent=$false;receiptState='absent';error=$null}
        try {
            Invoke-Sl3InstallerResourceTest $tx $plan.archiveSource.path $plan.installerResource.path $plan.installerResource.sha256 {
                Assert-Stopped
                if ($supervisorState.permitIssued -and (Test-Path -LiteralPath $permit)) { throw 'Installer permit remains' }
            } {
                try {
                    Write-New $permit (@{bundleSha256=$plan.nativeBundle.sha256;
                        expiresUnix=[DateTimeOffset]::UtcNow.AddSeconds($plan.permitLimitSeconds).ToUnixTimeSeconds()} | ConvertTo-Json -Compress)
                    $supervisorState.permitIssued=$true
                    Assert-Sl3ArchiveProtectedPath $permit
                    Write-New $ready 'staged'
                    $deadline=[Environment]::TickCount64+1000*$plan.stageLimitSeconds
                    while (-not (Test-Path -LiteralPath $release) -and -not $runnerProcess.HasExited -and
                           [Environment]::TickCount64 -lt $deadline) { Start-Sleep -Milliseconds 200 }
                } finally {
                    if ($supervisorState.permitIssued) { Invoke-Installer revoke }
                    Assert-Stopped
                    if ((Test-Path -LiteralPath $receipt) -or (Test-Path -LiteralPath $session)) {
                        if (-not (Test-Path -LiteralPath $clean) -or (Test-Path -LiteralPath $plan.pointerPath) -or
                            (Get-Content -LiteralPath $clean -Raw | ConvertFrom-Json).controllerExited -ne $true) {
                            throw 'Broker cleanup is unverified; preserve native stage for recovery'
                        }
                    }
                    if (Test-Path -LiteralPath $receipt) {
                        $report.receiptState='incomplete'
                        $result=Get-Content -LiteralPath $receipt -Raw | ConvertFrom-Json -AsHashtable
                        if ($result.successful -isnot [bool]) { throw 'Incomplete installer result' }
                        $report.receiptState=if ($result.successful) { 'success' } else { 'failed' }
                    }
                    Rollback-OwnInstall
                    $supervisorState.completed=$true
                }
            }
        } catch { $report.error=$_.Exception.Message }
        finally {
            $report.restored=(Get-Sl3ArchiveTransactionState $tx).state -eq 'original' -and -not (Test-Path -LiteralPath $bundle)
            $report.registrationAbsent=$supervisorState.completed -and (Test-RegistrationAbsent)
            Write-New $final ($report | ConvertTo-Json)
        }
        if ($report.error -or -not $report.restored -or -not $report.registrationAbsent) { throw 'Protected session requires recovery; inspect session-final.json' }
        return
    }
    if ($admin) { throw 'Run must start from the ordinary desktop token' }
    $runLease=[IO.File]::Open($runLock,'CreateNew','ReadWrite','Read')
    $leases.Add($runLease)
    $runOwner=@{runner=@{pid=$PID;created=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToFileTimeUtc().ToString()}}
    function Save-RunOwner {
        $runLease.Position=0; $runLease.SetLength(0)
        $runLease.Write([Text.Encoding]::UTF8.GetBytes(($runOwner | ConvertTo-Json -Depth 4 -Compress))); $runLease.Flush($true)
    }
    Save-RunOwner
    $helper=Start-Process -FilePath (Get-Process -Id $PID).Path -Verb RunAs -WindowStyle Hidden -PassThru -ArgumentList @(
        '-NoProfile','-File',('"{0}"' -f $PSCommandPath),'-Mode','Stage','-SessionPlan',('"{0}"' -f $SessionPlan),
        '-ExpectedPlanSha256',$ExpectedPlanSha256)
    try {
        $runOwner.stage=@{pid=$helper.Id;created=$helper.StartTime.ToUniversalTime().ToFileTimeUtc().ToString()}
        Save-RunOwner
        $deadline=[Environment]::TickCount64+20000
        while (-not (Test-Path -LiteralPath $ready) -and -not $helper.HasExited -and [Environment]::TickCount64 -lt $deadline) { Start-Sleep -Milliseconds 150 }
        if (-not (Test-Path -LiteralPath $ready) -or $helper.HasExited) { throw 'Protected resources did not stage' }
        $traceArguments=@()
        if ($plan.asioPrivateTrace) { $traceArguments=@('--asio-private-trace') }
        & $python -I -B "$PSScriptRoot/run-serato-startup-session.py" @traceArguments --run --prepared $plan.preparedShim.path `
            --expected-preparation-sha256 $plan.preparedShim.sha256 --app $exe --bundle $plan.nativeBundle.path `
            --expected-bundle-sha256 $plan.nativeBundle.sha256 --expected-installer-bundle-sha256 $plan.installerResource.sha256 `
            --output $plan.hostOutput --frida-directory $plan.fridaDirectory `
            --launcher-capsule $capsulePath --expected-launcher-capsule-sha256 $capsuleHash
        $hostExit=$LASTEXITCODE
        if ($hostExit) { throw 'Application supervision failed; preserve its result while completing independent cleanup' }
    } finally {
        Assert-Stopped
        Invoke-BrokerStop
        Write-New $release 'rollback'
        if (-not $helper.WaitForExit(50000)) { throw 'Protected stage helper remains active' }
        Get-Content -LiteralPath $final
        if ($helper.ExitCode) { throw 'Protected stage helper requires recovery' }
        Assert-Stopped
        & $python -I -B "$PSScriptRoot/retire-serato-session-cache.py" --local-app-data $localAppData --expected-launcher-sha256 $plan.launcher.sha256 --retire
        if ($LASTEXITCODE) { throw 'Cached launcher retirement needs review' }
    }
} finally {
    if ($runnerProcess) { $runnerProcess.Dispose() }
    foreach ($stream in $leases) { $stream.Dispose() }
}
