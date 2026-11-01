param([switch]$Prepare)
# Creates a short-lived, untrusted development identity and signs only our INF
# catalogue. Does not import a trust anchor, install a driver or change boot policy.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root 'artifacts/build/sl3winusb'
$stage = Join-Path $root 'artifacts/build/sl3winusb-development'
$manifest = Join-Path $stage 'development-package.json'
if (-not $Prepare) {
    [ordered]@{source=$source;destination=$stage;certificateStore='CurrentUser/My (not a trust store)';validDays=7;trustChanges='None';driverInstallation=$false} | ConvertTo-Json
    exit
}
if (Test-Path -LiteralPath $manifest) {
    $record = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
    foreach ($file in @('sl3winusb.inf','sl3winusb.cat','sl3-winusb-development.cer')) {
        if ((Get-FileHash -LiteralPath (Join-Path $stage $file)).Hash -ne $record.files.$file) { throw "Prepared file changed: $file" }
    }
    $record | ConvertTo-Json -Depth 5
    exit
}
if (Test-Path -LiteralPath $stage) { throw 'Development staging directory already exists without a manifest; inspect it before retrying.' }
$build = Get-Content -LiteralPath (Join-Path $source 'build-result.json') -Raw | ConvertFrom-Json
if ((Get-FileHash -LiteralPath (Join-Path $source 'sl3winusb.inf')).Hash -ne $build.infSha256 -or
    (Get-FileHash -LiteralPath (Join-Path $source 'sl3winusb.cat')).Hash -ne $build.catSha256) { throw 'Unsigned package does not match its build record.' }
if ((Get-AuthenticodeSignature -LiteralPath (Join-Path $source 'sl3winusb.cat')).Status -ne 'NotSigned') { throw 'Expected our unsigned catalogue.' }
New-Item -ItemType Directory -Path $stage | Out-Null
Copy-Item -LiteralPath (Join-Path $source 'sl3winusb.inf'),(Join-Path $source 'sl3winusb.cat') -Destination $stage
$cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject 'CN=SL3 WinUSB Local Development Only' `
    -FriendlyName 'Serato-SL3 WinUSB development only (7 days)' -CertStoreLocation 'Cert:\CurrentUser\My' `
    -KeyAlgorithm RSA -KeyLength 3072 -HashAlgorithm SHA256 -KeyUsage DigitalSignature `
    -KeyExportPolicy NonExportable -NotBefore (Get-Date).AddMinutes(-5) -NotAfter (Get-Date).AddDays(7)
$public = Join-Path $stage 'sl3-winusb-development.cer'
Export-Certificate -Cert $cert -FilePath $public | Out-Null
# Persist the identity immediately so a failed signing operation is recoverable.
[ordered]@{thumbprint=$cert.Thumbprint;subject=$cert.Subject;notAfterUtc=$cert.NotAfter.ToUniversalTime().ToString('o');trusted=$false} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stage 'certificate-created.json') -Encoding utf8
$signTool = 'C:\Program Files (x86)\Windows Kits\10\bin\10.0.19041.0\x64\signtool.exe'
& $signTool sign /fd SHA256 /sha1 $cert.Thumbprint /s My /v (Join-Path $stage 'sl3winusb.cat') 2>&1 |
    Tee-Object -FilePath (Join-Path $stage 'signing.log')
if ($LASTEXITCODE -ne 0) { throw 'Development catalogue signing failed; see signing.log and certificate-created.json.' }
$signature = Get-AuthenticodeSignature -LiteralPath (Join-Path $stage 'sl3winusb.cat')
if ($signature.SignerCertificate.Thumbprint -ne $cert.Thumbprint) { throw 'Unexpected catalogue signer.' }
$trustPresence = foreach($store in @('Cert:\LocalMachine\Root','Cert:\LocalMachine\TrustedPublisher','Cert:\CurrentUser\Root','Cert:\CurrentUser\TrustedPublisher')) {
    [ordered]@{store=$store;containsCertificate=(Test-Path -LiteralPath "$store\$($cert.Thumbprint)")}
}
if (@($trustPresence | Where-Object containsCertificate).Count) { throw 'Development certificate unexpectedly present in a trust store.' }
$files = [ordered]@{}
foreach($file in @('sl3winusb.inf','sl3winusb.cat','sl3-winusb-development.cer')) {
    $files[$file] = (Get-FileHash -LiteralPath (Join-Path $stage $file)).Hash.ToLowerInvariant()
}
[ordered]@{
    preparedUtc=[DateTime]::UtcNow.ToString('o');subject=$cert.Subject;thumbprint=$cert.Thumbprint
    certificateSha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($cert.RawData)).ToLowerInvariant()
    notBeforeUtc=$cert.NotBefore.ToUniversalTime().ToString('o');notAfterUtc=$cert.NotAfter.ToUniversalTime().ToString('o')
    privateKey='Non-exportable; CurrentUser/My only';enhancedKeyUsage=@($cert.EnhancedKeyUsageList.ObjectId)
    catalogueStatusBeforeTrust=$signature.Status.ToString();trustStores=$trustPresence;files=$files
    scope='Development INF/catalogue only; no replacement SYS, firmware, boot-policy change, trust import or driver installation.'
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifest -Encoding utf8
Get-Content -LiteralPath $manifest
