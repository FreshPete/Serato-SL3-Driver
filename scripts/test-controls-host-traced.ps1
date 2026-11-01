#requires -Version 7.5
param([switch]$Run,[switch]$WithUsbDkLifecycle,[switch]$WithUsbIdentity,[string]$ResultDirectory='tests/results/local/controls-host-traced-01')
# Explicit no-audio read-only diagnostic. Never self-elevates or retries.
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if($ResultDirectory -match '["\r\n]'){throw 'Invalid result path'}
if(-not [IO.Path]::IsPathRooted($ResultDirectory)){$ResultDirectory=Join-Path $root $ResultDirectory}
$ResultDirectory=[IO.Path]::GetFullPath($ResultDirectory)
if($ResultDirectory.StartsWith('\\')){throw 'A local output directory is required'}
if(Test-Path -LiteralPath $ResultDirectory){throw 'Choose a fresh evidence directory'}
if(-not $Run){
    [ordered]@{planOnly=$true;deviceAccess=$false;resultDirectory=$ResultDirectory;redirectsRequested=1
        getters=@('rate 0x30','audio controls 0x32');audioStartAttempts=0;alternateChanges=0;controlSetters=0;rateChanges=0
        driverChanges=$false;securityChanges=$false;asioRegistration=$false;automaticRetry=$false
        traceSeconds=60;probeDeadlineSeconds=40;output='Defined 22-byte control table; original UI interpretation; independent cleanup'
        withUsbDkLifecycle=[bool]$WithUsbDkLifecycle;lifecycleSharesUsbTraceSession=[bool]$WithUsbDkLifecycle
        withUsbIdentity=[bool]$WithUsbIdentity;identitySeconds=45;identityIntervalMilliseconds=50
        identityRequiresCompleteBeforeAndAfter=[bool]$WithUsbIdentity;heldDeviceIdentityCoverageVerified=$false
        prerequisites=@('Owner present; already elevated terminal; Secure Boot enabled; reviewed driver running',
            'Current tested native probe/worker and scripts; no remaining test worker',
            'A fresh result directory and normal SL3 recovery baseline; no audio fixture required')}
        |ConvertTo-Json -Depth 5
    return
}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
if(-not ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'An elevated terminal is required'}
if(-not (Confirm-SecureBootUEFI)){throw 'Secure Boot must remain enabled'}
if(@(Get-CimInstance Win32_Process -Filter "Name='sl3_usbdk.exe' OR Name='sl3_host_probe.exe' OR Name='sl3_host_probe_simulated.exe'").Count){throw 'A prior device-test process remains; do not reopen'}
$preflight=& (Join-Path $PSScriptRoot 'preflight-usbdk.ps1')|ConvertFrom-Json
if(@($preflight.installedDriver|Where-Object State -eq 'Running').Count -ne 1){throw 'Reviewed UsbDk must already be running'}
$build=Get-Content -LiteralPath (Join-Path $root 'artifacts/build/native/native-build-Release.json') -Raw|ConvertFrom-Json
$probe=Join-Path $root 'artifacts/build/native/Release/sl3_host_probe.exe'
$worker=Join-Path $root 'artifacts/build/native/Release/sl3_usbdk.exe'
$helper=Join-Path $root 'artifacts/extracted/usbdk-msi/UsbDkHelper.dll10'
$python=Join-Path $root '.venv/Scripts/python.exe'
$validator=Join-Path $PSScriptRoot 'validate-controls-host-probe.py'
if(-not $build.hostProbe.controls.simulatedLifecyclePassed -or $build.hostProbe.controls.nativeQueryRunDuringBuild -or
   (Get-FileHash -LiteralPath $probe).Hash -ne $build.hostProbe.executableSha256 -or
   (Get-FileHash -LiteralPath $worker).Hash -ne $build.usbdk.executableSha256){throw 'Controls probe/worker is not the tested build'}
$names=@('test-controls-host-traced.ps1','validate-controls-host-probe.py','test-controls-host-probe.py','read-startup-journal.ps1',
    'capture-usb-startup.ps1','preflight-usbdk.ps1','collect-windows-state.ps1','export-usbdk-physical-checkpoint.py','validate-usbdk-capture.py',
    'prepare-usbdk-lifecycle-trace.py','observe-sl3-usb-identity.py','supervise-usb-identity.py','controls-usb-identity.py',
            'capture-controls-user-context.ps1','test-controls-user-probe.ps1','inspect-process.psm1','validate-controls-user-probe.py')
