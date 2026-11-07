# Start the retained setup from the operator's desktop. Plan is the default.
[CmdletBinding()]
param([switch]$Run)

$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if (([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Start from your normal Windows desktop session.'
}

$experiment = Join-Path (Split-Path -Parent $PSScriptRoot) 'analysis/sl3-on-demand-test-retained-idle-guard-20261107/experiment.json'
$expected = '0d842831f4c1b0a6dfa02ef8f0d07608132aec5128da42b29d8518666f45b538'
$handoff = Join-Path $PSScriptRoot 'retained-setup-handoff.py'
$handoffSha = 'cfac264d1a2a6285679aca6f5640c6f8110ae3e2f0844d67cebc20f5796e28e1'
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

$mutex = $null
$claimed = $false
$child = $null
try {
    if ($Run) {
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
    $preflight = & $python -I -B $handoff plan --experiment $Experiment --expected-experiment-sha256 $expected
    if ($LASTEXITCODE) { throw 'The retained setup preflight did not pass.' }
    $plan = $preflight | ConvertFrom-Json
    if ($plan.schema -ne 'sl3.retained-setup-handoff.v1' -or $plan.planOnly -ne $true -or
        $plan.experimentSha256 -ne $expected) { throw 'Unexpected setup plan result.' }
    if (-not $Run) { $preflight; return }

    Write-Host 'Approve the Windows prompt for temporary SL3 setup. Leave Serato closed for now.'
    try {
        $arguments = @('-I','-B',('"{0}"' -f $handoff),'run','--experiment',('"{0}"' -f $Experiment),
                       '--expected-experiment-sha256',$expected)
        $child = Start-Process -FilePath $python -ArgumentList $arguments -Verb RunAs -WindowStyle Hidden -PassThru
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
