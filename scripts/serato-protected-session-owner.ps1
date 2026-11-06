# Library only. The session wrapper supplies protected paths and quiescence.
Set-StrictMode -Version Latest
function Assert-Sl3SessionOwnerPath([string]$Path,[scriptblock]$AssertProtectedPath) {
    $full=[IO.Path]::GetFullPath($Path)
    if ($full.StartsWith('\\') -or $full.Substring(2).Contains(':') -or
        [IO.Path]::GetFileName($full) -cne '8c7758f23375cee18a9cf3be4a3acc15.bin.sl3-session') { throw 'Exact local session-owner path required' }
    $parent=Split-Path $full
    & $AssertProtectedPath $parent
    $walk=Get-Item -LiteralPath $parent -Force -ErrorAction Stop
    while($null -ne $walk) {
        if($walk.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Reparse session-owner path refused'}
        $walk=$walk.Parent
    }
    if(Test-Path -LiteralPath $full) {
        $item=Get-Item -LiteralPath $full -Force -ErrorAction Stop
        if($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Regular session-owner file required'}
        & $AssertProtectedPath $full
    }
    return $full
}
function Get-Sl3ProtectedSessionOwner {
    param([Parameter(Mandatory)][string]$Path,[Parameter(Mandatory)][scriptblock]$AssertProtectedPath)
    $full=Assert-Sl3SessionOwnerPath $Path $AssertProtectedPath
    if(-not(Test-Path -LiteralPath $full)){return [pscustomobject]@{present=$false;record=$null;sha256=$null}}
    $stream=[IO.File]::Open($full,'Open','Read','ReadWrite')
    try {
        if($stream.Length -le 0 -or $stream.Length -gt 4096){throw 'Bounded session-owner record required'}
        $raw=[byte[]]::new([int]$stream.Length);$stream.ReadExactly($raw,0,$raw.Length)
    } finally {$stream.Dispose()}
    $record=[Text.UTF8Encoding]::new($false,$true).GetString($raw) | ConvertFrom-Json -AsHashtable
    if($record -isnot [Collections.IDictionary] -or $record.Count -ne 4 -or
       $record.schema -cne 'sl3.protected-session-owner.v1' -or
       $record.capsuleSha256 -isnot [string] -or $record.capsuleSha256 -cnotmatch '^[0-9a-f]{64}$' -or
       $record.bundleSha256 -isnot [string] -or $record.bundleSha256 -cnotmatch '^[0-9a-f]{64}$' -or
       $record.stage -isnot [Collections.IDictionary] -or $record.stage.Count -ne 2 -or
       ($record.stage.pid -isnot [int] -and $record.stage.pid -isnot [long]) -or
       $record.stage.pid -le 0 -or $record.stage.pid -gt [int]::MaxValue -or
       $record.stage.created -isnot [string] -or $record.stage.created -cnotmatch '^[1-9][0-9]{0,19}$' -or
       [uint64]$record.stage.created -eq 0){throw 'Session-owner record identity differs'}
    $digest=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($raw)).ToLowerInvariant()
    return [pscustomobject]@{present=$true;record=$record;sha256=$digest}
}
function Assert-Sl3ProtectedSessionScope($Owner,[string]$CapsuleSha256,[string]$BundleSha256) {
    if(-not $Owner.present -or $Owner.record.capsuleSha256 -cne $CapsuleSha256 -or
        $Owner.record.bundleSha256 -cne $BundleSha256){throw 'Protected staging belongs to another or unknown session'}
}
function Test-Sl3ProtectedStageAlive($Owner) {
    $queryErrors=@()
    $process=Get-Process -Id $Owner.record.stage.pid -ErrorAction SilentlyContinue -ErrorVariable queryErrors
    if($queryErrors | Where-Object {$_.FullyQualifiedErrorId -notlike 'NoProcessFoundForGivenId*'}){throw 'Protected stage identity query failed'}
    if(-not $process){return $false}
    try {
        $null=$process.Handle
        return (-not $process.HasExited -and
            $process.StartTime.ToUniversalTime().ToFileTimeUtc().ToString([Globalization.CultureInfo]::InvariantCulture) -ceq $Owner.record.stage.created)
    } finally {$process.Dispose()}
}
function New-Sl3ProtectedSessionOwner {
    param([Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{64}$')][string]$CapsuleSha256,
        [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{64}$')][string]$BundleSha256,
        [Parameter(Mandatory)][scriptblock]$AssertQuiescent,
        [Parameter(Mandatory)][scriptblock]$AssertProtectedPath)
    & $AssertQuiescent
    $full=Assert-Sl3SessionOwnerPath $Path $AssertProtectedPath
    $record=[ordered]@{schema='sl3.protected-session-owner.v1';capsuleSha256=$CapsuleSha256;bundleSha256=$BundleSha256;
        stage=@{pid=$PID;created=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToFileTimeUtc().ToString([Globalization.CultureInfo]::InvariantCulture)}}
    $raw=[Text.UTF8Encoding]::new($false).GetBytes(($record | ConvertTo-Json -Depth 4 -Compress))
    $writer=[IO.File]::Open($full,'CreateNew','Write','Read')
    try {$writer.Write($raw,0,$raw.Length);$writer.Flush($true)}finally{$writer.Dispose()}
    # Retain read access without write/delete sharing for the entire stage.
    $lease=[IO.File]::Open($full,'Open','Read','Read')
    try {
        $owner=Get-Sl3ProtectedSessionOwner $full $AssertProtectedPath
        Assert-Sl3ProtectedSessionScope $owner $CapsuleSha256 $BundleSha256
        return [pscustomobject]@{path=$full;owner=$owner;lease=$lease}
    } catch {$lease.Dispose();throw}
}
function Remove-Sl3ProtectedSessionOwner {
    param([Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$CapsuleSha256,[Parameter(Mandatory)][string]$BundleSha256,
        [Parameter(Mandatory)][scriptblock]$AssertQuiescent,[Parameter(Mandatory)][scriptblock]$AssertProtectedPath,
        $OwnedLease=$null)
    try {
        & $AssertQuiescent
        $owner=Get-Sl3ProtectedSessionOwner $Path $AssertProtectedPath
        Assert-Sl3ProtectedSessionScope $owner $CapsuleSha256 $BundleSha256
        if($null -ne $OwnedLease) {
            if($OwnedLease.owner.sha256 -cne $owner.sha256 -or $owner.record.stage.pid -ne $PID -or
                $owner.record.stage.created -cne (Get-Process -Id $PID).StartTime.ToUniversalTime().ToFileTimeUtc().ToString([Globalization.CultureInfo]::InvariantCulture)) {
                throw 'Only the exact creating stage may release its live lease'
            }
        } elseif(Test-Sl3ProtectedStageAlive $owner){throw 'Protected stage remains active'}
    } finally {if($null -ne $OwnedLease){$OwnedLease.lease.Dispose()}}
    & $AssertQuiescent
    $again=Get-Sl3ProtectedSessionOwner $Path $AssertProtectedPath
    if($again.sha256 -cne $owner.sha256){throw 'Protected session ownership changed; preserve it'}
    [IO.File]::Delete([IO.Path]::GetFullPath($Path))
    if(Test-Path -LiteralPath $Path){throw 'Protected session ownership was not removed'}
}
