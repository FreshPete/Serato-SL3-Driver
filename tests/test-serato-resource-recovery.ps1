#requires -Version 7.5
param([Parameter(Mandatory)][string]$OutputFile)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../scripts/serato-installer-resource-transaction.ps1')
$analysis=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../analysis'))
$output=[IO.Path]::GetFullPath($OutputFile)
if ([IO.Path]::GetDirectoryName($output) -cne $analysis -or (Test-Path -LiteralPath $output)) { throw 'Fresh analysis result required' }
$root=Join-Path $analysis ('sl3-resource-recovery-fixture-'+[Guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory -Path $root
$checks=[Collections.Generic.List[string]]::new()
function Assert([bool]$Ok,[string]$Message){if(-not $Ok){throw $Message}}
function Check([string]$Name,[scriptblock]$Body){& $Body;$checks.Add($Name)}
function Reject([scriptblock]$Body,[string]$Pattern){
    $caught=$null;try{$null=& $Body}catch{$caught=$_}
    Assert ($null -ne $caught -and $caught.Exception.Message -match $Pattern) ('Expected refusal '+$Pattern+'; got '+$caught)
}
$quiet={}
# Fixture callback deliberately does not assert production ACLs. The session
# wrapper passes the real protected-path validator; this test never elevates.
$protection={param($Path) if(-not (Test-Path -LiteralPath $Path)){throw 'Fixture path missing'}}
function Fixture([string]$Name,[string]$State='original'){
    $dir=Join-Path $root $Name;$null=New-Item -ItemType Directory -Path (Join-Path $dir 'bundles')
    $target=Join-Path $dir 'userio_resources.bin';$source=Join-Path $dir 'candidate.bin'
    [IO.File]::WriteAllText($target,('original '+$Name));[IO.File]::WriteAllText($source,('candidate '+$Name))
    $t=New-Sl3ArchiveTransaction $target (Get-Sl3ArchiveHash $target) (Get-Sl3ArchiveHash $source)
    if($State -eq 'install-staged'){Write-Sl3ArchiveStage $source $t.Stage $t.CandidateSha256}
    elseif($State -in @('installed','rollback-staged','restored')){
        $null=Install-Sl3ArchiveFile $t $source $quiet
        if($State -eq 'rollback-staged'){Write-Sl3ArchiveStage $t.Backup $t.Stage $t.OriginalSha256}
        if($State -eq 'restored'){$null=Restore-Sl3ArchiveFile $t $quiet}
    }
    $bundle=Join-Path $dir 'bundles/8c7758f23375cee18a9cf3be4a3acc15.bin'
    $bundleSource=Join-Path $dir 'reviewed-installer.bin'
    [IO.File]::WriteAllText($bundleSource,('reviewed installer '+$Name))
    return [pscustomobject]@{dir=$dir;t=$t;bundle=$bundle;pending=($bundle+'.sl3-pending');source=$bundleSource;
        hash=(Get-Sl3ArchiveHash $bundleSource)}
}
function Snapshot($Fixture){
    $files=[ordered]@{}
    foreach($file in (Get-ChildItem -LiteralPath $Fixture.dir -Recurse -File | Sort-Object FullName)){
        $files[[IO.Path]::GetRelativePath($Fixture.dir,$file.FullName)]=(Get-FileHash -LiteralPath $file.FullName).Hash
    }
    return ($files | ConvertTo-Json -Compress)
}
function Recover($Fixture,[scriptblock]$Guard=$quiet,[scriptblock]$Protect=$protection){
    return Restore-Sl3InstallerResourceState $Fixture.t $Fixture.hash $Guard $Protect
}
function Original($Fixture){
    Assert ((Get-Sl3ArchiveTransactionState $Fixture.t).state -eq 'original') 'Original archive not restored'
    Assert (-not (Test-Path -LiteralPath $Fixture.bundle) -and -not (Test-Path -LiteralPath $Fixture.pending)) 'Installer copies remain'
}
Check 'clean-original-no-op' {
    $f=Fixture 'clean';$before=Snapshot $f;$r=Recover $f
    Assert ($r.restored -and -not $r.bundleRemoved -and -not $r.pendingRemoved) 'Wrong clean result'
    Assert ((Snapshot $f) -ceq $before) 'No-op changed files'
}
Check 'staged-archive-and-pending-installer-recovered' {
    $f=Fixture 'install-staged' 'install-staged';[IO.File]::Copy($f.source,$f.pending)
    $before=Snapshot $f;$plan=Get-Sl3InstallerResourceRecoveryPlan $f.t $f.hash $quiet $protection
    Assert ($plan.archiveState -eq 'install-staged' -and $plan.pendingPresent -and -not $plan.filesWritten) 'Wrong read-only plan'
    Assert ((Snapshot $f) -ceq $before) 'Planning changed files'
    $r=Recover $f;Original $f;Assert $r.pendingRemoved 'Pending copy not reported'
}
Check 'installed-archive-and-published-installer-recovered' {
    $f=Fixture 'installed' 'installed';[IO.File]::Copy($f.source,$f.bundle)
    $r=Recover $f;Original $f;Assert $r.bundleRemoved 'Published copy not reported'
}
Check 'rollback-stage-resumes-recovery' {
    $f=Fixture 'rollback' 'rollback-staged';[IO.File]::Copy($f.source,$f.bundle)
    $null=Recover $f;Original $f
}
Check 'restored-witnesses-and-both-matching-installer-copies-cleared' {
    $f=Fixture 'restored' 'restored';[IO.File]::Copy($f.source,$f.bundle);[IO.File]::Copy($f.source,$f.pending)
    $null=Recover $f;Original $f
}
Check 'unknown-pending-copy-preserves-every-resource-before-mutation' {
    $f=Fixture 'bad-pending' 'installed';[IO.File]::Copy($f.source,$f.bundle);[IO.File]::WriteAllText($f.pending,'unknown pending')
    $before=Snapshot $f;Reject {Recover $f} 'pending copy differs';Assert ((Snapshot $f) -ceq $before) 'Unknown pending caused mutation'
}
Check 'unknown-published-copy-preserves-every-resource-before-mutation' {
    $f=Fixture 'bad-bundle' 'installed';[IO.File]::WriteAllText($f.bundle,'unknown published')
    $before=Snapshot $f;Reject {Recover $f} 'pending copy differs';Assert ((Snapshot $f) -ceq $before) 'Unknown bundle caused mutation'
}
Check 'conflicting-archive-preserves-installer-copies' {
    $f=Fixture 'bad-archive' 'installed';[IO.File]::Copy($f.source,$f.bundle);[IO.File]::WriteAllText($f.t.Backup,'unknown backup')
    $before=Snapshot $f;Reject {Recover $f} 'Conflicting archive';Assert ((Snapshot $f) -ceq $before) 'Conflict caused mutation'
}
Check 'busy-owner-refuses-before-file-mutation' {
    $f=Fixture 'busy' 'installed';[IO.File]::Copy($f.source,$f.bundle);$before=Snapshot $f
    Reject {Recover $f {throw 'fixture owner active'}} 'owner active';Assert ((Snapshot $f) -ceq $before) 'Busy recovery mutated files'
}
Check 'failed-path-protection-refuses-before-file-mutation' {
    $f=Fixture 'protection' 'installed';[IO.File]::Copy($f.source,$f.bundle);$before=Snapshot $f
    Reject {Recover $f $quiet {param($Path) throw 'fixture protection rejected'}} 'protection rejected'
    Assert ((Snapshot $f) -ceq $before) 'Rejected protection mutated files'
}
Check 'retargeted-witness-path-refused' {
    $f=Fixture 'retargeted';$before=Snapshot $f;$f.t.Stage=$f.source
    Reject {Recover $f} 'Transaction path identity differs';Assert ((Snapshot $f) -ceq $before) 'Retarget caused mutation'
}
Check 'installer-changed-during-rollback-is-preserved' {
    $f=Fixture 'late-change' 'installed';[IO.File]::Copy($f.source,$f.bundle);$script:changed=$false
    $guard={
        if(-not $script:changed -and (Get-Sl3ArchiveHash $f.t.Target) -ceq $f.t.OriginalSha256){
            [IO.File]::WriteAllText($f.bundle,'changed during recovery');$script:changed=$true
        }
    }
    Reject {Recover $f $guard} 'Installer resource changed'
    Assert ([IO.File]::ReadAllText($f.bundle) -ceq 'changed during recovery') 'Changed installer was deleted'
}
$result=[ordered]@{schema='sl3.installer-resource-recovery-tests.v1';passed=$checks.Count;checks=@($checks);
    realWindowsFileOperations=$true;fixtureOnly=$true;productionAclValidationExercised=$false;
    protectedSessionRecoveryValidated=$false;installedApplicationModified=$false;deviceAccess=$false;elevationRequested=$false}
[IO.File]::WriteAllText($output,($result | ConvertTo-Json -Depth 4)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$result | ConvertTo-Json -Depth 4
