#requires -Version 7.5
param([ValidateSet('Release','Debug')][string]$Configuration='Release')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$build=Join-Path $root 'artifacts/build/asio-trace-decoder'
& cmake -S (Join-Path $root 'diagnostics/asio-decode') -B $build -G 'Visual Studio 16 2019' -A x64 '-DCMAKE_SYSTEM_VERSION=10.0.19041.0'
if($LASTEXITCODE -ne 0){throw 'Decoder configure failed'}
& cmake --build $build --config $Configuration
if($LASTEXITCODE -ne 0){throw 'Decoder build failed'}
& ctest --test-dir $build -C $Configuration --output-on-failure
if($LASTEXITCODE -ne 0){throw 'Decoder plan/refusal checks failed'}
$inputs=[ordered]@{}
foreach($path in @('diagnostics/asio-decode/CMakeLists.txt','diagnostics/asio-decode/decode.cpp','src/asio/call_trace.hpp','scripts/build-asio-trace-decoder.ps1')){
    $inputs[$path]=(Get-FileHash -LiteralPath (Join-Path $root $path)).Hash.ToLowerInvariant()
}
$record=[ordered]@{schema='sl3.asio-etl-decoder-build.v1';configuration=$Configuration;inputs=$inputs;
    executableSha256=(Get-FileHash -LiteralPath (Join-Path $build "$Configuration/sl3_asio_decode_trace.exe")).Hash.ToLowerInvariant();
    planAndRefusalTestsPassed=$true;traceControllerStarted=$false;deviceAccess=$false;seratoExecuted=$false}
$record|ConvertTo-Json -Depth 5|Out-File -LiteralPath (Join-Path $build "decoder-build-$Configuration.json") -Encoding utf8
