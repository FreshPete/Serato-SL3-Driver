#requires -Version 7.5
param([Parameter(Mandatory)][string]$BuildDirectory,[Parameter(Mandatory)][string]$ExpectedSourceManifestSha256)
$ErrorActionPreference='Stop'
$entryRoot=Split-Path -Parent $PSScriptRoot
$entryDirectory=[IO.Path]::GetFullPath($BuildDirectory)
$entryManifest=Join-Path $entryDirectory 'entry-source.json'
if((Get-FileHash -LiteralPath $entryManifest).Hash.ToLowerInvariant() -ne $ExpectedSourceManifestSha256){throw 'Reviewed native entry source manifest required'}
$entrySource=Get-Content -LiteralPath $entryManifest -Raw|ConvertFrom-Json
foreach($entryPin in $entrySource.sourcePins.PSObject.Properties){if((Get-FileHash -LiteralPath (Join-Path $entryRoot $entryPin.Name)).Hash.ToLowerInvariant() -ne $entryPin.Value){throw 'Native entry source changed'}}
foreach($entryPin in $entrySource.generatedPins.PSObject.Properties){if((Get-FileHash -LiteralPath (Join-Path $entryDirectory $entryPin.Name)).Hash.ToLowerInvariant() -ne $entryPin.Value){throw 'Generated native entry source changed'}}
& cmake -S $entryDirectory -B (Join-Path $entryDirectory 'build') -G 'Visual Studio 16 2019' -A x64 '-DCMAKE_GENERATOR_INSTANCE=C:/Program Files (x86)/Microsoft Visual Studio/2019/BuildTools' '-DCMAKE_SYSTEM_VERSION=10.0.19041.0'
if($LASTEXITCODE -ne 0){throw 'Setup entry configuration failed'}
& cmake --build (Join-Path $entryDirectory 'build') --config Release
if($LASTEXITCODE -ne 0){throw 'Setup entry build failed'}
& ctest --test-dir (Join-Path $entryDirectory 'build') -C Release --output-on-failure
if($LASTEXITCODE -ne 0){throw 'Setup entry inert checks failed'}
[ordered]@{schema='sl3.native-setup-entry-build.v1';configuration='Release';sourceManifestSha256=$ExpectedSourceManifestSha256;
 executableSha256=(Get-FileHash -LiteralPath (Join-Path $entryDirectory 'build/Release/SL3_Setup_Engineering.exe')).Hash.ToLowerInvariant();
 inertChecksPassed=$true;productionSetupExecuted=$false;seratoLaunched=$false;nativeDeviceAccess=$false}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $entryDirectory 'entry-build.json') -Encoding utf8
