#requires -Version 7.5
# Actual owned temporary files; no protected paths, elevation or applications.
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../scripts/serato-installer-resource-transaction.ps1')
$root=Join-Path ([IO.Path]::GetTempPath()) ('sl3-session-resource-tests-'+[Guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory -Path $root
$passed=0
function Assert([bool]$Value,[string]$Text) { if (-not $Value) { throw $Text } }
function Fixture([string]$Name) {
    $directory=Join-Path $root $Name
    $null=New-Item -ItemType Directory -Path (Join-Path $directory 'bundles')
    $null=New-Item -ItemType Directory -Path (Join-Path $directory 'source')
    $target=Join-Path $directory 'userio_resources.bin'
    $candidate=Join-Path $directory 'candidate.bin'
    $source=Join-Path $directory 'source/8c7758f23375cee18a9cf3be4a3acc15.bin'
    [IO.File]::WriteAllText($target,'original fixture')
    [IO.File]::WriteAllText($candidate,'candidate fixture')
    [IO.File]::WriteAllText($source,'own launcher resource fixture')
    return @{tx=(New-Sl3ArchiveTransaction $target (Get-Sl3ArchiveHash $target) (Get-Sl3ArchiveHash $candidate));
             candidate=$candidate;source=$source;sha=(Get-Sl3ArchiveHash $source);
             bundle=(Join-Path $directory 'bundles/8c7758f23375cee18a9cf3be4a3acc15.bin')}
}
try {
    foreach ($scenario in @('normal','body-failure','busy-cleanup','foreign-resource')) {
        $f=Fixture $scenario
        $supervisorState=@{permitIssued=$false;busy=$false;guards=0}
        $guard={
            $supervisorState.guards++
            if ($supervisorState.busy) { throw 'fixture application busy' }
            if ($supervisorState.permitIssued) { throw 'fixture permit still issued' }
        }
        $caught=$null
        try {
            Invoke-Sl3InstallerResourceTest $f.tx $f.candidate $f.source $f.sha $guard {
                Assert ((Get-Sl3ArchiveTransactionState $f.tx).state -eq 'installed') 'Candidate not installed in body'
                Assert ((Get-Sl3ArchiveHash $f.bundle) -eq $f.sha) 'Installer resource not installed in body'
                $supervisorState.permitIssued=$true
                $supervisorState.permitIssued=$false
                if ($scenario -eq 'body-failure') { throw 'fixture body failed' }
                if ($scenario -eq 'busy-cleanup') { $supervisorState.busy=$true; throw 'fixture body ended busy' }
                if ($scenario -eq 'foreign-resource') { [IO.File]::WriteAllText($f.bundle,'foreign fixture bytes') }
            }
        } catch { $caught=$_ }
        if ($scenario -eq 'normal') {
            Assert ($null -eq $caught) ('Normal flow failed: '+$caught)
            Assert ((Get-Sl3ArchiveTransactionState $f.tx).state -eq 'original') 'Normal rollback incomplete'
            Assert (-not (Test-Path -LiteralPath $f.bundle)) 'Owned resource not removed'
        } elseif ($scenario -eq 'body-failure') {
            Assert ($caught.Exception.Message -match 'body failed') 'Original body error lost'
            Assert ((Get-Sl3ArchiveTransactionState $f.tx).state -eq 'original') 'Body failure lost original archive'
            Assert (-not (Test-Path -LiteralPath $f.bundle)) 'Body failure retained owned resource unnecessarily'
        } elseif ($scenario -eq 'busy-cleanup') {
            Assert ($caught.Exception.Message -match 'application busy') 'Busy application not refused'
            Assert ((Get-Sl3ArchiveTransactionState $f.tx).state -eq 'installed') 'Busy cleanup changed live archive'
            Assert ((Get-Sl3ArchiveHash $f.bundle) -eq $f.sha) 'Busy cleanup deleted resource'
            $supervisorState.busy=$false
            $null=Restore-Sl3ArchiveFile $f.tx $guard
            $null=Clear-Sl3ArchiveWitnesses $f.tx $guard
        } else {
            Assert ($caught.Exception.Message -match 'bundle changed') 'Foreign resource not detected'
            Assert ((Get-Sl3ArchiveTransactionState $f.tx).state -eq 'original') 'Foreign-resource conflict lost original archive'
            Assert ([IO.File]::ReadAllText($f.bundle) -eq 'foreign fixture bytes') 'Unknown resource was deleted'
        }
        Assert ($supervisorState.guards -ge 3) 'Quiescence was not rechecked'
        $passed++
    }
    @{passed=$passed;temporaryFilesOnly=$true;protectedFilesModified=$false;applicationStarted=$false}|ConvertTo-Json -Compress
} finally {
    $absolute=[IO.Path]::GetFullPath($root)
    $temporary=[IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if (-not $absolute.StartsWith($temporary,[StringComparison]::OrdinalIgnoreCase) -or
        [IO.Path]::GetFileName($absolute) -notlike 'sl3-session-resource-tests-*') { throw 'Temporary cleanup scope differs' }
    Remove-Item -LiteralPath $absolute -Recurse -Force
}
