# Library only. The attended caller supplies its protection and quiescence checks.
. (Join-Path $PSScriptRoot 'serato-archive-file-transaction.ps1')

function Get-Sl3InstallerResourceRecoveryPlan {
    param(
        [Parameter(Mandatory)]$Archive,
        [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{64}$')][string]$BundleSha256,
        [Parameter(Mandatory)][scriptblock]$AssertQuiescent,
        [Parameter(Mandatory)][scriptblock]$AssertProtectedPath
    )
    & $AssertQuiescent
    $directory=Join-Path (Split-Path $Archive.Target) 'bundles'
    $item=Get-Item -LiteralPath $directory -Force -ErrorAction Stop
    if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Existing non-reparse installer directory required'
    }
    $bundle=Join-Path $directory '8c7758f23375cee18a9cf3be4a3acc15.bin'
    $pending=$bundle+'.sl3-pending'
    foreach ($path in @($Archive.Target,$Archive.Stage,$Archive.Backup,$Archive.Retired,$bundle,$pending)) {
        & $AssertProtectedPath (Split-Path $path)
        if (Test-Path -LiteralPath $path) { & $AssertProtectedPath $path }
    }
    $state=(Get-Sl3ArchiveTransactionState $Archive).state
    if ($state -notin @('original','install-staged','installed','rollback-staged','restored')) {
        throw 'Conflicting archive witnesses; preserve for review'
    }
    foreach ($path in @($bundle,$pending)) {
        if ((Test-Path -LiteralPath $path) -and (Get-Sl3ArchiveHash $path) -cne $BundleSha256) {
            throw 'Installer resource or pending copy differs; preserve every resource witness'
        }
    }
    return [pscustomobject]@{schema='sl3.installer-resource-recovery-plan.v1';archiveState=$state;
        bundlePresent=(Test-Path -LiteralPath $bundle);pendingPresent=(Test-Path -LiteralPath $pending);
        filesWritten=$false;deviceAccess=$false}
}

function Restore-Sl3InstallerResourceState {
    param(
        [Parameter(Mandatory)]$Archive,
        [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{64}$')][string]$BundleSha256,
        [Parameter(Mandatory)][scriptblock]$AssertQuiescent,
        [Parameter(Mandatory)][scriptblock]$AssertProtectedPath
    )
    $before=Get-Sl3InstallerResourceRecoveryPlan $Archive $BundleSha256 $AssertQuiescent $AssertProtectedPath
    if ($before.archiveState -in @('installed','rollback-staged')) {
        $null=Restore-Sl3ArchiveFile $Archive $AssertQuiescent
    }
    $null=Clear-Sl3ArchiveWitnesses $Archive $AssertQuiescent
    $directory=Join-Path (Split-Path $Archive.Target) 'bundles'
    $bundle=Join-Path $directory '8c7758f23375cee18a9cf3be4a3acc15.bin'
    foreach ($path in @($bundle,($bundle+'.sl3-pending'))) {
        & $AssertQuiescent
        if (Test-Path -LiteralPath $path) {
            & $AssertProtectedPath $directory
            & $AssertProtectedPath $path
            if ((Get-Sl3ArchiveHash $path) -cne $BundleSha256) { throw 'Installer resource changed; preserve it' }
            [IO.File]::Delete($path)
        }
    }
    $after=Get-Sl3InstallerResourceRecoveryPlan $Archive $BundleSha256 $AssertQuiescent $AssertProtectedPath
    if ($after.archiveState -ne 'original' -or $after.bundlePresent -or $after.pendingPresent) {
        throw 'Resource recovery did not reach the original state'
    }
    return [pscustomobject]@{schema='sl3.installer-resource-recovery.v1';initialArchiveState=$before.archiveState;
        finalArchiveState=$after.archiveState;bundleRemoved=$before.bundlePresent;pendingRemoved=$before.pendingPresent;
        restored=$true;deviceAccess=$false}
}

function Invoke-Sl3InstallerResourceTest {
    param(
        [Parameter(Mandatory)]$Archive,
        [Parameter(Mandatory)][string]$ArchiveSource,
        [Parameter(Mandatory)][string]$BundleSource,
        [Parameter(Mandatory)][string]$BundleSha256,
        [Parameter(Mandatory)][scriptblock]$AssertQuiescent,
        [Parameter(Mandatory)][scriptblock]$RunTest
    )

    $name = '8c7758f23375cee18a9cf3be4a3acc15.bin'
    $bundleDirectory = Join-Path (Split-Path $Archive.Target) 'bundles'
    if (-not (Test-Path -LiteralPath $bundleDirectory -PathType Container)) {
        throw 'Existing installer bundle directory required'
    }
    $directoryItem = Get-Item -LiteralPath $bundleDirectory -Force
    if ($directoryItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'Reparse installer bundle directory refused'
    }
    $bundle = Join-Path $bundleDirectory $name
    $pending = $bundle + '.sl3-pending'
    if ([IO.Path]::GetFileName($BundleSource) -cne $name -or
        (Get-Sl3ArchiveHash $BundleSource) -cne $BundleSha256) {
        throw 'Reviewed installer bundle identity differs'
    }
    if ((Get-Sl3ArchiveTransactionState $Archive).state -ne 'original' -or
        (Test-Path -LiteralPath $bundle) -or (Test-Path -LiteralPath $pending)) {
        throw 'Original archive and unused installer bundle paths required'
    }
    & $AssertQuiescent

    $ownsPending = $false
    $ownsBundle = $false
    $archiveAttempted = $false
    try {
        Write-Sl3ArchiveStage $BundleSource $pending $BundleSha256
        $ownsPending = $true
        & $AssertQuiescent
        [IO.File]::Move($pending, $bundle)
        $ownsPending = $false
        $ownsBundle = $true
        $archiveAttempted = $true
        $null = Install-Sl3ArchiveFile $Archive $ArchiveSource $AssertQuiescent
        if ((Get-Sl3ArchiveHash $bundle) -cne $BundleSha256) {
            throw 'Installed bundle identity differs'
        }
        & $RunTest
    } finally {
        & $AssertQuiescent
        if ($archiveAttempted) {
            $state = (Get-Sl3ArchiveTransactionState $Archive).state
            if ($state -in @('installed', 'rollback-staged')) {
                $null = Restore-Sl3ArchiveFile $Archive $AssertQuiescent
            }
            $null = Clear-Sl3ArchiveWitnesses $Archive $AssertQuiescent
        }
        $ownedPath = if ($ownsBundle) { $bundle } elseif ($ownsPending) { $pending }
        if ($ownedPath -and (Test-Path -LiteralPath $ownedPath)) {
            if ((Get-Sl3ArchiveHash $ownedPath) -cne $BundleSha256) {
                throw 'Installer bundle changed. Preserved for review.'
            }
            [IO.File]::Delete($ownedPath)
        }
    }
}
