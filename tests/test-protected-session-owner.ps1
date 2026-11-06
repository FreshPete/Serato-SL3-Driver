#requires -Version 7.5
param([Parameter(Mandatory)][string]$OutputFile)
$ErrorActionPreference='Stop'
$library=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../scripts/serato-protected-session-owner.ps1'))
. $library
$analysis=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../analysis'))
$output=[IO.Path]::GetFullPath($OutputFile)
if([IO.Path]::GetDirectoryName($output) -cne $analysis -or (Test-Path -LiteralPath $output)){throw 'Fresh analysis result required'}
$root=Join-Path $analysis ('sl3-protected-owner-fixture-'+[Guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory -Path $root
$checks=[Collections.Generic.List[string]]::new()
$a='a'*64;$b='b'*64;$other='c'*64;$quiet={};$protection={param($Path)}
function Assert([bool]$Ok,[string]$Message){if(-not $Ok){throw $Message}}
function Check([string]$Name,[scriptblock]$Body){& $Body;$checks.Add($Name)}
function Reject([scriptblock]$Body,[string]$Pattern){
    $caught=$null;try{$null=& $Body}catch{$caught=$_}
    Assert ($null -ne $caught -and $caught.Exception.Message -match $Pattern) ('Expected '+$Pattern+'; got '+$caught)
}
function Fixture([string]$Name){
    $dir=Join-Path $root $Name;$null=New-Item -ItemType Directory -Path $dir
    return (Join-Path $dir '8c7758f23375cee18a9cf3be4a3acc15.bin.sl3-session')
}
function Claim([string]$Path){return New-Sl3ProtectedSessionOwner $Path $a $b $quiet $protection}
function Release($Claim){Remove-Sl3ProtectedSessionOwner $Claim.path $a $b $quiet $protection $Claim}
Check 'claim-readable-and-creating-stage-releases' {
    $path=Fixture 'normal';$claim=Claim $path
    try {
        $owner=Get-Sl3ProtectedSessionOwner $path $protection
        Assert $owner.present 'Record missing'
        Assert ($owner.record.capsuleSha256 -ceq $a -and $owner.record.bundleSha256 -ceq $b) 'Scope differs'
        Assert (Test-Sl3ProtectedStageAlive $owner) 'Creating process not live'
        Release $claim
        Assert (-not(Test-Path -LiteralPath $path)) 'Owner record remains'
    } finally {$claim.lease.Dispose()}
}
Check 'second-session-cannot-claim-same-slot' {
    $path=Fixture 'collision';$claim=Claim $path
    try {
        $before=(Get-FileHash -LiteralPath $path).Hash
        Reject {New-Sl3ProtectedSessionOwner $path $other $b $quiet $protection} 'exist|used|sharing'
        Assert ((Get-FileHash -LiteralPath $path).Hash -ceq $before) 'Other claim changed ownership'
    } finally {Release $claim}
}
Check 'held-lease-blocks-write-and-delete' {
    $path=Fixture 'sharing';$claim=Claim $path
    try {
        Reject {[IO.File]::WriteAllText($path,'changed')} 'used|sharing|access'
        Reject {[IO.File]::Delete($path)} 'used|sharing|access'
    } finally {Release $claim}
}
Check 'another-scope-cannot-release-even-matching-bundle' {
    $path=Fixture 'wrong-scope';$claim=Claim $path
    try {
        Reject {Remove-Sl3ProtectedSessionOwner $path $other $b $quiet $protection} 'another or unknown session'
        Assert (Test-Path -LiteralPath $path) 'Foreign scope removed record'
    } finally {Release $claim}
}
Check 'ordinary-recovery-cannot-release-live-stage' {
    $path=Fixture 'live';$claim=Claim $path
    try {Reject {Remove-Sl3ProtectedSessionOwner $path $a $b $quiet $protection} 'remains active'}
    finally {Release $claim}
}
Check 'exited-stage-record-can-be-retired' {
    $path=Fixture 'retired'
    $code=@'
$ErrorActionPreference='Stop'
. ([Environment]::GetEnvironmentVariable('SL3_OWNER_LIBRARY'))
$claim=New-Sl3ProtectedSessionOwner ([Environment]::GetEnvironmentVariable('SL3_OWNER_PATH')) ('a'*64) ('b'*64) {} {param($Path)}
$claim.lease.Dispose()
'@
    $start=[Diagnostics.ProcessStartInfo]::new((Get-Process -Id $PID).Path)
    $start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    foreach($argument in @('-NoLogo','-NoProfile','-NonInteractive','-EncodedCommand',[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($code)))){$start.ArgumentList.Add($argument)}
    $start.Environment['SL3_OWNER_LIBRARY']=$library;$start.Environment['SL3_OWNER_PATH']=$path
    $child=[Diagnostics.Process]::Start($start)
    try {
        if(-not $child.WaitForExit(10000)){$child.Kill();throw 'Owned child timed out'}
        Assert ($child.ExitCode -eq 0) ('Owned child failed: '+$child.StandardError.ReadToEnd())
        $owner=Get-Sl3ProtectedSessionOwner $path $protection
        Assert (-not(Test-Sl3ProtectedStageAlive $owner)) 'Exited owner still active'
        $reader=[IO.File]::Open($path,'Open','Read','Read')
        try {
            Reject {Remove-Sl3ProtectedSessionOwner $path $a $b $quiet $protection} 'used|sharing|access'
            Assert (Test-Path -LiteralPath $path) 'Concurrent recovery reader lost ownership barrier'
        } finally {$reader.Dispose()}
        Remove-Sl3ProtectedSessionOwner $path $a $b $quiet $protection
        Assert (-not(Test-Path -LiteralPath $path)) 'Retired owner record remains'
    } finally {$child.Dispose()}
}
Check 'malformed-record-preserved' {
    $path=Fixture 'malformed';[IO.File]::WriteAllText($path,'not-json');$before=(Get-FileHash -LiteralPath $path).Hash
    Reject {Remove-Sl3ProtectedSessionOwner $path $a $b $quiet $protection} 'JSON|Unexpected|invalid'
    Assert ((Get-FileHash -LiteralPath $path).Hash -ceq $before) 'Malformed record changed'
}
Check 'changed-record-not-released-by-stale-lease-object' {
    $path=Fixture 'changed';$claim=Claim $path;$claim.lease.Dispose()
    $record=$claim.owner.record;$record.capsuleSha256=$other
    [IO.File]::WriteAllText($path,($record|ConvertTo-Json -Depth 4 -Compress))
    Reject {Release $claim} 'another or unknown session'
    Assert (Test-Path -LiteralPath $path) 'Changed record deleted'
}
Check 'busy-or-unprotected-claim-refused-before-creation' {
    $path=Fixture 'guards'
    Reject {New-Sl3ProtectedSessionOwner $path $a $b {throw 'owner busy'} $protection} 'owner busy'
    Assert (-not(Test-Path -LiteralPath $path)) 'Busy claim created record'
    Reject {New-Sl3ProtectedSessionOwner $path $a $b $quiet {param($Path)throw 'unprotected'}} 'unprotected'
    Assert (-not(Test-Path -LiteralPath $path)) 'Unprotected claim created record'
}
Check 'reparse-parent-refused' {
    $target=Join-Path $root 'junction-target';$null=New-Item -ItemType Directory -Path $target
    $link=Join-Path $root 'junction';$null=New-Item -ItemType Junction -Path $link -Target $target
    $path=Join-Path $link '8c7758f23375cee18a9cf3be4a3acc15.bin.sl3-session'
    Reject {Claim $path} 'Reparse'
    Assert (-not(Test-Path -LiteralPath $path)) 'Reparse claim created record'
}
$result=[ordered]@{schema='sl3.protected-session-owner-tests.v1';passed=$checks.Count;checks=@($checks);
    realWindowsFileSharing=$true;ownedChildExited=$true;fixtureOnly=$true;productionAclMutationValidated=$false;
    installedApplicationModified=$false;deviceAccess=$false;elevationRequested=$false}
[IO.File]::WriteAllText($output,($result|ConvertTo-Json -Depth 4)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$result|ConvertTo-Json -Depth 4
