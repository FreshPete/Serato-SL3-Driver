#requires -Version 7.5
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../scripts/serato-archive-file-transaction.ps1')
$root=Join-Path ([IO.Path]::GetTempPath()) ('sl3-archive-transaction-tests-'+[Guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory -Path $root
$checks=[Collections.Generic.List[string]]::new()
function Assert([bool]$Ok,[string]$Message){if(-not $Ok){throw $Message}}
function Check([string]$Name,[scriptblock]$Body){& $Body;$checks.Add($Name)}
function Reject([scriptblock]$Body,[string]$Pattern){
    $caught=$null
    try{$null=& $Body}catch{$caught=$_}
    Assert ($null -ne $caught -and $caught.Exception.Message -match $Pattern) ('Expected refusal: '+$Pattern+'; actual: '+$caught)
}
function Fixture([string]$Name){
    $dir=Join-Path $root $Name;$null=New-Item -ItemType Directory -Path $dir
    $target=Join-Path $dir 'userio_resources.bin';$candidate=Join-Path $dir 'candidate.bin'
    [IO.File]::WriteAllText($target,('original fixture '+$Name));[IO.File]::WriteAllText($candidate,('candidate fixture '+$Name))
    $t=New-Sl3ArchiveTransaction $target (Get-Sl3ArchiveHash $target) (Get-Sl3ArchiveHash $candidate)
    return [pscustomobject]@{t=$t;source=$candidate}
}
$quiet={}
try{
    Check 'atomic-install-rollback-and-cleanup' {
        $f=Fixture 'roundtrip';$t=$f.t
        Assert ((Get-Sl3ArchiveTransactionState $t).state -eq 'original') 'Initial state'
        Assert ((Install-Sl3ArchiveFile $t $f.source $quiet).state -eq 'installed') 'Installed state'
        Assert ((Get-Sl3ArchiveHash $t.Backup) -ceq $t.OriginalSha256) 'Backup identity'
        Reject {Install-Sl3ArchiveFile $t $f.source $quiet} 'Original or verified'
        Assert ((Restore-Sl3ArchiveFile $t $quiet).state -eq 'restored') 'Restored state'
        Assert ((Get-Sl3ArchiveHash $t.Backup) -ceq $t.OriginalSha256) 'Original backup retained'
        Assert ((Get-Sl3ArchiveHash $t.Retired) -ceq $t.CandidateSha256) 'Displaced candidate retained'
        Assert ((Clear-Sl3ArchiveWitnesses $t $quiet).state -eq 'original') 'Cleanup state'
        Assert ((Get-ChildItem -LiteralPath (Split-Path $t.Target)).Count -eq 2) 'Only original and independent candidate remain'
    }
    Check 'wrong-candidate-refused' {
        $f=Fixture 'wrong-source';[IO.File]::WriteAllText($f.source,'changed')
        Reject {Install-Sl3ArchiveFile $f.t $f.source $quiet} 'Candidate source differs'
        Assert ((Get-Sl3ArchiveTransactionState $f.t).state -eq 'original') 'Source refusal mutated target'
    }
    Check 'changed-target-preserved' {
        $f=Fixture 'changed-target';[IO.File]::WriteAllText($f.t.Target,'unrelated new archive')
        Reject {Install-Sl3ArchiveFile $f.t $f.source $quiet} 'Original or verified'
        Reject {Clear-Sl3ArchiveWitnesses $f.t $quiet} 'Verified original live'
        Assert ([IO.File]::ReadAllText($f.t.Target) -eq 'unrelated new archive') 'Unknown target lost'
    }
    Check 'busy-before-stage-refused' {
        $f=Fixture 'busy-first'
        Reject {Install-Sl3ArchiveFile $f.t $f.source {throw 'fixture busy'}} 'fixture busy'
        Assert ((Get-Sl3ArchiveTransactionState $f.t).state -eq 'original') 'Busy stage changed target'
    }
    Check 'busy-after-stage-cancelled' {
        $f=Fixture 'busy-second';$script:guardCalls=0
        Reject {Install-Sl3ArchiveFile $f.t $f.source {$script:guardCalls++;if($script:guardCalls -eq 2){throw 'fixture busy'}}} 'fixture busy'
        Assert ((Get-Sl3ArchiveTransactionState $f.t).state -eq 'install-staged') 'Verified stage not retained'
        Assert ((Clear-Sl3ArchiveWitnesses $f.t $quiet).state -eq 'original') 'Stage cancellation failed'
    }
    Check 'verified-install-stage-resumes' {
        $f=Fixture 'resume-install';Write-Sl3ArchiveStage $f.source $f.t.Stage $f.t.CandidateSha256
        Assert ((Install-Sl3ArchiveFile $f.t $f.source $quiet).state -eq 'installed') 'Install did not resume'
        $null=Restore-Sl3ArchiveFile $f.t $quiet;$null=Clear-Sl3ArchiveWitnesses $f.t $quiet
    }
    Check 'rollback-busy-preserves-installed' {
        $f=Fixture 'rollback-busy';$null=Install-Sl3ArchiveFile $f.t $f.source $quiet
        Reject {Restore-Sl3ArchiveFile $f.t {throw 'fixture busy'}} 'fixture busy'
        Assert ((Get-Sl3ArchiveTransactionState $f.t).state -eq 'installed') 'Busy rollback changed target'
    }
    Check 'verified-rollback-stage-resumes' {
        $f=Fixture 'resume-rollback';$null=Install-Sl3ArchiveFile $f.t $f.source $quiet;$script:guardCalls=0
        Reject {Restore-Sl3ArchiveFile $f.t {$script:guardCalls++;if($script:guardCalls -eq 2){throw 'fixture busy'}}} 'fixture busy'
        Assert ((Get-Sl3ArchiveTransactionState $f.t).state -eq 'rollback-staged') 'Rollback stage not retained'
        Assert ((Restore-Sl3ArchiveFile $f.t $quiet).state -eq 'restored') 'Rollback did not resume'
    }
    Check 'unknown-backup-not-overwritten' {
        $f=Fixture 'foreign-backup';[IO.File]::WriteAllText($f.t.Backup,'unknown backup')
        Reject {Install-Sl3ArchiveFile $f.t $f.source $quiet} 'Original or verified'
        Reject {Clear-Sl3ArchiveWitnesses $f.t $quiet} 'Verified original live'
        Assert ([IO.File]::ReadAllText($f.t.Backup) -eq 'unknown backup') 'Foreign backup overwritten'
    }
    Check 'partial-stage-preserved' {
        $f=Fixture 'partial';[IO.File]::WriteAllText($f.t.Stage,'partial stage')
        Reject {Install-Sl3ArchiveFile $f.t $f.source $quiet} 'Original or verified'
        Reject {Clear-Sl3ArchiveWitnesses $f.t $quiet} 'Verified original live'
        Assert ([IO.File]::ReadAllText($f.t.Stage) -eq 'partial stage') 'Partial witness lost'
    }
    Check 'derived-path-tampering-refused' {
        $f=Fixture 'paths';$f.t.Backup=$f.source
        Reject {Get-Sl3ArchiveTransactionState $f.t} 'path identity differs'
    }
    Check 'stage-source-alias-refused' {
        $f=Fixture 'alias';Write-Sl3ArchiveStage $f.source $f.t.Stage $f.t.CandidateSha256
        Reject {Install-Sl3ArchiveFile $f.t $f.t.Stage $quiet} 'Independent candidate'
    }
    Check 'target-change-during-guard-refused' {
        $f=Fixture 'race';$script:guardCalls=0
        Reject {Install-Sl3ArchiveFile $f.t $f.source {$script:guardCalls++;if($script:guardCalls -eq 2){[IO.File]::WriteAllText($f.t.Target,'changed by fixture')}}} 'Install state changed'
        Assert ([IO.File]::ReadAllText($f.t.Target) -eq 'changed by fixture') 'Changed target overwritten'
        Assert (-not (Test-Path -LiteralPath $f.t.Backup)) 'Unexpected backup'
    }
    Check 'exclusive-stage-creation' {
        $f=Fixture 'create-race'
        Reject {Install-Sl3ArchiveFile $f.t $f.source {[IO.File]::WriteAllText($f.t.Stage,'racing fixture')}} 'already exists'
        Assert ([IO.File]::ReadAllText($f.t.Stage) -eq 'racing fixture') 'Existing stage overwritten'
    }
    Check 'locked-live-file-fails-with-original-retained' {
        $f=Fixture 'locked';$held=[IO.File]::Open($f.t.Target,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
        try{Reject {Install-Sl3ArchiveFile $f.t $f.source $quiet} 'being used by another process'}finally{$held.Dispose()}
        Assert ((Get-Sl3ArchiveTransactionState $f.t).state -eq 'install-staged') 'Failed replacement lost original/stage'
        $null=Install-Sl3ArchiveFile $f.t $f.source $quiet;$null=Restore-Sl3ArchiveFile $f.t $quiet
    }
    Check 'destination-acl-preserved' {
        $f=Fixture 'acl';$acl=Get-Acl -LiteralPath $f.t.Target;$acl.SetAccessRuleProtection($true,$true);Set-Acl -LiteralPath $f.t.Target -AclObject $acl
        $before=(Get-Acl -LiteralPath $f.t.Target).Sddl
        $null=Install-Sl3ArchiveFile $f.t $f.source $quiet
        Assert ((Get-Acl -LiteralPath $f.t.Target).Sddl -ceq $before) 'Install destination ACL changed'
        $null=Restore-Sl3ArchiveFile $f.t $quiet
        Assert ((Get-Acl -LiteralPath $f.t.Target).Sddl -ceq $before) 'Rollback destination ACL changed'
    }
    Check 'junction-parent-refused' {
        $f=Fixture 'junction-source';$junction=Join-Path $root 'junction-alias'
        $null=New-Item -ItemType Junction -Path $junction -Target (Split-Path $f.t.Target)
        try{Reject {Get-Sl3ArchiveHash (Join-Path $junction 'userio_resources.bin')} 'Reparse path refused'}finally{[IO.Directory]::Delete($junction)}
    }
    Check 'identity-and-filename-validation' {
        $f=Fixture 'identity'
        Reject {New-Sl3ArchiveTransaction $f.t.Target $f.t.OriginalSha256 $f.t.OriginalSha256} 'Distinct lowercase'
        Reject {New-Sl3ArchiveTransaction $f.t.Target $f.t.OriginalSha256.ToUpperInvariant() $f.t.CandidateSha256} 'Distinct lowercase'
        Reject {New-Sl3ArchiveTransaction $f.source $f.t.OriginalSha256 $f.t.CandidateSha256} 'Exact resource filename'
    }
    Check 'corrupt-backup-refuses-rollback-and-cleanup' {
        $f=Fixture 'corrupt-backup';$null=Install-Sl3ArchiveFile $f.t $f.source $quiet
        [IO.File]::WriteAllText($f.t.Backup,'unknown backup bytes')
        Reject {Restore-Sl3ArchiveFile $f.t $quiet} 'Verified installed state'
        Reject {Clear-Sl3ArchiveWitnesses $f.t $quiet} 'Verified original live'
        Assert ((Get-Sl3ArchiveHash $f.t.Target) -ceq $f.t.CandidateSha256) 'Candidate modified after refusal'
        Assert ([IO.File]::ReadAllText($f.t.Backup) -eq 'unknown backup bytes') 'Corrupt evidence removed'
    }
    Check 'missing-backup-refuses-rollback' {
        $f=Fixture 'missing-backup';$null=Install-Sl3ArchiveFile $f.t $f.source $quiet
        [IO.File]::Delete($f.t.Backup)
        Reject {Restore-Sl3ArchiveFile $f.t $quiet} 'Verified installed state'
        Assert ((Get-Sl3ArchiveHash $f.t.Target) -ceq $f.t.CandidateSha256) 'Candidate lost without backup'
    }
    Check 'busy-cleanup-preserves-restored-witnesses' {
        $f=Fixture 'cleanup-busy';$null=Install-Sl3ArchiveFile $f.t $f.source $quiet;$null=Restore-Sl3ArchiveFile $f.t $quiet
        Reject {Clear-Sl3ArchiveWitnesses $f.t {throw 'fixture busy'}} 'fixture busy'
        Assert ((Get-Sl3ArchiveTransactionState $f.t).state -eq 'restored') 'Cleanup removed witnesses despite guard'
    }
    Check 'ordinary-user-owned-deployment-path-refused' {
        $f=Fixture 'unprotected-owner'
        Reject {Assert-Sl3ArchiveProtectedPath $f.t.Target} 'Protected archive path owner required'
    }
    [ordered]@{schema='sl3.archive-file-transaction-tests.v1';passed=$checks.Count;checks=@($checks);
        realWindowsAtomicReplacements=$true;fixtureOnly=$true;installedApplicationModified=$false;deviceAccess=$false}|ConvertTo-Json -Depth 4
}finally{
    $resolved=[IO.Path]::GetFullPath($root);$parent=[IO.Path]::GetDirectoryName($resolved)
    if($parent.TrimEnd('\') -cne ([IO.Path]::GetTempPath()).TrimEnd('\') -or -not ([IO.Path]::GetFileName($resolved).StartsWith('sl3-archive-transaction-tests-'))){throw 'Owned temporary cleanup boundary differs'}
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
