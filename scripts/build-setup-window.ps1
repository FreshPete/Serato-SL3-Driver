#requires -Version 7.5
param([Parameter(Mandatory)][string]$BuildDirectory,[Parameter(Mandatory)][string]$ExpectedSourceManifestSha256)
$ErrorActionPreference='Stop'
$windowRoot=Split-Path -Parent $PSScriptRoot
$windowDirectory=[IO.Path]::GetFullPath($BuildDirectory)
$windowManifest=Join-Path $windowDirectory 'window-source.json'
if((Get-FileHash -LiteralPath $windowManifest).Hash.ToLowerInvariant() -ne $ExpectedSourceManifestSha256){throw 'Reviewed window source manifest required'}
$windowSource=Get-Content -LiteralPath $windowManifest -Raw|ConvertFrom-Json
foreach($windowPin in $windowSource.sourcePins.PSObject.Properties){if((Get-FileHash -LiteralPath (Join-Path $windowRoot $windowPin.Name)).Hash.ToLowerInvariant() -ne $windowPin.Value){throw 'Window source changed'}}
foreach($windowPin in $windowSource.generatedPins.PSObject.Properties){if((Get-FileHash -LiteralPath (Join-Path $windowDirectory $windowPin.Name)).Hash.ToLowerInvariant() -ne $windowPin.Value){throw 'Generated window source changed'}}
& cmake -S $windowDirectory -B (Join-Path $windowDirectory 'build') -G 'Visual Studio 16 2019' -A x64 '-DCMAKE_GENERATOR_INSTANCE=C:/Program Files (x86)/Microsoft Visual Studio/2019/BuildTools' '-DCMAKE_SYSTEM_VERSION=10.0.19041.0'
if($LASTEXITCODE -ne 0){throw 'Window configuration failed'}
& cmake --build (Join-Path $windowDirectory 'build') --config Release
if($LASTEXITCODE -ne 0){throw 'Window build failed'}
if($windowSource.portableLayout){
    $release=Join-Path $windowDirectory 'build/Release'
    $kit=Join-Path $release 'kit'
    $entry=Join-Path $release 'SL3_Setup_Engineering.exe'
    if((Get-FileHash -LiteralPath $windowSource.portableLayout.entry).Hash.ToLowerInvariant() -ne $windowSource.nativeEntrySha256 -or
       (Get-FileHash -LiteralPath (Join-Path $windowSource.portableLayout.kit 'kit-manifest.json')).Hash.ToLowerInvariant() -ne $windowSource.kitManifestSha256){throw 'Portable setup inputs differ'}
    if(-not (Test-Path -LiteralPath $entry)){Copy-Item -LiteralPath $windowSource.portableLayout.entry -Destination $entry}
    if(-not (Test-Path -LiteralPath $kit)){
        New-Item -ItemType Directory -Path $kit | Out-Null
        Get-ChildItem -LiteralPath $windowSource.portableLayout.kit -Force | Where-Object Name -CNE 'analysis' | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $kit -Recurse
        }
    }
}
& ctest --test-dir (Join-Path $windowDirectory 'build') -C Release --output-on-failure -V
if($LASTEXITCODE -ne 0){throw 'Window contract checks failed'}
[ordered]@{schema='sl3.setup-window-build.v1';configuration='Release';sourceManifestSha256=$ExpectedSourceManifestSha256;
 executableSha256=(Get-FileHash -LiteralPath (Join-Path $windowDirectory 'build/Release/SL3_Compatibility_Setup.exe')).Hash.ToLowerInvariant();
 contractChecksPassed=$true;privilegedActionsExecuted=$false;seratoLaunched=$false;nativeDeviceAccess=$false}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $windowDirectory 'window-build.json') -Encoding utf8
