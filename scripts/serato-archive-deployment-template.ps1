# Generated attended-test wrapper. Default Plan is read-only. No automatic UAC.
# Do not run this template directly; prepare and review its source-bound bundle.
#requires -Version 7.5
param([ValidateSet('Plan','Install','Rollback','Clean')][string]$Action='Plan')
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$target='@@TARGET@@'
$originalSha='@@ORIGINAL_SHA@@'
$candidateSha='@@CANDIDATE_SHA@@'
$exeSha='@@EXE_SHA@@'
$signerThumbprint='@@SIGNER@@'
$coreSha='@@CORE_SHA@@'
$planSha='@@PLAN_SHA@@'
function Read-ReviewedHash([string]$Path){
    $item=Get-Item -LiteralPath $Path -Force
    if($item.PSIsContainer -or $item.Length -le 0 -or $item.Length -gt 16777216){throw 'Bounded package file required'}
    $walk=$item
    while($null -ne $walk){
        if($walk.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Reparse package path refused'}
        if($walk -is [IO.FileInfo]){$walk=$walk.Directory}else{$walk=$walk.Parent}
    }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
$core=Join-Path $PSScriptRoot 'serato-archive-file-transaction.ps1'
$plan=Join-Path $PSScriptRoot 'deployment-plan.json'
if((Read-ReviewedHash $core) -cne $coreSha -or (Read-ReviewedHash $plan) -cne $planSha){throw 'Reviewed package code/plan differs'}
$coreBytes=[IO.File]::ReadAllBytes($core)
if([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($coreBytes)).ToLowerInvariant() -cne $coreSha){throw 'Reviewed core changed before import'}
. ([scriptblock]::Create([Text.Encoding]::UTF8.GetString($coreBytes)))
$source=Join-Path $PSScriptRoot 'candidate-userio_resources.bin'
if($Action -in @('Plan','Install')){
    if((Get-Sl3ArchiveHash $source) -cne $candidateSha){throw 'Reviewed candidate archive differs'}
}
$exe=Join-Path (Split-Path $target) 'Serato DJ Pro.exe'
if((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant() -cne $exeSha){throw 'Original application identity differs'}
$signature=Get-AuthenticodeSignature -LiteralPath $exe
if($signature.Status.ToString() -cne 'Valid' -or $null -eq $signature.SignerCertificate -or $signature.SignerCertificate.Thumbprint -cne $signerThumbprint){throw 'Original executable signature verification failed'}
function Assert-SeratoStopped {
    if(@(Get-Process -Name 'Serato DJ Pro' -ErrorAction SilentlyContinue).Count){throw 'Close Serato DJ Pro before changing its archive'}
    foreach($path in @($target,(Split-Path $target),(Split-Path (Split-Path $target)))){Assert-Sl3ArchiveProtectedPath $path}
    foreach($path in @($t.Stage,$t.Backup,$t.Retired)){if(Test-Path -LiteralPath $path){Assert-Sl3ArchiveProtectedPath $path}}
}
$t=New-Sl3ArchiveTransaction $target $originalSha $candidateSha
$before=Get-Sl3ArchiveTransactionState $t
foreach($path in @($target,(Split-Path $target),(Split-Path (Split-Path $target)))){Assert-Sl3ArchiveProtectedPath $path}
if($Action -ne 'Plan'){
    $identity=[Security.Principal.WindowsIdentity]::GetCurrent()
    try{$principal=[Security.Principal.WindowsPrincipal]::new($identity)
        if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Attended elevated launch required; this wrapper does not request UAC'}
    }finally{$identity.Dispose()}
}
switch($Action){
    'Plan' {$after=$before}
    'Install' {$after=Install-Sl3ArchiveFile $t $source ${function:Assert-SeratoStopped}}
    'Rollback' {$after=Restore-Sl3ArchiveFile $t ${function:Assert-SeratoStopped}}
    'Clean' {$after=Clear-Sl3ArchiveWitnesses $t ${function:Assert-SeratoStopped}}
}
[ordered]@{schema='sl3.archive-deployment-action.v1';action=$Action;before=$before;after=$after;
    originalExecutableSignatureStatus=$signature.Status.ToString();seratoRunning=@(Get-Process -Name 'Serato DJ Pro' -ErrorAction SilentlyContinue).Count -gt 0;
    applicationExecuted=$false;applicationAcceptanceVerified=$false;deviceAccess=$false;audioPlayed=$false;
    authorizationModified=$false;firmwareModified=$false;securityPolicyModified=$false}|ConvertTo-Json -Depth 8
