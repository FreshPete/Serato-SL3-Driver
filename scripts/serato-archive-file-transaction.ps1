# Library only: dot-sourcing declares functions and performs no filesystem mutation.
# The attended deployment caller must establish protected paths, reviewed package
# identity, elevation and application quiescence. No installed path is selected here.
Set-StrictMode -Version Latest

function Assert-Sl3ArchiveProtectedPath([string]$Path) {
    $trusted=@('S-1-5-18','S-1-5-32-544','S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464')
    $acl=Get-Acl -LiteralPath $Path -ErrorAction Stop
    if($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $trusted){throw 'Protected archive path owner required'}
    $raw=[Security.AccessControl.RawSecurityDescriptor]::new($acl.Sddl)
    if($null -eq $raw.DiscretionaryAcl){throw 'Null protected-path DACL refused'}
    foreach($rule in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){
        if(($rule.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) -or $rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow){continue}
        if($rule.IdentityReference.Value -notin $trusted -and ([int64]$rule.FileSystemRights -band 0x500d0156)){throw 'Protected archive path grants untrusted write/ownership access'}
    }
}

function Get-Sl3ArchiveHash([string]$Path) {
    $full=[IO.Path]::GetFullPath($Path)
    if($full.StartsWith('\\') -or $full.Substring(2).Contains(':')){throw 'Local path without streams required'}
    $item=Get-Item -LiteralPath $full -Force -ErrorAction Stop
    if($item.PSIsContainer -or $item.Length -le 0 -or $item.Length -gt 16777216){throw 'Bounded regular archive required'}
    $walk=$item
    while($null -ne $walk){
        if($walk.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Reparse path refused'}
        if($walk -is [IO.FileInfo]){$walk=$walk.Directory}else{$walk=$walk.Parent}
    }
    $stream=[IO.File]::Open($full,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    try{
        if($stream.Length -le 0 -or $stream.Length -gt 16777216){throw 'Archive changed beyond bounds'}
        return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($stream)).ToLowerInvariant()
    }finally{$stream.Dispose()}
}

function New-Sl3ArchiveTransaction([string]$Target,[string]$OriginalSha256,[string]$CandidateSha256) {
    if($OriginalSha256 -cnotmatch '^[0-9a-f]{64}$' -or $CandidateSha256 -cnotmatch '^[0-9a-f]{64}$' -or $OriginalSha256 -ceq $CandidateSha256){throw 'Distinct lowercase SHA256 identities required'}
    $full=[IO.Path]::GetFullPath($Target)
    if([IO.Path]::GetFileName($full) -cne 'userio_resources.bin'){throw 'Exact resource filename required'}
    $null=Get-Sl3ArchiveHash $full
    $prefix=$full+'.sl3-'+$CandidateSha256.Substring(0,16)
    return [pscustomobject]@{Target=$full;OriginalSha256=$OriginalSha256;CandidateSha256=$CandidateSha256;
        Stage=$prefix+'.pending';Backup=$prefix+'.original';Retired=$prefix+'.retired'}
}

function Get-Sl3ArchiveTransactionState($Transaction) {
    # Reconstruct derived paths rather than trusting caller-edited witness names.
    $t=New-Sl3ArchiveTransaction $Transaction.Target $Transaction.OriginalSha256 $Transaction.CandidateSha256
    foreach($key in @('Stage','Backup','Retired')){if($Transaction.$key -cne $t.$key){throw 'Transaction path identity differs'}}
    $hashes=[ordered]@{}
    foreach($key in @('Target','Stage','Backup','Retired')){
        if(Test-Path -LiteralPath $t.$key){$hashes[$key]=Get-Sl3ArchiveHash $t.$key}else{$hashes[$key]=$null}
    }
    $state='conflict'
    if($hashes.Target -ceq $t.OriginalSha256){
        if($null -eq $hashes.Backup -and $null -eq $hashes.Retired){
            if($null -eq $hashes.Stage){$state='original'}
            elseif($hashes.Stage -ceq $t.CandidateSha256){$state='install-staged'}
        }elseif(($null -eq $hashes.Backup -or $hashes.Backup -ceq $t.OriginalSha256) -and
                 ($null -eq $hashes.Retired -or $hashes.Retired -ceq $t.CandidateSha256) -and $null -eq $hashes.Stage){$state='restored'}
    }elseif($hashes.Target -ceq $t.CandidateSha256 -and $hashes.Backup -ceq $t.OriginalSha256 -and $null -eq $hashes.Retired){
        if($null -eq $hashes.Stage){$state='installed'}
        elseif($hashes.Stage -ceq $t.OriginalSha256){$state='rollback-staged'}
    }
    return [pscustomobject]@{schema='sl3.archive-file-state.v1';state=$state;hashes=$hashes;
        applicationAcceptanceVerified=$false;deviceAccess=$false;audioPlayed=$false}
}

function Write-Sl3ArchiveStage([string]$Source,[string]$Destination,[string]$Expected) {
    if((Get-Sl3ArchiveHash $Source) -cne $Expected){throw 'Stage source identity differs'}
    $sourceStream=[IO.File]::Open($Source,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    try{
        $destinationStream=[IO.File]::Open($Destination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try{$sourceStream.CopyTo($destinationStream);$destinationStream.Flush($true)}finally{$destinationStream.Dispose()}
    }finally{$sourceStream.Dispose()}
    if((Get-Sl3ArchiveHash $Destination) -cne $Expected){throw 'Staged bytes differ; preserve for review'}
}

function Install-Sl3ArchiveFile {
    param([Parameter(Mandatory)]$Transaction,[Parameter(Mandatory)][string]$Source,
          [Parameter(Mandatory)][scriptblock]$AssertQuiescent)
    $t=$Transaction
    $state=Get-Sl3ArchiveTransactionState $t
    if($state.state -notin @('original','install-staged')){throw 'Original or verified install-staged state required'}
    if((Get-Sl3ArchiveHash $Source) -cne $t.CandidateSha256){throw 'Candidate source differs'}
    if([IO.Path]::GetFullPath($Source) -in @($t.Target,$t.Stage,$t.Backup,$t.Retired)){throw 'Independent candidate source required'}
    & $AssertQuiescent
    if($state.state -eq 'original'){Write-Sl3ArchiveStage $Source $t.Stage $t.CandidateSha256}
    # The second guard covers an application launch while copying the stage.
    & $AssertQuiescent
    if((Get-Sl3ArchiveTransactionState $t).state -ne 'install-staged'){throw 'Install state changed before replacement'}
    # Windows ReplaceFile preserves/merges destination metadata and atomically
    # creates the original backup. Do not ignore metadata errors or overwrite it.
    [IO.File]::Replace($t.Stage,$t.Target,$t.Backup,$false)
    $result=Get-Sl3ArchiveTransactionState $t
    if($result.state -ne 'installed'){throw 'Post-install identity differs; preserve every witness'}
    return $result
}

function Restore-Sl3ArchiveFile {
    param([Parameter(Mandatory)]$Transaction,[Parameter(Mandatory)][scriptblock]$AssertQuiescent)
    $t=$Transaction;$state=Get-Sl3ArchiveTransactionState $t
    if($state.state -notin @('installed','rollback-staged')){throw 'Verified installed state and original backup required'}
    & $AssertQuiescent
    if($state.state -eq 'installed'){Write-Sl3ArchiveStage $t.Backup $t.Stage $t.OriginalSha256}
    & $AssertQuiescent
    if((Get-Sl3ArchiveTransactionState $t).state -ne 'rollback-staged'){throw 'Rollback state changed before replacement'}
    [IO.File]::Replace($t.Stage,$t.Target,$t.Retired,$false)
    $result=Get-Sl3ArchiveTransactionState $t
    if($result.state -ne 'restored'){throw 'Post-rollback identity differs; preserve every witness'}
    return $result
}

function Clear-Sl3ArchiveWitnesses {
    param([Parameter(Mandatory)]$Transaction,[Parameter(Mandatory)][scriptblock]$AssertQuiescent)
    $t=$Transaction;$state=Get-Sl3ArchiveTransactionState $t
    if($state.state -notin @('original','restored','install-staged')){throw 'Verified original live archive required for witness cleanup'}
    & $AssertQuiescent
    foreach($key in @('Stage','Backup','Retired')){
        $state=Get-Sl3ArchiveTransactionState $t
        if($state.state -notin @('original','restored','install-staged')){throw 'Cleanup state changed'}
        if(Test-Path -LiteralPath $t.$key){
            # State validation bound this exact derived file and all live bytes.
            [IO.File]::Delete($t.$key)
        }
    }
    $result=Get-Sl3ArchiveTransactionState $t
    if($result.state -ne 'original'){throw 'Cleanup did not return to original state'}
    return $result
}
