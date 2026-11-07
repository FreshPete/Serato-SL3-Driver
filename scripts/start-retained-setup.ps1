# Start the retained setup from the operator's desktop. Plan is the default.
[CmdletBinding(DefaultParameterSetName='Plan')]
param(
    [Parameter(ParameterSetName='Setup')][switch]$Run,
    [Parameter(ParameterSetName='Trial')][switch]$Trial
)

$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if (([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Start from your normal Windows desktop session.'
}

$experiment = Join-Path (Split-Path -Parent $PSScriptRoot) 'analysis/sl3-on-demand-test-retained-idle-guard-20261107/experiment.json'
$expected = '0d842831f4c1b0a6dfa02ef8f0d07608132aec5128da42b29d8518666f45b538'
$handoff = Join-Path $PSScriptRoot 'retained-setup-handoff.py'
$handoffSha = '1ea6cecbb07f3b4eeabaf58ac1d9534c1746a711f82910f6f8f04cfeb1675c33'
$leases = [Collections.Generic.List[IO.FileStream]]::new()

function Hold-ReviewedFile([string]$Path,[string]$Sha) {
    if ($Path -notmatch '^[A-Za-z]:[\\/]' -or
        ((Get-Item -LiteralPath $Path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Expected a local reviewed file.'
    }
    $lease = [IO.File]::Open($Path,'Open','Read','Read')
    $leases.Add($lease)
    if ((Get-FileHash -InputStream $lease -Algorithm SHA256).Hash -ne $Sha) {
        throw "Reviewed file hash differs for $Path"
    }
}

function Read-ReviewedPlan([string]$Python) {
    $raw = & $Python -I -B $handoff plan --experiment $experiment --expected-experiment-sha256 $expected
    if ($LASTEXITCODE) { throw 'The read-only check of the original Serato setup did not pass.' }
    $plan = $raw | ConvertFrom-Json
    if ($plan.schema -ne 'sl3.retained-setup-handoff.v1' -or $plan.planOnly -ne $true -or
        $plan.experimentSha256 -ne $expected -or $plan.freshSetupRecordDirectory -isnot [bool]) {
        throw 'Unexpected setup plan result.'
    }
    $plan
}

function Publish-TrialReadout([string]$Python,[string]$Folder,[bool]$SetupExited) {
    $moduleReport = Join-Path $Folder 'desktop-start/module-observation.json'
    $brokerReport = Join-Path $Folder 'broker/result.json'
    $restoreReport = Join-Path $Folder 'attended-setup/restore-stdout.json'
    $output = Join-Path $Folder 'desktop-start/start-readout.json'
    $reader = Join-Path $PSScriptRoot 'read-retained-start-result.py'
    $arguments = @('--module-report',$moduleReport,
        '--module-report-sha256',(Get-FileHash -LiteralPath $moduleReport).Hash.ToLowerInvariant(),
        '--broker-report',$brokerReport,
        '--broker-report-sha256',(Get-FileHash -LiteralPath $brokerReport).Hash.ToLowerInvariant(),
        '--output',$output)
    if ($SetupExited -and (Test-Path -LiteralPath $restoreReport -PathType Leaf)) {
        $arguments += @('--restore-report',$restoreReport,
            '--restore-report-sha256',(Get-FileHash -LiteralPath $restoreReport).Hash.ToLowerInvariant())
    }
    $raw = & $Python -I -B $reader @arguments
    if ($LASTEXITCODE) { throw 'The saved startup reports could not be matched.' }
    $result = $raw | ConvertFrom-Json
    if ($result.schema -ne 'sl3.retained-start-readout.v1') { throw 'Unexpected startup readout.' }
    Write-Host ('Serato process sampled: {0}. ASIO driver sampled: {1}.' -f $result.ordinaryProcessObserved,$result.moduleLoadObserved)
    if ($result.moduleDisappearanceSampled) { Write-Host 'A later sample of the same Serato process showed the driver had disappeared.' }
    Write-Host ('Broker replies to that process: {0} admissions, {1} stream starts.' -f
        $result.matchingAdmissionReplies,$result.matchingStreamStartReplies)
    Write-Host ('Startup summary saved to {0}' -f $output)
}

function Invoke-ReviewedTrial($Record, $SetupProcess) {
    $desktop = Join-Path $PSScriptRoot 'retained-desktop-trial.py'
    $observer = Join-Path $PSScriptRoot 'observe-asio-module-load.ps1'
    $desktopArgs = @('--experiment',$experiment,'--expected-experiment-sha256',$expected,
        '--expected-launch-sha256','c2ca50acac0acd6296a85471d00e30249a92c4c2159f5564acadbffae8d1abf8')
    $folder = Split-Path -Parent $experiment
    $name = [IO.Path]::GetFileNameWithoutExtension($Record.application)
    $started = $false
    $retired = $false
    try {
        Write-Host 'Checking the USB connection. Keep Serato closed.'
        $startup = & $Record.python.path -I -B $desktop start @desktopArgs --recovery-confirmed
        if ($LASTEXITCODE) { throw 'The retained USB check stopped. See the desktop startup records.' }
        $startup = $startup | ConvertFrom-Json
        if ($startup.outcome -ne 'broker_ready') { throw 'Unexpected retained USB result.' }
        $started = $true
        if ($null -eq $startup.sl3VisibleDuring) {
            Write-Host 'USB visibility was inconclusive while the connection was held. The broker is ready for the Serato check.'
        } elseif ($startup.sl3VisibleDuring) {
            Write-Host 'The USB snapshots showed the SL3 while the connection was held.'
        } else {
            Write-Host 'The USB snapshots did not show the SL3 while the connection was held. The Serato check can still run.'
        }

        Write-Host 'When the observer is armed, open Serato from its usual shortcut. Leave playback stopped.'
        Write-Host 'Note what Serato shows. Keep it open for five seconds after hardware status appears, then close it normally.'
        Write-Host 'Leave any Download Driver notice untouched.'
        $module = Join-Path $env:ProgramFiles 'SL3 Rebuild/on-demand-diagnostic-v2/sl3_asio.dll'
        $observed = & $observer -Application $Record.application -Module $module `
            -ApplicationSha256 $Record.applicationSha256 `
            -ModuleSha256 '9d41ddcc0de481cd966d6786b15e656a3dcc6e4d71191815e6431a4009a9be55' -TimeoutSeconds 45 -FollowUpSeconds 5
        if (($observed | ConvertFrom-Json).schema -ne 'sl3.asio-module-observation.v1') {
            throw 'Unexpected module observation result.'
        }
        $path = Join-Path $folder 'desktop-start/module-observation.json'
        $stream = [IO.File]::Open($path,'CreateNew','Write','Read')
        try {
            $bytes = [Text.Encoding]::UTF8.GetBytes(($observed -join "`n") + "`n")
            $stream.Write($bytes,0,$bytes.Length)
        } finally { $stream.Dispose() }
    } finally {
        if (($started -or (Test-Path -LiteralPath (Join-Path $folder 'broker.pointer.json') -PathType Leaf)) -and
            -not $SetupProcess.HasExited) {
            $close = [Diagnostics.Stopwatch]::StartNew()
            while ((Get-Process -Name $name -ErrorAction SilentlyContinue) -and $close.Elapsed.TotalSeconds -lt 35) {
                Start-Sleep -Milliseconds 250
            }
            if (Get-Process -Name $name -ErrorAction SilentlyContinue) {
                Write-Host 'Serato is still open. Close it normally so the setup process can restore the original files.'
            } else {
                Write-Host 'Retiring the USB connection and requesting restoration.'
                $finished = & $Record.python.path -I -B $desktop finish @desktopArgs
                $retired = $LASTEXITCODE -eq 0 -and ($finished | ConvertFrom-Json).outcome -eq 'retired'
                if (-not $retired) { Write-Host 'Check the desktop and setup records to verify cleanup.' }
            }
        } elseif (-not $SetupProcess.HasExited) {
            # Startup can fail before the desktop runner installs its own cleanup path.
            $request = Join-Path $folder 'attended-setup/restore.request'
            if (-not (Test-Path -LiteralPath $request -PathType Leaf)) {
                try {
                    $stream = [IO.File]::Open($request,'CreateNew','Write','Read')
                    $stream.Dispose()
                    Write-Host 'Startup stopped. Requesting restoration of the original Serato setup.'
                } catch {
                    if (-not (Test-Path -LiteralPath $request -PathType Leaf)) {
                        Write-Warning 'Could not request early restoration. The setup process still has its timed cleanup.'
                    }
                }
            }
        }
        $setupExited = $SetupProcess.WaitForExit(25000)
        if ($setupExited) {
            $result = Get-Content -LiteralPath (Join-Path $folder 'attended-setup/result.json') -Raw -ErrorAction SilentlyContinue |
                ConvertFrom-Json -ErrorAction SilentlyContinue
            if ($result.outcome -in 'restored','restored_after_failed_setup') {
                try {
                    Read-ReviewedPlan $Record.python.path | Out-Null
                    Write-Host 'Original Serato setup restored and independently verified.'
                } catch { Write-Warning ('Restoration was reported. The independent check failed. ' + $_.Exception.Message) }
            } else { Write-Host 'See the setup result for restoration status.' }
        } else { Write-Host 'Restoration is still pending. Check the setup result before retrying.' }
    }
    if ($retired) {
        try { Publish-TrialReadout $Record.python.path $folder $setupExited }
        catch { Write-Warning ('Startup summary unavailable. Review the saved reports. ' + $_.Exception.Message) }
    }
}

$mutex = $null
$claimed = $false
$child = $null
try {
    if ($Run -or $Trial) {
        $mutex = [Threading.Mutex]::new($false, "Local\SL3RetainedSetup-$expected")
        try { $claimed = $mutex.WaitOne(0) }
        catch [Threading.AbandonedMutexException] { $claimed = $true }
        if (-not $claimed) { throw 'A setup launch is already being observed for this experiment.' }
    }
    Hold-ReviewedFile $Experiment $expected
    $record = Get-Content -LiteralPath $Experiment -Raw | ConvertFrom-Json
    if ($record.schema -ne 'sl3.on-demand-normal-start-test.v1' -or $record.retainedBroker -ne $true) {
        throw 'Expected the reviewed retained-broker experiment.'
    }
    $python = $record.python.path
    Hold-ReviewedFile $python $record.python.sha256
    Hold-ReviewedFile $handoff $handoffSha
    $plan = Read-ReviewedPlan $python
    if (-not ($Run -or $Trial)) { $plan | ConvertTo-Json -Depth 4; return }
    if (-not $plan.freshSetupRecordDirectory) { throw 'This trial already has setup records. Preserve them and prepare a fresh trial before requesting approval.' }
    if ($Trial) {
        Hold-ReviewedFile (Join-Path $PSScriptRoot 'retained-desktop-trial.py') '50f748fcc01407ef9f38e32a7d64eeb750d274e01b42b35fb9f6b60be245560c'
        Hold-ReviewedFile (Join-Path $PSScriptRoot 'observe-asio-module-load.ps1') '97f15e24e861f8cd82c68ee0723c598382ecf6e41511790c7ea1c12a9147bf0d'
        Hold-ReviewedFile (Join-Path $PSScriptRoot 'inspect-process.psm1') '6ffb8427f79ebd173fd31e9824442293eb66689107fe63307204f76a6db4a290'
        Hold-ReviewedFile (Join-Path $PSScriptRoot 'read-retained-start-result.py') 'd4b91ac3dd7fffa24a6f2ce25a5347d61dfcf1928ccb1f29f711a776e103f012'
        $confirmation = Read-Host 'Power-cycle the SL3 for 30 seconds, reconnect it, wait 30 seconds, close Serato and type RECOVERED'
        if ($confirmation -cne 'RECOVERED') { Write-Host 'Test canceled before setup.'; return }
    }

    Write-Host 'Approve the Windows prompt for temporary SL3 setup. Leave Serato closed for now.'
    try {
        $arguments = @('-I','-B',('"{0}"' -f $handoff),'run','--experiment',('"{0}"' -f $Experiment),
                       '--expected-experiment-sha256',$expected)
        $startInfo = [Diagnostics.ProcessStartInfo]::new($python, ($arguments -join ' '))
        $startInfo.WorkingDirectory = Split-Path -Parent $PSScriptRoot
        $startInfo.UseShellExecute = $true
        $startInfo.Verb = 'runas'
        $startInfo.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
        # Preserve the Win32 error code if the shell cancels elevation.
        $child = [Diagnostics.Process]::Start($startInfo)
        if ($null -eq $child) { throw 'Windows returned no setup process.' }
    } catch {
        $cause = $_.Exception
        while ($cause.InnerException) { $cause = $cause.InnerException }
        if ($cause -is [ComponentModel.Win32Exception] -and $cause.NativeErrorCode -eq 1223) {
            Write-Host 'Windows canceled the approval. Setup did not start.'
            exit 1
        }
        throw
    }

    $windowPath = Join-Path (Split-Path -Parent $Experiment) 'attended-setup/window.json'
    $clock = [Diagnostics.Stopwatch]::StartNew()
    while (-not $child.HasExited -and $clock.Elapsed.TotalSeconds -lt 120) {
        if (Test-Path -LiteralPath $windowPath -PathType Leaf) {
            try { $window = Get-Content -LiteralPath $windowPath -Raw | ConvertFrom-Json }
            catch { $window = $null }
            if ($window -and $window.schema -eq 'sl3.retained-setup-window.v1' -and
                $window.experimentSha256 -eq $expected -and $window.pid -eq $child.Id -and -not $child.HasExited) {
                if ($Trial) { Invoke-ReviewedTrial $record $child; return }
                Write-Host 'Temporary setup is ready. Leave Serato closed until the USB check and observer are ready.'
                $window | ConvertTo-Json
                return
            }
        }
        Start-Sleep -Milliseconds 200
    }
    if ($child.HasExited) { throw 'The setup process exited before a live test window was verified. Check the handoff records.' }
    throw 'Setup is still running. Check the existing handoff before starting another attempt.'
} finally {
    if ($child) { $child.Dispose() }
    foreach ($lease in $leases) { $lease.Dispose() }
    if ($claimed) { $mutex.ReleaseMutex() }
    if ($mutex) { $mutex.Dispose() }
    $identity.Dispose()
}
