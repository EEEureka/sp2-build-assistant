param([string]$Name='dev17-headless-a',
      [string]$GameDir='D:\apps\steam\steamapps\common\SimplePlanes 2',
      [string]$BridgeDll)
$ErrorActionPreference='Stop'
if($Name -notmatch '^[a-zA-Z0-9-]+$'){throw 'Use a simple run name.'}
$taskHostProject=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if(-not $BridgeDll){$BridgeDll=Join-Path $taskHostProject 'bin/SP2BuildAssistant.dll'}
$taskRunningGames=@(Get-Process -Name 'SimplePlanes 2' -ErrorAction SilentlyContinue | Where-Object { $_.Path })
if($taskRunningGames.Count){throw 'A live game process is still running. Finish its native shutdown and confirm exit before starting another GPU acceptance process.'}
$taskHostRoot=Join-Path $taskHostProject ('tests/artifacts/precision-0.5.0/'+$Name)
if(Test-Path -LiteralPath $taskHostRoot){throw 'A fresh run directory is required.'}
$taskHostRuntime=Join-Path $taskHostRoot 'runtime'
New-Item -ItemType Directory -Path $taskHostRuntime -Force | Out-Null
foreach($taskHostFile in @('SimplePlanes 2.exe','UnityPlayer.dll','winhttp.dll','doorstop_config.ini')){
    Copy-Item -LiteralPath (Join-Path $GameDir $taskHostFile) -Destination $taskHostRuntime
}
foreach($taskHostDir in @('SimplePlanes 2_Data','MonoBleedingEdge','D3D12')){
    New-Item -ItemType Junction -Path (Join-Path $taskHostRuntime $taskHostDir) -Target (Join-Path $GameDir $taskHostDir) | Out-Null
}
New-Item -ItemType Directory -Path (Join-Path $taskHostRuntime 'BepInEx/plugins') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $taskHostRuntime 'BepInEx/config') -Force | Out-Null
New-Item -ItemType Junction -Path (Join-Path $taskHostRuntime 'BepInEx/core') -Target (Join-Path $GameDir 'BepInEx/core') | Out-Null
Copy-Item -LiteralPath (Join-Path $GameDir 'BepInEx/config/BepInEx.cfg') -Destination (Join-Path $taskHostRuntime 'BepInEx/config')
Copy-Item -LiteralPath $BridgeDll -Destination (Join-Path $taskHostRuntime 'BepInEx/plugins/SP2BuildAssistant.dll')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'SP2AcceptanceHost.dll') -Destination (Join-Path $taskHostRuntime 'BepInEx/plugins')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'SP2HeapProbe.dll') -Destination $taskHostRuntime
$taskHostCraftRoot=Join-Path $env:USERPROFILE 'AppData/LocalLow/Jundroo/SimplePlanes 2/Crafts'
Get-ChildItem -LiteralPath $taskHostCraftRoot -File -Recurse | Get-FileHash | Select-Object Path,Hash | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $taskHostRoot 'craft-hashes-before.json')
$taskHostChannel=Join-Path $taskHostRoot 'channel'
$env:SP2BUILD_TEST_HOST=$taskHostChannel
$env:SP2BUILD_TEST_TOKEN=[guid]::NewGuid().ToString('N')+[guid]::NewGuid().ToString('N')
try{
    $taskHostArgs='-batchmode -screen-width 1280 -screen-height 720 -logFile "'+(Join-Path $taskHostRoot 'player.log')+'"'
    $taskHostProcess=Start-Process -FilePath (Join-Path $taskHostRuntime 'SimplePlanes 2.exe') -ArgumentList $taskHostArgs -WorkingDirectory $taskHostRuntime -WindowStyle Hidden -PassThru
}finally{Remove-Item Env:SP2BUILD_TEST_HOST;Remove-Item Env:SP2BUILD_TEST_TOKEN}
$taskHostManifest=[pscustomobject]@{pid=$taskHostProcess.Id;host=$taskHostChannel;runtime=$taskHostRuntime;batchMode=$true;bridgeSha256=(Get-FileHash -LiteralPath $BridgeDll).Hash;hostSha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'SP2AcceptanceHost.dll')).Hash;heapProbeSha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'SP2HeapProbe.dll')).Hash}
$taskHostManifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskHostRoot 'launch.json')
$taskHostManifest | ConvertTo-Json
