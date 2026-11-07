param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
$app = 'C:\Program Files\Serato\Serato DJ Pro\Serato DJ Pro.exe'
$helper = Join-Path $PSScriptRoot 'sl3-notice-startup-early.dll'
$pins = @{
    $app = '66E7AF01DDFD151814F51BF44BD8472E5C94F54B3CE12119EF70B7CBAB433265'
    $helper = 'A370AB23C5C1ED80A35B8B49046C92EC270F2BB5CB43D058F72C5EA67A3B8306'
}
foreach ($item in $pins.GetEnumerator()) {
    if ((Get-FileHash -LiteralPath $item.Key).Hash -ne $item.Value) {
        throw "The reviewed image changed: $($item.Key)"
    }
}

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class Sl3NoticeTrial {
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern IntPtr LoadLibrary(string file);
    [DllImport("kernel32.dll", CharSet=CharSet.Ansi, ExactSpelling=true, SetLastError=true)]
    public static extern IntPtr GetProcAddress(IntPtr module, string name);
    [DllImport("kernel32.dll")]
    public static extern bool FreeLibrary(IntPtr module);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode)]
    public static extern IntPtr GetModuleHandle(string name);
    [DllImport("kernel32.dll", EntryPoint="GetModuleHandleExW", SetLastError=true)]
    public static extern bool GetOwner(uint flags, IntPtr address, out IntPtr module);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern IntPtr OpenProcess(uint access, bool inherit, uint pid);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern IntPtr VirtualAllocEx(IntPtr process, IntPtr address, UIntPtr size, uint flags, uint protect);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool VirtualFreeEx(IntPtr process, IntPtr address, UIntPtr size, uint flags);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool WriteProcessMemory(IntPtr process, IntPtr address, byte[] data, UIntPtr size, out UIntPtr written);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern IntPtr CreateRemoteThread(IntPtr process, IntPtr attributes, UIntPtr stack, IntPtr start, IntPtr arg, uint flags, IntPtr id);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern uint WaitForSingleObject(IntPtr handle, uint timeout);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool GetExitCodeThread(IntPtr handle, out uint code);
    [DllImport("kernel32.dll")]
    public static extern bool CloseHandle(IntPtr handle);
    [DllImport("user32.dll", EntryPoint="SetWindowsHookExW", SetLastError=true)]
    public static extern IntPtr SetHook(int type, IntPtr callback, IntPtr module, uint thread);
    [DllImport("user32.dll", SetLastError=true)]
    public static extern bool UnhookWindowsHookEx(IntPtr hook);
    [DllImport("user32.dll", EntryPoint="PostThreadMessageW", SetLastError=true)]
    public static extern bool PostThreadMessage(uint thread, uint message, UIntPtr wparam, IntPtr lparam);
}
'@

function Start-EarlyObserver($process, [IntPtr]$module, [IntPtr]$early) {
    $nullPointer = [IntPtr]::Zero
    $loader = [Sl3NoticeTrial]::GetProcAddress([Sl3NoticeTrial]::GetModuleHandle('kernel32.dll'), 'LoadLibraryW')
    $owner = $nullPointer
    if ($loader -eq $nullPointer -or ![Sl3NoticeTrial]::GetOwner(6, $loader, [ref]$owner)) {
        throw 'The Windows loader entry could not be identified'
    }
    $localLoaderModule = (Get-Process -Id $PID).Modules | Where-Object BaseAddress -EQ $owner | Select-Object -First 1
    if (!$localLoaderModule) { throw 'The Windows loader module was not found' }
    $until = [DateTime]::UtcNow.AddSeconds(3)
    do {
        $process.Refresh()
        $remoteLoaderModule = $process.Modules | Where-Object FileName -EQ $localLoaderModule.FileName | Select-Object -First 1
        if ($remoteLoaderModule) { break }
        Start-Sleep -Milliseconds 20
    } while (!$process.HasExited -and [DateTime]::UtcNow -lt $until)
    if (!$remoteLoaderModule) { throw 'Serato did not load the expected Windows loader module' }
    $remoteLoader = [IntPtr]($remoteLoaderModule.BaseAddress.ToInt64() + $loader.ToInt64() - $owner.ToInt64())
    $target = [Sl3NoticeTrial]::OpenProcess(0x10043a, $false, [uint32]$process.Id)
    if ($target -eq $nullPointer) { throw 'Windows refused access to the Serato trial process' }
    $memory = $nullPointer
    $loadThread = $nullPointer
    $observeThread = $nullPointer
    $loaderRunning = $false
    try {
        $data = [Text.Encoding]::Unicode.GetBytes($helper + [char]0)
        $length = [UIntPtr]::new([uint64]$data.Length)
        $memory = [Sl3NoticeTrial]::VirtualAllocEx($target, $nullPointer, $length, 0x3000, 4)
        $written = [UIntPtr]::Zero
        if ($memory -eq $nullPointer -or ![Sl3NoticeTrial]::WriteProcessMemory($target, $memory, $data, $length, [ref]$written) -or $written -ne $length) {
            throw 'The Serato helper path could not be passed to the Windows loader'
        }
        $loadThread = [Sl3NoticeTrial]::CreateRemoteThread($target, $nullPointer, [UIntPtr]::Zero, $remoteLoader, $memory, 0, $nullPointer)
        if ($loadThread -eq $nullPointer) { throw 'Windows declined to load the helper into Serato' }
        $loaderRunning = $true
        if ([Sl3NoticeTrial]::WaitForSingleObject($loadThread, 5000) -ne 0) { throw 'The Windows loader did not complete in five seconds' }
        $loaderRunning = $false
        $process.Refresh()
        $remoteHelper = $process.Modules | Where-Object FileName -EQ $helper | Select-Object -First 1
        if (!$remoteHelper) { throw 'Windows did not load the reviewed helper into Serato' }
        $remoteEarly = [IntPtr]($remoteHelper.BaseAddress.ToInt64() + $early.ToInt64() - $module.ToInt64())
        $observeThread = [Sl3NoticeTrial]::CreateRemoteThread($target, $nullPointer, [UIntPtr]::Zero, $remoteEarly, $nullPointer, 0, $nullPointer)
        [uint32]$exitCode = 0
        if ($observeThread -eq $nullPointer -or [Sl3NoticeTrial]::WaitForSingleObject($observeThread, 5000) -ne 0 -or
            ![Sl3NoticeTrial]::GetExitCodeThread($observeThread, [ref]$exitCode) -or $exitCode -ne 0) {
            throw "The Serato notice observer could not arm (exit $exitCode)"
        }
    } finally {
        if (!$loaderRunning -and $memory -ne $nullPointer) {
            [void][Sl3NoticeTrial]::VirtualFreeEx($target, $memory, [UIntPtr]::Zero, 0x8000)
        }
        if ($loadThread -ne $nullPointer) { [void][Sl3NoticeTrial]::CloseHandle($loadThread) }
        if ($observeThread -ne $nullPointer) { [void][Sl3NoticeTrial]::CloseHandle($observeThread) }
        [void][Sl3NoticeTrial]::CloseHandle($target)
    }
}

