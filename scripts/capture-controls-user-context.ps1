#requires -Version 7.5
param([switch]$Run,[switch]$WithStateObserver,[ValidateRange(20,60)][int]$TraceSeconds=60,[string]$ContextDirectory='tests/results/local/user-controls-01')
$ErrorActionPreference='Stop';$root=Split-Path -Parent $PSScriptRoot
if($ContextDirectory -match '["\r\n]'){throw 'Invalid context path'}
if(-not [IO.Path]::IsPathRooted($ContextDirectory)){$ContextDirectory=Join-Path $root $ContextDirectory}
$ContextDirectory=[IO.Path]::GetFullPath($ContextDirectory)
if($ContextDirectory.StartsWith('\\')){throw 'Local context directory required'}
if(Test-Path -LiteralPath $ContextDirectory){throw 'Choose a fresh context directory'}
if(-not $Run){[ordered]@{planOnly=$true;deviceAccess=$false;role='administrator trace/state collector';contextDirectory=$ContextDirectory
    traceSeconds=$TraceSeconds;withUsbDkLifecycle=$true;withStateObserver=[bool]$WithStateObserver;launchesProbe=$false;selfElevates=$false;securityChanges=$false}|ConvertTo-Json;return}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
if(-not ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Use an already elevated terminal for trace/state collection'}
New-Item -ItemType Directory -Path $ContextDirectory|Out-Null
$record=[ordered]@{schema='sl3.controls-user.context.v1';startedUtc=[datetime]::UtcNow.ToString('o');completed=$false;error=$null
    administratorToken=$true;producerSha256=(Get-FileHash -LiteralPath $PSCommandPath).Hash;probeLaunched=$false;securityChanges=$false;withStateObserver=[bool]$WithStateObserver;traceSeconds=$TraceSeconds}
function Save-Context{$record|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $ContextDirectory 'context.json')}
Save-Context
try{
    & (Join-Path $PSScriptRoot 'collect-windows-state.ps1') -Output (Join-Path $ContextDirectory 'before-state.json')|Out-Null
    $record.testProcessesBefore=@(Get-CimInstance Win32_Process -Filter "Name='sl3_usbdk.exe' OR Name='sl3_host_probe.exe' OR Name='sl3_scope_probe.exe' OR Name='sl3_broker_scope_probe.exe' OR Name='sl3_broker_controller.exe'"|Select-Object ProcessId,Name)
    if($record.testProcessesBefore.Count){throw 'A prior device-test process remains'}
    $before=Get-Content -LiteralPath (Join-Path $ContextDirectory 'before-state.json') -Raw|ConvertFrom-Json
    if($before.secureBoot -ne $true -or @($before.devices).Count -ne 1){throw 'Enabled Secure Boot and one resting SL3 required'}
    $record.beforeStateSha256=(Get-FileHash -LiteralPath (Join-Path $ContextDirectory 'before-state.json')).Hash;Save-Context
    & (Join-Path $PSScriptRoot 'capture-usb-startup.ps1') -Capture -WithUsbDkLifecycle -WithStateObserver:$WithStateObserver -DurationSeconds $TraceSeconds -OutputDirectory (Join-Path $ContextDirectory 'trace')|Out-Null
    $trace=Get-Content -LiteralPath (Join-Path $ContextDirectory 'trace/capture.json') -Raw|ConvertFrom-Json -DateKind String
    if($trace.status -ne 'window completed'){throw 'Shared USB/WPP capture did not complete'}
    $record.traceRecordSha256=(Get-FileHash -LiteralPath (Join-Path $ContextDirectory 'trace/capture.json')).Hash
}catch{$record.error=$_.Exception.Message}
finally{
    try{
        & (Join-Path $PSScriptRoot 'collect-windows-state.ps1') -Output (Join-Path $ContextDirectory 'after-state.json')|Out-Null
        $record.afterStateSha256=(Get-FileHash -LiteralPath (Join-Path $ContextDirectory 'after-state.json')).Hash
        $record.testProcessesAfter=@(Get-CimInstance Win32_Process -Filter "Name='sl3_usbdk.exe' OR Name='sl3_host_probe.exe' OR Name='sl3_scope_probe.exe' OR Name='sl3_broker_scope_probe.exe' OR Name='sl3_broker_controller.exe'"|Select-Object ProcessId,Name)
        if($record.testProcessesAfter.Count){throw 'A device-test process remains after the trace'}
    }catch{if(-not $record.error){$record.error=$_.Exception.Message}}
    $record.completed=($null -eq $record.error);$record.completedUtc=[datetime]::UtcNow.ToString('o');Save-Context
}
if($record.error){throw $record.error}
