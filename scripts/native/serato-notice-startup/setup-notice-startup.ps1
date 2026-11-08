param(
    [Parameter(Mandatory)][ValidateSet('Check','Install','Restore')][string]$Action,
    [Parameter(Mandatory)][string]$WatcherSha256,
    [Parameter(Mandatory)][string]$HelperSha256
)

$ErrorActionPreference = 'Stop'
$env:PSModulePath = Join-Path $PSHOME 'Modules'
$folder = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'SL3RebuildNoticeStartup'
$watcher = Join-Path $folder 'watch-notice-startup.ps1'
$ready = Join-Path $folder 'watcher-ready.json'
$powershell = Join-Path ([Environment]::SystemDirectory) 'WindowsPowerShell\v1.0\powershell.exe'
$parameters = '-NoProfile -NonInteractive -WindowStyle Hidden -File "{0}" -Installed' -f $watcher
$command = '"{0}" {1}' -f $powershell,$parameters
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$runName = 'SL3CompatibilityWatcher'
$assets = @{
    'watch-notice-startup.ps1' = $WatcherSha256
    'sl3-notice-startup-early.dll' = $HelperSha256
}
$session = (Get-Process -Id $PID).SessionId

function Read-StartupCommand {
    if (Test-Path -LiteralPath $runKey) {
        (Get-Item -LiteralPath $runKey).GetValue($runName, $null, 'DoNotExpandEnvironmentNames')
    }
}

function Test-Asset([string]$Path, [string]$Digest) {
    $file = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if (!$file) { return $false }
    if ($file.PSIsContainer -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        (Get-FileHash -LiteralPath $Path).Hash -ne $Digest) {
        throw "Unexpected watcher file at $Path"
    }
    return $true
}

function Get-WatcherProcess {
    if (!(Test-Path -LiteralPath $ready -PathType Leaf)) { return }
    try {
        $receipt = Get-Content -LiteralPath $ready -Raw | ConvertFrom-Json
        if ($receipt.session -ne $session) { return }
        $process = Get-Process -Id $receipt.pid -ErrorAction SilentlyContinue
        if ($process -and $process.SessionId -eq $session -and $process.Path -eq $powershell -and
            [string]$process.StartTime.ToUniversalTime().ToFileTimeUtc() -ceq $receipt.created) {
            $process
        }
    } catch [System.ComponentModel.Win32Exception] {
        # The reported process may have just exited.
    }
}

$mutex = [Threading.Mutex]::new($false, 'Local\SL3CompatibilityWatcherSetup-v1')
$owned = $false
try {
    try { $owned = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $owned = $true }
    if (!$owned) { throw 'Another watcher setup action is in progress' }
    $existing = Get-Item -LiteralPath $folder -Force -ErrorAction SilentlyContinue
    if ($existing -and (!$existing.PSIsContainer -or ($existing.Attributes -band [IO.FileAttributes]::ReparsePoint))) {
        throw 'Unexpected watcher directory'
    }
    $startup = Read-StartupCommand
    if ($null -ne $startup -and $startup -cne $command) { throw 'The Windows sign-in entry is owned by another setup' }
    $present = @($assets.Keys | Where-Object { Test-Asset (Join-Path $folder $_) $assets[$_] })
    if ($Action -ne 'Restore') {
        foreach ($name in $assets.Keys) {
            if (!(Test-Asset (Join-Path $PSScriptRoot $name) $assets[$name])) { throw "Missing reviewed file $name" }
        }
    }
    if ($Action -eq 'Check') {
        if ($null -eq $startup -and $present.Count -eq 0) { 'absent'; return }
        if ($startup -ceq $command -and $present.Count -eq $assets.Count -and (Get-WatcherProcess)) { 'ready'; return }
        'stopped'
        return
    }
    if ($Action -eq 'Restore') {
        if ($null -ne $startup) { Remove-ItemProperty -LiteralPath $runKey -Name $runName }
        $until = [DateTime]::UtcNow.AddSeconds(12)
        while (Get-WatcherProcess) {
            if ([DateTime]::UtcNow -ge $until) { throw 'Watcher has not stopped. Retry Restore original setup.' }
            Start-Sleep -Milliseconds 100
        }
        foreach ($name in $present) { Remove-Item -LiteralPath (Join-Path $folder $name) }
        'absent'
        return
    }
    if ($command.Length -gt 260) { throw 'The watcher command exceeds the Windows sign-in path limit' }
    $null = New-Item -ItemType Directory -Path $folder -Force
    foreach ($name in $assets.Keys) {
        $source = Join-Path $PSScriptRoot $name
        if ($name -in $present) { continue }
        $pending = Join-Path $folder ([guid]::NewGuid().ToString('N') + '.pending')
        try {
            [IO.File]::WriteAllBytes($pending,[IO.File]::ReadAllBytes($source))
            $null = Test-Asset $pending $assets[$name]
            [IO.File]::Move($pending,(Join-Path $folder $name))
        } finally {
            if (Test-Path -LiteralPath $pending) { Remove-Item -LiteralPath $pending }
        }
    }
    if ($null -eq $startup) {
        if (!(Test-Path -LiteralPath $runKey)) { $null = New-Item -Path $runKey -Force }
        $null = New-ItemProperty -LiteralPath $runKey -Name $runName -Value $command -PropertyType String
    }
    if (!(Get-WatcherProcess)) {
        $child = Start-Process -FilePath $powershell -ArgumentList $parameters -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $folder 'watcher-launch.out') `
            -RedirectStandardError (Join-Path $folder 'watcher-launch.err')
        try {
            $until = [DateTime]::UtcNow.AddSeconds(20)
            while (!(Get-WatcherProcess)) {
                if ($child.HasExited -or [DateTime]::UtcNow -ge $until) {
                    $diagnostic = Get-Content -LiteralPath (Join-Path $folder 'watcher-launch.err') -Raw
                    throw "Watcher did not become ready. $diagnostic"
                }
                Start-Sleep -Milliseconds 100
            }
        } finally { $child.Dispose() }
    }
    'ready'
} finally {
    if ($owned) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