$lease = [IO.File]::Open($helper, 'Open', 'Read', 'Read')
$module = [IntPtr]::Zero
try {
    if ((Get-FileHash -InputStream $lease).Hash -ne $pins[$helper]) { throw 'Helper changed before load' }
    $module = [Sl3NoticeTrial]::LoadLibrary($helper)
    if ($module -eq [IntPtr]::Zero) { throw 'Windows could not load the trial helper' }
    $callback = [Sl3NoticeTrial]::GetProcAddress($module, 'Sl3GetMessage')
    $early = [Sl3NoticeTrial]::GetProcAddress($module, 'Sl3ObserveEarly')
    if ($callback -eq [IntPtr]::Zero -or $early -eq [IntPtr]::Zero) { throw 'The trial helper export is missing' }
    if ($CheckOnly) { 'helper_export_verified'; return }

    if (Get-Process -Name 'Serato DJ Pro' -ErrorAction SilentlyContinue) { throw 'Close Serato before arming the watcher' }
    if (!(Test-Path -LiteralPath 'C:/Program Files/SL3 Rebuild/on-demand-diagnostic-v1/sl3-asio.conf') -or
        !(Test-Path -LiteralPath 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\ASIO\SL3 Rebuild Development')) {
        throw 'The trial package must be installed before arming the watcher'
    }
    'notice_watcher_armed'
    $end = [DateTime]::UtcNow.AddMinutes(7)
    $seen = [Collections.Generic.HashSet[string]]::new()
    while ($seen.Count -lt 2 -and [DateTime]::UtcNow -lt $end) {
        $processes = @(Get-Process -Name 'Serato DJ Pro' -ErrorAction SilentlyContinue)
        if ($processes.Count -gt 1) { throw 'More than one Serato process' }
        if ($processes.Count -eq 0) { Start-Sleep -Milliseconds 40; continue }
        $process = $processes[0]
        try {
            if ($process.Path -ne $app -or $process.SessionId -ne (Get-Process -Id $PID).SessionId) {
                throw 'Unexpected application path or Windows session'
            }
            $identity = "$($process.Id)-$($process.StartTime.ToUniversalTime().ToFileTimeUtc())"
            if ($seen.Contains($identity)) { Start-Sleep -Milliseconds 100; continue }
            $main = @($process.Threads | Sort-Object StartTime)[0]
        } catch [System.ComponentModel.Win32Exception] {
            Start-Sleep -Milliseconds 40
            continue
        }
        if (!$main) { Start-Sleep -Milliseconds 40; continue }
        $thread = [uint32]$main.Id
        Start-EarlyObserver $process $module $early
        "notice_watcher_observing=$identity"
        $hook = [Sl3NoticeTrial]::SetHook(3, $callback, $module, $thread)
        if ($hook -eq [IntPtr]::Zero) {
            $errorCode = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
            if ($process.HasExited) { continue }
            throw "Windows declined the Serato thread hook (error $errorCode)"
        }
        [void]$seen.Add($identity)
        "notice_watcher_hooked=$identity thread=$thread"
        try {
            $log = Join-Path $PSScriptRoot "notice-hook-$($process.Id).log"
            $until = [DateTime]::UtcNow.AddSeconds(20)
            while (!$process.HasExited -and [DateTime]::UtcNow -lt $until) {
                [void][Sl3NoticeTrial]::PostThreadMessage($thread, 0, [UIntPtr]::Zero, [IntPtr]::Zero)
                if ((Test-Path -LiteralPath $log) -and
                    (Select-String -LiteralPath $log -SimpleMatch 'selection_ui_timer_armed' -Quiet)) { break }
                Start-Sleep -Milliseconds 100
            }
        } finally {
            if (![Sl3NoticeTrial]::UnhookWindowsHookEx($hook) -and !$process.HasExited) {
                throw 'Windows did not retire the Serato thread hook'
            }
        }
    }
    "notice_watcher_finished launches=$($seen.Count)"
} finally {
    if ($module -ne [IntPtr]::Zero) { [void][Sl3NoticeTrial]::FreeLibrary($module) }
    $lease.Dispose()
}
