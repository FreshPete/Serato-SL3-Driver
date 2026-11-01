<# Read installed Image/EventVersion and Image_Load WMI metadata only. #>
[CmdletBinding()]
param([Parameter(Mandatory)][string]$Output)
$ErrorActionPreference='Stop'
$Output=[IO.Path]::GetFullPath($Output)
if ((Test-Path -LiteralPath $Output) -or -not (Test-Path -LiteralPath ([IO.Path]::GetDirectoryName($Output)) -PathType Container)) {
    throw 'Expected a new output in an existing directory.'
}
$base=Get-CimClass -Namespace root/wmi -ClassName Image
$payload=Get-CimClass -Namespace root/wmi -ClassName Image_Load
$result=[ordered]@{
    scope='Read-only installed Microsoft WMI image schema; no source/session/device or privilege operation'
    observedUtc=[datetime]::UtcNow.ToString('o')
    baseClass=$base.CimClassName
    superClass=$base.CimSuperClassName
    baseQualifiers=@($base.CimClassQualifiers | ForEach-Object {[ordered]@{name=$_.Name;value=$_.Value}})
    payloadClass=$payload.CimClassName
    payloadSuperClass=$payload.CimSuperClassName
    payloadQualifiers=@($payload.CimClassQualifiers | ForEach-Object {[ordered]@{name=$_.Name;value=$_.Value}})
    properties=@($payload.CimClassProperties | ForEach-Object {
        [ordered]@{name=$_.Name;cimType=$_.CimType.ToString();qualifiers=@($_.Qualifiers | ForEach-Object {[ordered]@{name=$_.Name;value=$_.Value}})}
    })
    sourceSha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
}
$stream=[IO.File]::Open($Output,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try { $bytes=[Text.UTF8Encoding]::new($false).GetBytes(($result | ConvertTo-Json -Depth 9)+[Environment]::NewLine);$stream.Write($bytes,0,$bytes.Length) }
finally { $stream.Dispose() }
[ordered]@{base=$base.CimClassName;eventVersion=($base.CimClassQualifiers | Where-Object Name -eq EventVersion).Value;
    payload=$payload.CimClassName;propertyCount=$payload.CimClassProperties.Count;sourceOrDeviceOperation=$false} | ConvertTo-Json
