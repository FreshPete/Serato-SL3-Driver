#requires -Version 7.0
# Read-only preflight. Does not install, start services, load the helper or redirect USB.
param([ValidateSet('Debug','Release')][string]$Configuration='Release', [string]$OutputPath)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$expected=[ordered]@{
    'artifacts/packages/UsbDk_1.0.22_x64.msi'='91F6F695E1E13C656024E6D3B55620BF08D8835EF05EE0496935BA6BB62466A5'
    'artifacts/extracted/usbdk-msi/UsbDk.sys10'='C92B6C15BD550023312AE4CFE49A39757952A3C2EBDC7D1D143AC5E695F69A63'
    'artifacts/extracted/usbdk-msi/UsbDkHelper.dll10'='66BBFE6F99B417F97C7A9E97816E24AF7DDE0E01B8E535C41E91E1C6C19CFEDA'
}
$files=@()
foreach($relative in $expected.Keys){
    $path=Join-Path $root $relative
    if(-not(Test-Path -LiteralPath $path)){throw "Required reviewed artifact is missing: $relative"}
    $hash=(Get-FileHash -LiteralPath $path).Hash
    if($hash -ne $expected[$relative]){throw "Artifact differs from reviewed bytes: $relative"}
    $files+=@([ordered]@{path=$relative;sha256=$hash;bytes=(Get-Item -LiteralPath $path).Length})
}
$manifestPath=Join-Path $root "artifacts/build/native/native-build-$Configuration.json"
$build=Get-Content -LiteralPath $manifestPath -Raw|ConvertFrom-Json
foreach($entry in $build.inputs.PSObject.Properties){
    if((Get-FileHash -LiteralPath (Join-Path $root $entry.Name)).Hash -ne $entry.Value){throw "Native source/dependency changed; rebuild first: $($entry.Name)"}
}
$exe=Join-Path $root "artifacts/build/native/$Configuration/sl3_usbdk.exe"
if(-not $build.coreTestsPassed -or -not $build.usbdk.planOnlyPassed -or (Get-FileHash -LiteralPath $exe).Hash -ne $build.usbdk.executableSha256){throw 'Native UsbDk binary/build verification mismatch'}
$plan=& $exe --plan|ConvertFrom-Json
if($LASTEXITCODE -ne 0 -or -not $plan.plan_only -or $plan.helper_loaded -or $plan.driver_changes){throw 'Native plan mode failed'}
$signTool=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10/bin/10.0.19041.0/x64/signtool.exe'
if(-not(Test-Path -LiteralPath $signTool)){throw 'Reviewed SDK signature verifier is missing'}
$signatureOutput=@(& $signTool verify /ds 1 /kp /v (Join-Path $root 'artifacts/extracted/usbdk-msi/UsbDk.sys10') 2>&1)
$signatureExit=$LASTEXITCODE
if($signatureExit -ne 0){throw 'Microsoft signature index 1 failed kernel verification'}
$installed=@(Get-CimInstance -ClassName Win32_SystemDriver -Filter "Name='UsbDk'"|Select-Object Name,State,StartMode,PathName)
$device=@(Get-PnpDevice -PresentOnly|Where-Object InstanceId -like 'USB\VID_1CC5&PID_0001\*'|Select-Object Status,Class,FriendlyName,InstanceId)
$secureBoot=try{[ordered]@{known=$true;enabled=[bool](Confirm-SecureBootUEFI)}}catch{[ordered]@{known=$false;reason=$_.Exception.Message}}
$result=[ordered]@{
    utc=[datetime]::UtcNow.ToString('o');scope='Read-only dependency, source, signature and service checks'
    files=$files;configuration=$Configuration;nativeSha256=$build.usbdk.executableSha256
    signature=[ordered]@{index=1;kernelVerificationExitCode=$signatureExit}
    nativePlan=$plan;installedDriver=$installed;sl3=$device;secureBoot=$secureBoot
    helperLoaded=$false;driverInstalled=$false;deviceRedirected=$false;audioSubmissions=0
    nextGate='Owner-present traced driver load test, exact-SL3 descriptor-only enumeration, then separate bounded capture; no audio OUT'
}
$json=$result|ConvertTo-Json -Depth 8
if($OutputPath){
    if(-not[IO.Path]::IsPathRooted($OutputPath)){$OutputPath=Join-Path $root $OutputPath}
    if(Test-Path -LiteralPath $OutputPath){throw 'Choose a new preflight record; existing evidence is not overwritten'}
    $parent=Split-Path -Parent $OutputPath
    if(-not(Test-Path -LiteralPath $parent)){New-Item -ItemType Directory -Path $parent -Force|Out-Null}
    $json|Set-Content -LiteralPath $OutputPath -Encoding utf8
}
$json
