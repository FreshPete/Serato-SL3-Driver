# Project-local REA CLI; does not register or modify the Codex client.
$root = Split-Path -Parent $PSScriptRoot
$env:GHIDRA_INSTALL_DIR = Join-Path $root 'tools/ghidra_12.1.4_PUBLIC'
$env:JAVA_HOME = Join-Path $root 'tools/jdk-21.0.9+10'
$nodeDir = Join-Path $root 'tools/node-v24.22.1-win-x64'
$env:PATH = $nodeDir + ';' + $env:PATH
& (Join-Path $nodeDir 'node.exe') (Join-Path $root 'tools/rea/node_modules/rea-agents/scripts/rea.mjs') @args
exit $LASTEXITCODE
