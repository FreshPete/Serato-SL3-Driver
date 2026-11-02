#requires -Version 7.5
param([ValidateSet('Release','Debug')][string]$Configuration='Release')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$build=Join-Path $root 'artifacts/build/asio-private-trace'
& cmake -S (Join-Path $root 'diagnostics/asio-trace') -B $build -G 'Visual Studio 16 2019' -A x64 '-DCMAKE_SYSTEM_VERSION=10.0.19041.0'
if($LASTEXITCODE -ne 0){throw 'Private trace configuration failed'}
& cmake --build $build --config $Configuration
if($LASTEXITCODE -ne 0){throw 'Private trace build failed'}
& ctest --test-dir $build -C $Configuration --output-on-failure
if($LASTEXITCODE -ne 0){throw 'Private trace plan/refusal checks failed'}
$files=@('diagnostics/asio-trace/CMakeLists.txt','diagnostics/asio-trace/private_capture.cpp','src/asio/call_trace.hpp','src/asio/com_identity.hpp','scripts/build-asio-private-trace.ps1',
    'artifacts/references/asio-sdk-2.3.4/ASIOSDK/common/asio.h','artifacts/references/asio-sdk-2.3.4/ASIOSDK/common/asiosys.h','artifacts/references/asio-sdk-2.3.4/ASIOSDK/common/iasiodrv.h')
$inputs=[ordered]@{};foreach($path in $files){$inputs[$path]=(Get-FileHash -LiteralPath (Join-Path $root $path)).Hash.ToLowerInvariant()}
$record=[ordered]@{schema='sl3.asio-private-trace-build.v1';configuration=$Configuration;inputs=$inputs;
    executableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_asio_private_trace.exe")).Hash.ToLowerInvariant();
    planAndRefusalTestsPassed=$true;captureExecutedByBuild=$false;deviceAccess=$false;seratoExecuted=$false}
$record|ConvertTo-Json -Depth 5|Out-File -LiteralPath (Join-Path $build "diagnostic-build-$Configuration.json") -Encoding utf8
