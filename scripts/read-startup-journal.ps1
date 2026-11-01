#requires -Version 7.5
param([Parameter(Mandatory)][string]$Path)
# Snapshot only: permit the isolated writer to remain open. Hash these exact
# bytes rather than asking Get-FileHash to reopen with incompatible sharing.
$ErrorActionPreference='Stop'
$stream=[IO.File]::Open([IO.Path]::GetFullPath($Path),[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
try{
    $length=$stream.Length
    if($length -gt 64KB){throw 'Oversized startup journal'}
    $snapshot=[byte[]]::new([int]$length)
    $stream.ReadExactly($snapshot,0,$snapshot.Length)
}finally{$stream.Dispose()}
$text=[Text.Encoding]::ASCII.GetString($snapshot)
$terminated=($text.Length -eq 0 -or $text.EndsWith("`n"))
$lines=@($text -split "`n")
# The last split item is empty for a complete record, otherwise an incomplete
# suffix. Never promote that suffix into a complete observed operation marker.
$completeLines=@($lines|Select-Object -SkipLast 1)
foreach($line in $completeLines){
    if($line -notmatch '^\d+\t\d+\t([a-z_]+|redirect_owner\.acquire)\.(enter|return)$'){throw 'Malformed startup journal record'}
}
[ordered]@{name=[IO.Path]::GetFileName($Path);snapshotBytes=$snapshot.Length
    snapshotSha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($snapshot))
    completeRecords=$completeLines.Count;endsWithCompleteRecord=$terminated
    lastCompleteMarker=if($completeLines.Count){$completeLines[-1]}else{$null}
    scope='Exact observed prefix only; a live writer may append later records'}|ConvertTo-Json -Depth 4
