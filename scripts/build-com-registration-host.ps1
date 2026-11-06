#requires -Version 7.5
param()
$ErrorActionPreference='Stop'
$diagnosticRoot=Split-Path -Parent $PSScriptRoot
$diagnosticBuild=Join-Path $diagnosticRoot 'artifacts/build/com-registration-host-20261106'
& cmake -S (Join-Path $diagnosticRoot 'diagnostics/asio-com-registration') -B $diagnosticBuild -G 'Visual Studio 16 2019' -A x64 '-DCMAKE_GENERATOR_INSTANCE=C:/Program Files (x86)/Microsoft Visual Studio/2019/BuildTools' '-DCMAKE_SYSTEM_VERSION=10.0.19041.0'
if($LASTEXITCODE -ne 0){throw 'Owned host configuration failed'}
& cmake --build $diagnosticBuild --config Release
if($LASTEXITCODE -ne 0){throw 'Owned host build failed'}
& ctest --test-dir $diagnosticBuild -C Release --output-on-failure
if($LASTEXITCODE -ne 0){throw 'Owned host plan/refusal checks failed'}
$diagnosticSources=@('diagnostics/asio-com-registration/CMakeLists.txt','diagnostics/asio-com-registration/host.cpp','src/asio/com_identity.hpp','scripts/build-com-registration-host.ps1',
 'artifacts/references/asio-sdk-2.3.4/ASIOSDK/common/asio.h','artifacts/references/asio-sdk-2.3.4/ASIOSDK/common/asiosys.h','artifacts/references/asio-sdk-2.3.4/ASIOSDK/common/iasiodrv.h')
$diagnosticPins=[ordered]@{};foreach($diagnosticSource in $diagnosticSources){$diagnosticPins[$diagnosticSource]=(Get-FileHash -LiteralPath (Join-Path $diagnosticRoot $diagnosticSource)).Hash.ToLowerInvariant()}
[ordered]@{schema='sl3.com-registration-host-build.v1';configuration='Release';inputs=$diagnosticPins;
 executableSha256=(Get-FileHash -LiteralPath (Join-Path $diagnosticBuild 'Release/sl3_com_registration_host.exe')).Hash.ToLowerInvariant();
 planAndRefusalTestsPassed=$true;ownedFixtureExecutedByBuild=$false;seratoExecuted=$false;nativeDeviceAccess=$false}|ConvertTo-Json -Depth 5|Out-File -LiteralPath (Join-Path $diagnosticBuild 'diagnostic-build.json') -Encoding utf8
