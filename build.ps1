param(
    [string]$GameDir = 'D:\apps\steam\steamapps\common\SimplePlanes 2',
    [string]$Csc = 'D:\apps\visualStudio\MSBuild\Current\bin\Roslyn\csc.exe',
    [switch]$AcceptanceHooks
)
$ErrorActionPreference = 'Stop'
$taskProjectDir = $PSScriptRoot
$taskManaged = Join-Path $GameDir 'SimplePlanes 2_Data\Managed'
$taskOutput = Join-Path $taskProjectDir 'bin\SP2BuildAssistant.dll'
$taskReferences = @('mscorlib.dll','netstandard.dll','System.dll','System.Core.dll','System.Runtime.dll','System.Xml.dll','System.Xml.Linq.dll','Newtonsoft.Json.dll','Game.dll','UnityEngine.dll','UnityEngine.CoreModule.dll','UnityEngine.PhysicsModule.dll','Unity.Mathematics.dll','Unity.Collections.dll','UnityEngine.UI.dll','UniTask.dll','Jundroo.Common.dll') | ForEach-Object { Join-Path $taskManaged $_ }
$taskReferences += Join-Path $GameDir 'BepInEx\core\BepInEx.dll'
$taskReferences += Join-Path $taskManaged 'UnityEngine.ImageConversionModule.dll'
$taskReferences += Join-Path $taskManaged 'Unity.TextMeshPro.dll'
$taskReferences += Join-Path $taskManaged 'Jundroo.Packages.dll'
$taskReferences += Join-Path $GameDir 'BepInEx\core\0Harmony.dll'
foreach ($taskReference in $taskReferences) { if (-not (Test-Path -LiteralPath $taskReference -PathType Leaf)) { throw "Missing assembly: $taskReference" } }
New-Item -ItemType Directory -Path (Split-Path -Parent $taskOutput) -Force | Out-Null
$taskCompilerArguments = @('/nologo','/target:library','/optimize+','/deterministic+','/langversion:7.3','/nostdlib+',"/out:$taskOutput")
if ($AcceptanceHooks) { $taskCompilerArguments += '/define:ACCEPTANCE_HOOKS'; Write-Warning 'Acceptance-only fault hooks enabled. Do not package this DLL.' }
$taskCompilerArguments += $taskReferences | ForEach-Object { "/reference:$_" }
$taskCompilerArguments += (Get-ChildItem -LiteralPath (Join-Path $taskProjectDir 'bridge') -Filter '*.cs').FullName
& $Csc @taskCompilerArguments
if ($LASTEXITCODE -ne 0) { throw "DLL compilation failed: $LASTEXITCODE" }
[pscustomobject]@{version='0.5.0';acceptanceHooks=[bool]$AcceptanceHooks;sha256=(Get-FileHash -LiteralPath $taskOutput -Algorithm SHA256).Hash} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskProjectDir 'bin\build-manifest.json') -Encoding utf8
Get-FileHash -LiteralPath $taskOutput -Algorithm SHA256 | Format-List
