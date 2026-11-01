#requires -Version 7.5
param([switch]$Run, [string]$ResultDirectory='tests/results/local/usbdk-install-01')
# Installs only the reviewed unchanged MSI. No trust/security/firmware changes.
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if($ResultDirectory -match '["\r\n]'){throw 'Invalid result path'}
if(-not [IO.Path]::IsPathRooted($ResultDirectory)){$ResultDirectory=Join-Path $root $ResultDirectory}
$ResultDirectory=[IO.Path]::GetFullPath($ResultDirectory)
if(Test-Path -LiteralPath $ResultDirectory){throw 'Choose a fresh evidence directory'}
$msi=Join-Path $root 'artifacts/packages/UsbDk_1.0.22_x64.msi'
if(-not $Run){
    [ordered]@{planOnly=$true;package=$msi;resultDirectory=$ResultDirectory
        scope='System USB filter installation, passive 60-second USB trace, no device redirection or audio'
        automaticRestart=$false;securityChanges=$false
        recovery='Uninstall the same MSI with msiexec /x; preserve the original Rane package'
    }|ConvertTo-Json
    return
}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
if(-not ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Administrator terminal required'}
if(-not (Confirm-SecureBootUEFI)){throw 'Secure Boot must remain enabled'}
$preflight=& (Join-Path $PSScriptRoot 'preflight-usbdk.ps1')|ConvertFrom-Json
if(@($preflight.installedDriver).Count){throw 'UsbDk is already installed; this test is for first installation only'}
if(@($preflight.sl3).Count -ne 1){throw 'Exactly one connected SL3 is required'}
if((Get-AuthenticodeSignature -LiteralPath $msi).Status -ne 'Valid'){throw 'MSI Authenticode verification failed'}
New-Item -ItemType Directory -Path $ResultDirectory|Out-Null
$record=[ordered]@{schema='sl3.usbdk.install-test.v1';startedUtc=[datetime]::UtcNow.ToString('o')
    installerStarted=$false;installerExitCode=$null;restartRequired=$null;restartRequiredFromMsi=$null;error=$null
    restartRequirementSource='MSI result only; helper notices require separate review'
    securityChanges=$false;automaticRestart=$false;deviceRedirected=$false;audioSubmissions=0}
function Save-Record { $record|ConvertTo-Json -Depth 10|Set-Content -LiteralPath (Join-Path $ResultDirectory 'install.json') -Encoding utf8 }
function Read-Trace {
    try { Get-Content -LiteralPath (Join-Path $ResultDirectory 'trace/capture.json') -Raw|ConvertFrom-Json } catch { $null }
}
$trace=$null
Save-Record
try {
    $preflight|ConvertTo-Json -Depth 10|Set-Content -LiteralPath (Join-Path $ResultDirectory 'preflight.json')
    & (Join-Path $PSScriptRoot 'collect-windows-state.ps1') -Output (Join-Path $ResultDirectory 'before-state.json')|Out-Null
    $pwsh=(Get-Process -Id $PID).Path
    $trace=Start-Process -FilePath $pwsh -WindowStyle Hidden -PassThru -ArgumentList @('-NoProfile','-File',('"'+(Join-Path $PSScriptRoot 'capture-usb-startup.ps1')+'"'),'-Capture','-DurationSeconds','60','-OutputDirectory',('"'+(Join-Path $ResultDirectory 'trace')+'"')) -RedirectStandardOutput (Join-Path $ResultDirectory 'trace-output.txt') -RedirectStandardError (Join-Path $ResultDirectory 'trace-error.txt')
    $ready=$false
    for($i=0;$i -lt 100;$i++){
        if($trace.HasExited){throw 'Trace failed before installation'}
        $capture=Read-Trace
        if($capture.status -eq 'recording'){$ready=$true;break}
        Start-Sleep -Milliseconds 200
    }
    if(-not $ready){throw 'Trace readiness deadline exceeded'}
    $null=& logman.exe query $capture.session -ets 2>&1
    if($LASTEXITCODE -ne 0){throw 'USB trace is not live'}
    if((Get-FileHash -LiteralPath $msi).Hash -ne '91F6F695E1E13C656024E6D3B55620BF08D8835EF05EE0496935BA6BB62466A5'){throw 'Installer changed'}
    $record.installerStartedUtc=[datetime]::UtcNow.ToString('o');$record.installerStarted=$true;Save-Record
    # Do not terminate Windows Installer mid-transaction. /norestart and
    # REBOOT=ReallySuppress prevent an automatic restart even when required.
    $installer=Start-Process -FilePath "$env:SystemRoot\System32\msiexec.exe" -WindowStyle Hidden -PassThru -ArgumentList @('/i',('"'+$msi+'"'),'/qn','/norestart','REBOOT=ReallySuppress','/L*v',('"'+(Join-Path $ResultDirectory 'msi.log')+'"'))
    $installer.WaitForExit()
    $record.installerCompletedUtc=[datetime]::UtcNow.ToString('o')
    $record.installerExitCode=$installer.ExitCode
    $record.restartRequiredFromMsi=$installer.ExitCode -in @(3010,1641)
    # The reviewed helper can show a restart-required notice and still let
    # MSI return zero. Success alone therefore cannot establish no restart.
    $record.restartRequired=if($record.restartRequiredFromMsi){$true}else{$null}
    Save-Record
    if($installer.ExitCode -notin @(0,3010)){throw "Installer returned $($installer.ExitCode); inspect MSI log before any retry"}
} catch {
    $record.error=$_.Exception.Message
} finally {
    if($trace){
        $record.traceProcessExited=$trace.WaitForExit(75000)
        if($record.traceProcessExited){$record.traceExitCode=$trace.ExitCode}
        $capture=Read-Trace
        $record.trace=$capture
        $record.installationWithinTrace=$false
        if($record.installerCompletedUtc -and $capture.startedUtc -and $capture.stoppedUtc){
            $traceDeadline=([datetimeoffset]$capture.startedUtc).AddSeconds(60)
            $record.installationWithinTrace=([datetimeoffset]$record.installerStartedUtc -ge [datetimeoffset]$capture.startedUtc -and [datetimeoffset]$record.installerCompletedUtc -le $traceDeadline -and [datetimeoffset]$record.installerCompletedUtc -le [datetimeoffset]$capture.stoppedUtc)
        }
    }
    try {
        & (Join-Path $PSScriptRoot 'collect-windows-state.ps1') -Output (Join-Path $ResultDirectory 'after-state.json')|Out-Null
        $record.installedDriver=@(Get-CimInstance Win32_SystemDriver -Filter "Name='UsbDk'"|Select-Object Name,State,StartMode,PathName)
        $record.secureBootAfter=[bool](Confirm-SecureBootUEFI)
        $record.codeIntegrityEvents=@(Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-CodeIntegrity/Operational';StartTime=([datetime]$record.startedUtc).ToLocalTime()} -ErrorAction SilentlyContinue|Where-Object Message -Match 'UsbDk'|Select-Object TimeCreated,Id,Message)
    } catch { $record.postcheckError=$_.Exception.Message }
    $record.completedUtc=[datetime]::UtcNow.ToString('o');Save-Record
}
if($record.error){throw $record.error}
$record|ConvertTo-Json -Depth 10