if(@($build.hostProbe.controls.scriptInputs.PSObject.Properties).Count -ne $names.Count){throw 'Missing reviewed controls dependencies'}
foreach($name in $names){
    if((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name)).Hash -ne $build.hostProbe.controls.scriptInputs.$name){throw "Reviewed controls dependency changed: $name"}
}
$plan=& $probe --plan|ConvertFrom-Json
if($LASTEXITCODE -ne 0 -or $plan.simulated -or $plan.device_access -or $plan.controls_inspection.audio -or $plan.controls_inspection.mode -ne '--controls'){
    throw 'Probe plan is not the explicit native controls-only contract'
}
New-Item -ItemType Directory -Path $ResultDirectory|Out-Null
$record=[ordered]@{schema='sl3.controls-host.traced-run.v1';startedUtc=[datetime]::UtcNow.ToString('o');completed=$false;error=$null
    workerSha256=$preflight.nativeSha256;probeSha256=(Get-FileHash -LiteralPath $probe).Hash;probeExitCode=$null;traceExitCode=$null
    traceCleanupConfirmed=$false;secureBootBefore=$true;secureBootAfter=$false;recoveryConfirmed=$false
    withUsbDkLifecycle=[bool]$WithUsbDkLifecycle;withUsbIdentity=[bool]$WithUsbIdentity
    driverChanges=$false;securityChanges=$false;asioRegistration=$false;automaticRetry=$false;runnerInputs=[ordered]@{}}
