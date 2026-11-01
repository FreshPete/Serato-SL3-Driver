param([string]$Output = 'artifacts/build/sl3winusb')
# Generates an unsigned catalogue; never signs, installs, or changes trust.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not [IO.Path]::IsPathRooted($Output)) { $Output = Join-Path $root $Output }
$package = Join-Path $root 'artifacts/downloads/microsoft.windows.wdk.x64.10.0.28000.2526.nupkg'
if ((Get-FileHash -LiteralPath $package).Hash -ne '63c939fb5a79295bf40e941db592681272219b04edff095fe2f3d123e5579a90') {
    throw 'Expected pinned Microsoft WDK NuGet package; see analysis-workflow.md.'
}
$tool = Join-Path $root 'tools/wdk-10.0.28000.2526/c/bin/10.0.28000.0/x86/Inf2Cat.exe'
if (-not (Test-Path -LiteralPath $tool)) { throw 'Extract the pinned WDK NuGet package first.' }
if ((Get-FileHash -LiteralPath $tool).Hash -ne '82c302fc9069783674b51665ce80e769f8500db7fc737a4b8a3773c521950b86') {
    throw 'Inf2Cat executable does not match the pinned package extraction.'
}
New-Item -ItemType Directory -Force -Path $Output | Out-Null
$inf = Join-Path $Output 'sl3winusb.inf'
$cat = Join-Path $Output 'sl3winusb.cat'
Copy-Item -LiteralPath (Join-Path $root 'src/windows/sl3winusb.inf') -Destination $inf -Force
& $tool "/driver:$Output" /os:10_GE_X64 /verbose 2>&1 | Tee-Object -FilePath (Join-Path $Output 'inf2cat.log')
$result = $LASTEXITCODE
if ($result -ne 0) { throw "Inf2Cat failed with exit code $result; see inf2cat.log." }
if (-not (Test-Path -LiteralPath $cat)) { throw 'Inf2Cat did not produce the expected catalogue.' }
$signature = Get-AuthenticodeSignature -LiteralPath $cat
if ($signature.Status -ne 'NotSigned') { throw 'Expected an unsigned development catalogue; inspect its provenance.' }
[ordered]@{
    utc=[DateTime]::UtcNow.ToString('o')
    infSha256=(Get-FileHash -LiteralPath $inf).Hash.ToLowerInvariant()
    catSha256=(Get-FileHash -LiteralPath $cat).Hash.ToLowerInvariant()
    inf2catSha256=(Get-FileHash -LiteralPath $tool).Hash.ToLowerInvariant()
    target='10_GE_X64'
    exitCode=$result
    catalogueSignature=$signature.Status.ToString()
    interpretation='Inf2Cat signability/catalogue generation passed. Not signed, WHCP certified, installed or hardware validated.'
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Output 'build-result.json') -Encoding utf8
Get-Content -LiteralPath (Join-Path $Output 'build-result.json')
