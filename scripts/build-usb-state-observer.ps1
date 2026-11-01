param([ValidateSet('Release','Debug')][string]$Configuration='Release')
$ErrorActionPreference='Stop';$root=Split-Path -Parent $PSScriptRoot
$folder=Join-Path $root 'artifacts/build/usb-state-observer'
$python=Join-Path $root '.venv/Scripts/python.exe'
& cmake -S (Join-Path $PSScriptRoot 'native/usb-state-observer') -B $folder -G 'Visual Studio 16 2019' -A x64 '-DCMAKE_SYSTEM_VERSION=10.0.19041.0'
if($LASTEXITCODE -ne 0){throw 'Passive observer configuration failed'}
& cmake --build $folder --config $Configuration
if($LASTEXITCODE -ne 0){throw 'Passive observer build failed'}
$exe=Join-Path $folder "$Configuration/sl3_usb_state_observer.exe"
$testRecord=Join-Path $folder ("test-$Configuration-"+[guid]::NewGuid().ToString('N')+'.json')
& $python (Join-Path $PSScriptRoot 'test-usb-state-observer.py') $exe $testRecord
if($LASTEXITCODE -ne 0){throw 'Actual passive replay verification failed'}
$record=[ordered]@{configuration=$Configuration;executableSha256=(Get-FileHash -LiteralPath $exe).Hash
    testRecord=$testRecord;testRecordSha256=(Get-FileHash -LiteralPath $testRecord).Hash;nativeDeviceOperation=$false
    livePositiveValidated=$false;readinessAdmission=$false;inputs=[ordered]@{}}
foreach($name in @('scripts/native/usb-state-observer/main.cpp','scripts/native/usb-state-observer/CMakeLists.txt',
    'scripts/build-usb-state-observer.ps1','scripts/test-usb-state-observer.py','scripts/export-reopen-usb-timeline.py')){
    $record.inputs[$name]=(Get-FileHash -LiteralPath (Join-Path $root $name)).Hash
}
$record|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $folder "observer-build-$Configuration.json")