foreach($name in $names){$record.runnerInputs[$name]=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name)).Hash}
function Save-Run{$record|ConvertTo-Json -Depth 12|Set-Content -LiteralPath (Join-Path $ResultDirectory 'run.json')}
function Quoted([string]$Value){'"'+$Value+'"'}
function Child([string]$File,[string[]]$Arguments,[string]$Name){
    Start-Process -FilePath $File -ArgumentList $Arguments -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $ResultDirectory "$Name-output.txt") -RedirectStandardError (Join-Path $ResultDirectory "$Name-error.txt")
}
function Wait-Child($Process,[int]$Milliseconds){
    if($Process.WaitForExit($Milliseconds)){return}
    $record.timedOutProcessId=$Process.Id;$Process.Kill($true);$record.timedOutProcessExited=$Process.WaitForExit(5000)
    throw 'Child exceeded its deadline; ownership/recovery must be inspected before another attempt'
}
function Trace-Record{try{Get-Content -LiteralPath (Join-Path $ResultDirectory 'trace/capture.json') -Raw|ConvertFrom-Json -DateKind String}catch{$null}}
function Contract($State){
    [ordered]@{secureBoot=$State.secureBoot;deviceGuard=$State.deviceGuard;hvciRegistry=$State.hvciRegistry
        devices=@($State.devices|Sort-Object {$_.device.InstanceId}|ForEach-Object {
            [ordered]@{device=$_.device;properties=@($_.properties|Sort-Object KeyName)}})
        asio=$State.asio;application=$State.application}|ConvertTo-Json -Depth 12 -Compress
}
$traceProcess=$null;$identityProcess=$null;$before=$null;Save-Run
try{
    & (Join-Path $PSScriptRoot 'collect-windows-state.ps1') -Output (Join-Path $ResultDirectory 'before-state.json')|Out-Null
    $before=Get-Content -LiteralPath (Join-Path $ResultDirectory 'before-state.json') -Raw|ConvertFrom-Json
    if(@($before.devices).Count -ne 1 -or $before.secureBoot -ne $true){throw 'One SL3 and enabled Secure Boot required'}
    $traceArguments=@('-NoProfile','-File',(Quoted (Join-Path $PSScriptRoot 'capture-usb-startup.ps1')),
        '-Capture','-DurationSeconds','60','-OutputDirectory',(Quoted (Join-Path $ResultDirectory 'trace')))
    if($WithUsbDkLifecycle){$traceArguments+='-WithUsbDkLifecycle'}
    $traceProcess=Child (Get-Process -Id $PID).Path $traceArguments 'trace'
    $ready=$false
    for($i=0;$i -lt 100;$i++){
        if($traceProcess.HasExited){throw 'Trace exited before readiness'}
        $trace=Trace-Record
        if($trace.status -eq 'recording'){$ready=$true;break}
        Start-Sleep -Milliseconds 200
    }
    if(-not $ready -or ([datetime]::UtcNow-[datetime]$trace.startedUtc).TotalSeconds -gt 10){throw 'Trace is not ready with enough remaining time'}
    if($trace.plan.withUsbDkLifecycle -ne [bool]$WithUsbDkLifecycle){throw 'Trace lifecycle selection differs before device admission'}
    if($WithUsbDkLifecycle -and @($trace.commands|Where-Object {
        $_.arguments[0] -eq 'update' -and $_.arguments[5] -eq '{88e1661f-48b6-410f-b096-ba84e9f0656f}' -and
        $_.arguments[6] -eq '0x650' -and $_.arguments[7] -eq '4' -and $_.exitCode -eq 0
    }).Count -ne 1){throw 'Lifecycle provider was not configured before device admission'}
    $null=& logman.exe query $trace.session -ets 2>&1
    if($LASTEXITCODE -ne 0){throw 'Trace session is not live'}
    if($WithUsbIdentity){
        if(([datetime]::UtcNow-[datetime]$trace.startedUtc).TotalSeconds -gt 5){throw 'Insufficient shared trace time for identity observation'}
        $identityProcess=Child $python @((Quoted (Join-Path $PSScriptRoot 'supervise-usb-identity.py')),'--run',
            '--seconds','45','--interval-ms','50','--result-directory',(Quoted (Join-Path $ResultDirectory 'usb-identity'))) 'identity'
        $record.usbIdentitySupervisorPid=$identityProcess.Id;Save-Run
        $identityReady=$false;$readinessDeadline=[datetime]::UtcNow.AddSeconds(3)
        while([datetime]::UtcNow -lt $readinessDeadline){
            if($identityProcess.HasExited){throw 'Identity observer exited before probe admission'}
            $readyText=& $python (Join-Path $PSScriptRoot 'controls-usb-identity.py') --ready (Join-Path $ResultDirectory 'usb-identity')
            if($LASTEXITCODE -ne 0){throw 'Identity admission check failed'}
            $admission=$readyText|ConvertFrom-Json -DateKind String
            if($admission.ready -eq $true){
                $readyText|Set-Content -LiteralPath (Join-Path $ResultDirectory 'identity-ready.json')
                $record.usbIdentityReadySha256=(Get-FileHash -LiteralPath (Join-Path $ResultDirectory 'identity-ready.json')).Hash
                $identityReady=$true;break
            }
            Start-Sleep -Milliseconds 100
        }
        if(-not $identityReady){throw 'No fresh complete SL3 identity before probe admission'}
    }
    if((Get-FileHash -LiteralPath $probe).Hash -ne $record.probeSha256 -or (Get-FileHash -LiteralPath $worker).Hash -ne $record.workerSha256){throw 'Executables changed'}
    $record.probeStartedUtc=[datetime]::UtcNow.ToString('o');Save-Run
    $child=Child $probe @('--controls','--worker',(Quoted $worker),'--worker-sha256',$record.workerSha256,
        '--helper',(Quoted $helper),'--output',(Quoted (Join-Path $ResultDirectory 'probe'))) 'probe'
    Wait-Child $child 40000
    $record.probeCompletedUtc=[datetime]::UtcNow.ToString('o');$record.probeExitCode=$child.ExitCode
    $probePath=Join-Path $ResultDirectory 'probe/probe.json'
    if(Test-Path -LiteralPath $probePath){$record.probeRecordSha256=(Get-FileHash -LiteralPath $probePath).Hash}
    $record.startupJournals=@(Get-ChildItem -LiteralPath (Join-Path $ResultDirectory 'probe') -Filter 'worker-*.tsv' -ErrorAction SilentlyContinue|ForEach-Object {
        & (Join-Path $PSScriptRoot 'read-startup-journal.ps1') -Path $_.FullName|ConvertFrom-Json
    })
    if($child.ExitCode -ne 0){throw 'Controls probe failed; preserve its sample/progress and do not retry'}
    $validation=& $python $validator --probe (Join-Path $ResultDirectory 'probe') --worker-sha256 $record.workerSha256
    $validation|Set-Content -LiteralPath (Join-Path $ResultDirectory 'probe-validation.json')
    if($LASTEXITCODE -ne 0 -or ($validation|ConvertFrom-Json).valid -ne $true){throw 'Controls result/journal validation failed'}
    $record.probeValidationSha256=(Get-FileHash -LiteralPath (Join-Path $ResultDirectory 'probe-validation.json')).Hash
}catch{$record.error=$_.Exception.Message}
finally{
    try{
        if($identityProcess){
            Wait-Child $identityProcess 60000
            $record.usbIdentityExitCode=$identityProcess.ExitCode
            if($identityProcess.ExitCode -ne 0){throw 'Identity supervisor failed; do not retry'}
            $identityValidation=& $python (Join-Path $PSScriptRoot 'supervise-usb-identity.py') --validate (Join-Path $ResultDirectory 'usb-identity')
            if($LASTEXITCODE -ne 0){throw 'Identity observation/retirement validation failed'}
            $identityValidation|Set-Content -LiteralPath (Join-Path $ResultDirectory 'identity-validation.json')
            $record.usbIdentityValidationSha256=(Get-FileHash -LiteralPath (Join-Path $ResultDirectory 'identity-validation.json')).Hash
            $record.usbIdentitySupervisorRecordSha256=(Get-FileHash -LiteralPath (Join-Path $ResultDirectory 'usb-identity/supervisor.json')).Hash
        }
    }catch{if(-not $record.error){$record.error=$_.Exception.Message}}
    try{
        if($traceProcess){
            Wait-Child $traceProcess 75000;$record.traceExitCode=$traceProcess.ExitCode;$trace=Trace-Record
            if($traceProcess.ExitCode -ne 0 -or $trace.status -ne 'window completed'){throw 'USB trace failed'}
            $record.traceCleanupConfirmed=(@($trace.commands|Where-Object {$_.arguments[0] -eq 'delete' -and $_.exitCode -eq 0}).Count -eq 1)
            if(-not $record.traceCleanupConfirmed){throw 'USB trace cleanup is unproved'}
            $record.traceRecordSha256=(Get-FileHash -LiteralPath (Join-Path $ResultDirectory 'trace/capture.json')).Hash
            $record.traceStartedUtc=$trace.startedUtc;$record.traceStoppedUtc=$trace.stoppedUtc
            $etls=@(Get-ChildItem -LiteralPath (Join-Path $ResultDirectory 'trace') -Filter '*.etl')
            if($etls.Count -ne 1){throw 'Expected one USB ETL'}
            $record.etlSha256=(Get-FileHash -LiteralPath $etls[0].FullName).Hash
            $decoder=Child 'tracerpt.exe' @((Quoted $etls[0].FullName),'-o',(Quoted (Join-Path $ResultDirectory 'events.xml')),'-of','XML','-y') 'decode'
            Wait-Child $decoder 60000
            if($decoder.ExitCode -ne 0){throw 'USB trace decoding failed'}
            $stats=& $python (Join-Path $PSScriptRoot 'validate-usbdk-capture.py') --trace-xml (Join-Path $ResultDirectory 'events.xml')
            if($LASTEXITCODE -ne 0){throw 'USB trace statistics unavailable'}
            $record.traceStats=$stats|ConvertFrom-Json
            if($record.traceStats.eventsLost -ne 0 -or $record.traceStats.buffersLost -ne 0){throw 'USB trace lost events'}
        }
    }catch{if(-not $record.error){$record.error=$_.Exception.Message}}
    if($traceProcess -and -not $record.traceCleanupConfirmed){
        # Clean only the uniquely named collector whose creation our child recorded.
        $owned=Trace-Record
        if($owned.session -match '^SL3Startup-[0-9a-f]{32}$' -and @($owned.commands|Where-Object {$_.arguments[0] -eq 'create' -and $_.exitCode -eq 0}).Count){
            try{$null=& logman.exe stop -n $owned.session 2>&1;$record.fallbackTraceStopExitCode=$LASTEXITCODE}
            catch{$record.fallbackTraceStopError=$_.Exception.Message}
            try{$null=& logman.exe delete -n $owned.session 2>&1;$record.fallbackTraceDeleteExitCode=$LASTEXITCODE}
            catch{$record.fallbackTraceDeleteError=$_.Exception.Message}
        }
    }
    try{
        & (Join-Path $PSScriptRoot 'collect-windows-state.ps1') -Output (Join-Path $ResultDirectory 'after-state.json')|Out-Null
        $after=Get-Content -LiteralPath (Join-Path $ResultDirectory 'after-state.json') -Raw|ConvertFrom-Json
        $record.secureBootAfter=$after.secureBoot -eq $true;$record.recoveryConfirmed=($before -and (Contract $before) -ceq (Contract $after))
        $record.beforeStateSha256=(Get-FileHash -LiteralPath (Join-Path $ResultDirectory 'before-state.json')).Hash
        $record.afterStateSha256=(Get-FileHash -LiteralPath (Join-Path $ResultDirectory 'after-state.json')).Hash
        if(-not $record.secureBootAfter -or -not $record.recoveryConfirmed){throw 'Selected security/device recovery differs'}
    }catch{if(-not $record.error){$record.error=$_.Exception.Message}}
    $record.completed=($record.error -eq $null);$record.completedUtc=[datetime]::UtcNow.ToString('o');Save-Run
}
if($record.error){throw $record.error}
try{
    $checked=& $python $validator --run $ResultDirectory --worker-sha256 $record.workerSha256 --probe-sha256 $record.probeSha256
    $checked|Set-Content -LiteralPath (Join-Path $ResultDirectory 'run-validation.json')
    if($LASTEXITCODE -ne 0 -or ($checked|ConvertFrom-Json).valid -ne $true){throw 'Final controls trace/window/recovery validation failed'}
}catch{$record.completed=$false;$record.error=$_.Exception.Message;Save-Run;throw}
$record|ConvertTo-Json -Depth 12
