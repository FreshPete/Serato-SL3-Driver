# Read-only process/token queries. No token duplication, privilege change or launch.
if(-not ('Sl3ProcessInspector' -as [type])){
Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
public sealed class Sl3ProcessEvidence {
 public uint pid; public string creationFileTimeUtc, imagePath;
 public bool alive, tokenQueried; public bool? elevated; public int? elevationType;
}
public static class Sl3ProcessInspector {
 [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr OpenProcess(uint rights,bool inherit,uint pid);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool CloseHandle(IntPtr h);
 [DllImport("kernel32.dll",SetLastError=true)] static extern uint WaitForSingleObject(IntPtr h,uint milliseconds);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetProcessTimes(IntPtr h,out long created,out long exited,out long kernel,out long user);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool QueryFullProcessImageName(IntPtr h,uint flags,StringBuilder path,ref uint size);
 [DllImport("advapi32.dll",SetLastError=true)] static extern bool OpenProcessToken(IntPtr process,uint access,out IntPtr token);
 [DllImport("advapi32.dll",SetLastError=true)] static extern bool GetTokenInformation(IntPtr token,int kind,out int value,int bytes,out int needed);
 static void Check(bool ok){if(!ok)throw new Win32Exception(Marshal.GetLastWin32Error());}
 public static Sl3ProcessEvidence Inspect(uint pid,bool withToken){
  IntPtr process=OpenProcess(0x101000,false,pid);if(process==IntPtr.Zero)throw new Win32Exception(Marshal.GetLastWin32Error());
  try {
   long created,exited,kernel,user;
   Check(GetProcessTimes(process,out created,out exited,out kernel,out user));
   uint wait=WaitForSingleObject(process,0);Check(wait==0 || wait==0x102);
   var result=new Sl3ProcessEvidence{pid=pid,creationFileTimeUtc=created.ToString(),alive=wait==0x102};
   if(!result.alive)return result;
   var path=new StringBuilder(32768);uint size=32768;Check(QueryFullProcessImageName(process,0,path,ref size));
   result.imagePath=path.ToString();result.tokenQueried=withToken;
   if(withToken){IntPtr token;Check(OpenProcessToken(process,8,out token));try {
     int elevation,kind,needed;Check(GetTokenInformation(token,20,out elevation,4,out needed));
     Check(GetTokenInformation(token,18,out kind,4,out needed));result.elevated=elevation!=0;result.elevationType=kind;
    }finally{CloseHandle(token);}}
   return result;
  }finally{CloseHandle(process);}
 }
}
'@
}
function Get-Sl3ProcessEvidence {
    param([Parameter(Mandatory)][uint32]$ProcessId,[switch]$WithToken)
    [Sl3ProcessInspector]::Inspect($ProcessId,[bool]$WithToken)
}
Export-ModuleMember -Function Get-Sl3ProcessEvidence
