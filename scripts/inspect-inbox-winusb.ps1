param( [string]$Output = 'tests/results/local/winusb-selection.json')
# Read-only global SetupAPI driver-node enumeration for the inbox WinUSB INF.
# Presence here does not establish applicability to the SL3 hardware ID.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$device = @(Get-PnpDevice -PresentOnly | Where-Object InstanceId -like 'USB\VID_1CC5&PID_0001\*')
if ($device.Count -ne 1) { throw 'Exactly one connected SL3 is required.' }
$originalInf = (Get-PnpDeviceProperty -InstanceId $device[0].InstanceId -KeyName DEVPKEY_Device_DriverInfPath).Data
$sys = Join-Path $env:SystemRoot 'System32/drivers/winusb.sys'
if ((Get-AuthenticodeSignature -LiteralPath $sys).Status -ne 'Valid') { throw 'Inbox WinUSB signature did not validate.' }
Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
public static class Sl3InboxSelection {
 [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] public struct Params {
  public uint cbSize, Flags, FlagsEx; public IntPtr hwnd, handler, context, queue;
  public UIntPtr classReserved; public uint reserved;
  [MarshalAs(UnmanagedType.ByValTStr,SizeConst=260)] public string DriverPath;
 }
 [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] public struct Driver {
  public uint cbSize, DriverType; public UIntPtr Reserved;
  [MarshalAs(UnmanagedType.ByValTStr,SizeConst=256)] public string Description;
  [MarshalAs(UnmanagedType.ByValTStr,SizeConst=256)] public string MfgName;
  [MarshalAs(UnmanagedType.ByValTStr,SizeConst=256)] public string ProviderName;
  public System.Runtime.InteropServices.ComTypes.FILETIME DriverDate; public ulong DriverVersion;
 }
 [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] public struct Detail {
  public uint cbSize; public System.Runtime.InteropServices.ComTypes.FILETIME InfDate;
  public uint CompatIDsOffset, CompatIDsLength; public UIntPtr Reserved;
  [MarshalAs(UnmanagedType.ByValTStr,SizeConst=256)] public string SectionName;
  [MarshalAs(UnmanagedType.ByValTStr,SizeConst=260)] public string InfFileName;
  [MarshalAs(UnmanagedType.ByValTStr,SizeConst=256)] public string DrvDescription;
  [MarshalAs(UnmanagedType.ByValTStr,SizeConst=1)] public string HardwareID;
 }
 [DllImport("setupapi.dll",SetLastError=true)] static extern IntPtr SetupDiCreateDeviceInfoList(IntPtr g,IntPtr h);
 [DllImport("setupapi.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool SetupDiSetDeviceInstallParamsW(IntPtr s,IntPtr d,ref Params p);
 [DllImport("setupapi.dll",SetLastError=true)] static extern bool SetupDiBuildDriverInfoList(IntPtr s,IntPtr d,uint type);
 [DllImport("setupapi.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool SetupDiEnumDriverInfoW(IntPtr s,IntPtr d,uint t,uint n,ref Driver r);
 [DllImport("setupapi.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool SetupDiGetDriverInfoDetailW(IntPtr s,IntPtr d,ref Driver r,IntPtr b,uint size,out uint needed);
 [DllImport("setupapi.dll",SetLastError=true)] static extern bool SetupDiDestroyDeviceInfoList(IntPtr s);
 public static object Run(string inf) {
  IntPtr set=SetupDiCreateDeviceInfoList(IntPtr.Zero,IntPtr.Zero);
  if(set==new IntPtr(-1)) throw new Win32Exception();
  try {
   Params p=new Params { cbSize=(uint)Marshal.SizeOf<Params>(), Flags=0x10000, FlagsEx=0x800, DriverPath=inf };
   if(!SetupDiSetDeviceInstallParamsW(set,IntPtr.Zero,ref p)) throw new Win32Exception();
   if(!SetupDiBuildDriverInfoList(set,IntPtr.Zero,1)) throw new Win32Exception();
   for(uint n=0;;n++) {
    Driver r=new Driver {cbSize=(uint)Marshal.SizeOf<Driver>()};
    if(!SetupDiEnumDriverInfoW(set,IntPtr.Zero,1,n,ref r)) {
     int error=Marshal.GetLastWin32Error(); if(error==259) break; throw new Win32Exception(error);
    }
    IntPtr buffer=Marshal.AllocHGlobal(65536); Detail detail;
    try {
     Marshal.WriteInt32(buffer,Marshal.SizeOf<Detail>());
     uint needed;
     if(!SetupDiGetDriverInfoDetailW(set,IntPtr.Zero,ref r,buffer,65536,out needed)) throw new Win32Exception();
     detail=Marshal.PtrToStructure<Detail>(buffer);
    } finally {Marshal.FreeHGlobal(buffer);}
    if(!String.Equals(detail.SectionName,"WINUSB",StringComparison.OrdinalIgnoreCase)) continue;
    if(!String.Equals(detail.InfFileName,inf,StringComparison.OrdinalIgnoreCase)) throw new Exception("Unexpected INF path.");
    return new {r.Description,r.ProviderName,detail.InfFileName,detail.SectionName,bound=false};
   }
   throw new Exception("Exact inbox WINUSB section not found.");
  } finally {SetupDiDestroyDeviceInfoList(set);}
 }
}
'@
$result = [Sl3InboxSelection]::Run((Join-Path $env:SystemRoot 'INF/winusb.inf'))
$record = [ordered]@{utc=[DateTime]::UtcNow.ToString('o'); previousInf=$originalInf; winusbSha256=(Get-FileHash -LiteralPath $sys).Hash; result=$result}
New-Item -ItemType Directory -Force -Path (Split-Path $Output) | Out-Null
$record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Output -Encoding utf8
$record | ConvertTo-Json -Depth 5
