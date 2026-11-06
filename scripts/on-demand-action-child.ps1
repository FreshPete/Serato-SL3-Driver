# Bounded reviewed helper entry. An inherited duplicate keeps the same lock file
# alive if the coordinating Python process is terminated during archive work.
#requires -Version 7.5
param(
    [Parameter(Mandatory)][ValidateSet('Plan','Install','Rollback','Clean')][string]$Action,
    [Parameter(Mandatory)][ValidateRange(1,9223372036854775807)][long]$ActionLockHandle
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$actionHandle=[Microsoft.Win32.SafeHandles.SafeFileHandle]::new([IntPtr]::new($ActionLockHandle),$true)
$actionStream=$null
try {
    $actionStream=[IO.FileStream]::new($actionHandle,[IO.FileAccess]::ReadWrite)
    if($actionStream.Length -le 0 -or $actionStream.Length -gt 4096){throw 'Bounded inherited action lock required'}
    Add-Type -Namespace SL3.Rebuild -Name ActionLockNative -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError=true)]
[return: System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.Bool)]
public static extern bool SetHandleInformation(System.IntPtr handle, uint mask, uint flags);
'@
    if(-not [SL3.Rebuild.ActionLockNative]::SetHandleInformation($actionHandle.DangerousGetHandle(),1,0)){
        throw 'Could not make the received lock handle non-inheritable'
    }
    & (Join-Path $PSScriptRoot 'archive-test.ps1') -Action $Action
} finally {
    if($null -ne $actionStream){$actionStream.Dispose()}else{$actionHandle.Dispose()}
}
