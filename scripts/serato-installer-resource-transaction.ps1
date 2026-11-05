# Library only. The attended caller supplies its protection and quiescence checks.
. (Join-Path $PSScriptRoot 'serato-archive-file-transaction.ps1')

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
