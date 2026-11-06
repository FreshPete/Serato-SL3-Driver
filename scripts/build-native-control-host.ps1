#requires -Version 7.5
param()
$ErrorActionPreference='Stop'
$diagnosticRoot=Split-Path -Parent $PSScriptRoot
$diagnosticBuild=Join-Path $diagnosticRoot 'artifacts/build/native-control-host-20261106'
& cmake -S (Join-Path $diagnosticRoot 'diagnostics/asio-native-control') -B $diagnosticBuild -G 'Visual Studio 16 2019' -A x64 '-DCMAKE_GENERATOR_INSTANCE=C:/Program Files (x86)/Microsoft Visual Studio/2019/BuildTools' '-DCMAKE_SYSTEM_VERSION=10.0.19041.0'
if($LASTEXITCODE -ne 0){throw 'Diagnostic configuration failed'}
& cmake --build $diagnosticBuild --config Release
if($LASTEXITCODE -ne 0){throw 'Diagnostic build failed'}
& ctest --test-dir $diagnosticBuild -C Release --output-on-failure
if($LASTEXITCODE -ne 0){throw 'Diagnostic plan/refusal checks failed'}
$diagnosticSources=@('diagnostics/asio-native-control/CMakeLists.txt','diagnostics/asio-native-control/host.cpp','src/asio/com_identity.hpp','scripts/build-native-control-host.ps1',
 'artifacts/references/asio-sdk-2.3.4/ASIOSDK/common/asio.h','artifacts/references/asio-sdk-2.3.4/ASIOSDK/common/asiosys.h','artifacts/references/asio-sdk-2.3.4/ASIOSDK/common/iasiodrv.h')
$diagnosticPins=[ordered]@{};foreach($diagnosticSource in $diagnosticSources){$diagnosticPins[$diagnosticSource]=(Get-FileHash -LiteralPath (Join-Path $diagnosticRoot $diagnosticSource)).Hash.ToLowerInvariant()}
[ordered]@{schema='sl3.native-control-host-build.v1';configuration='Release';inputs=$diagnosticPins;
 executableSha256=(Get-FileHash -LiteralPath (Join-Path $diagnosticBuild 'Release/sl3_native_control_host.exe')).Hash.ToLowerInvariant();
 planAndRefusalTestsPassed=$true;deviceAccessDuringBuild=$false}|ConvertTo-Json -Depth 5|Out-File -LiteralPath (Join-Path $diagnosticBuild 'diagnostic-build.json') -Encoding utf8
