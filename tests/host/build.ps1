param([string]$GameDir=$env:SP2_GAME_DIR, [string]$Csc, [string]$VcTools=$env:VCToolsInstallDir)
$ErrorActionPreference='Stop'
if(-not $GameDir -or -not $VcTools){throw 'Pass -GameDir and -VcTools or use the Visual Studio developer shell.'}
if(-not $Csc){$Csc=(Get-Command csc.exe -ErrorAction Stop).Source}
$taskHostVc=$VcTools.TrimEnd('\')
$taskHostSdk='C:\Program Files (x86)\Windows Kits\10'
$taskHostSdkVersion='10.0.26100.0'
$taskHostNativeArgs=@('/nologo','/LD','/MT','/O2','/W4',('/I'+$taskHostVc+'\include'))
foreach($taskHostInclude in @('ucrt','um','shared')){
    $taskHostNativeArgs+=('/I'+(Join-Path $taskHostSdk ('Include\'+$taskHostSdkVersion+'\'+$taskHostInclude)))
}
$taskHostNativeArgs+=@((Join-Path $PSScriptRoot 'Win32HeapProbeNative.cpp'),('/Fo'+(Join-Path $PSScriptRoot 'Win32HeapProbeNative.obj')),
    '/link',('/OUT:'+(Join-Path $PSScriptRoot 'SP2HeapProbe.dll')),('/IMPLIB:'+(Join-Path $PSScriptRoot 'SP2HeapProbe.lib')),
    ('/LIBPATH:'+$taskHostVc+'\lib\x64'),('/LIBPATH:'+(Join-Path $taskHostSdk ('Lib\'+$taskHostSdkVersion+'\ucrt\x64'))),
    ('/LIBPATH:'+(Join-Path $taskHostSdk ('Lib\'+$taskHostSdkVersion+'\um\x64'))))
& (Join-Path $taskHostVc 'bin\Hostx64\x64\cl.exe') @taskHostNativeArgs
if($LASTEXITCODE -ne 0){throw 'Native heap diagnostic helper compilation failed.'}
$taskHostManaged=Join-Path $GameDir 'SimplePlanes 2_Data/Managed'
$taskHostRefs=@('mscorlib','netstandard','System','System.Core','System.Xml','System.Xml.Linq','Newtonsoft.Json','Game','UnityEngine','UnityEngine.CoreModule','Jundroo.Common','Jundroo.Packages') | ForEach-Object { Join-Path $taskHostManaged ($_.ToString()+'.dll') }
$taskHostRefs+=Join-Path $GameDir 'BepInEx/core/BepInEx.dll'
$taskHostRefs+=Join-Path $GameDir 'BepInEx/core/0Harmony.dll'
$taskHostRefs+=@('Unity.Collections','Unity.Mathematics') | ForEach-Object {Join-Path $taskHostManaged ($_.ToString()+'.dll')}
$taskHostArgs=@('/nologo','/target:library','/optimize+','/deterministic+','/langversion:7.3','/nostdlib+',('/out:'+(Join-Path $PSScriptRoot 'SP2AcceptanceHost.dll')))
$taskHostArgs+=$taskHostRefs | ForEach-Object { '/reference:'+$_ }
$taskHostArgs+=Join-Path $PSScriptRoot 'AcceptanceHost.cs'
$taskHostArgs+=Join-Path $PSScriptRoot 'Win32HeapProbe.cs'
$taskHostArgs+=Join-Path $PSScriptRoot 'MeshLifetimeReference.cs'
$taskHostArgs+=Join-Path $PSScriptRoot 'ExpressionTemplateReference.cs'
& $Csc @taskHostArgs
if($LASTEXITCODE -ne 0){throw 'Acceptance host compilation failed.'}
