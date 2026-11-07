param([string]$Version = '0.5.0')
$ErrorActionPreference = 'Stop'
$taskBuildManifest=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'bin\build-manifest.json') -Raw | ConvertFrom-Json
if ($taskBuildManifest.acceptanceHooks) { throw 'Refusing to package an acceptance-only fault injection build. Rebuild without -AcceptanceHooks.' }
if ($taskBuildManifest.version -ne $Version -or $taskBuildManifest.sha256 -ne (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'bin\SP2BuildAssistant.dll') -Algorithm SHA256).Hash) { throw 'Build manifest/version/hash mismatch.' }
$taskDist = Join-Path $PSScriptRoot 'dist'
$taskStage = Join-Path $taskDist ('stage-' + [guid]::NewGuid().ToString('N'))
$taskFull = Join-Path $taskStage ('SP2BuildAssistant-' + $Version)
$taskSkill = Join-Path $taskStage ('SP2BuildAssistant-Skill-' + $Version)
New-Item -ItemType Directory -Path $taskFull,$taskSkill -Force | Out-Null
# Copy only user-facing documentation and the two required build outputs.
New-Item -ItemType Directory -Path (Join-Path $taskFull 'bin'),(Join-Path $taskFull 'docs'),(Join-Path $taskFull 'skills') | Out-Null
New-Item -ItemType Directory -Path (Join-Path $taskFull 'docs\zh-CN') | Out-Null
foreach ($taskItem in @('cli','knowledge','README.md','README.zh-CN.md','install.ps1','install-skill.ps1')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $taskItem) -Destination $taskFull -Recurse
}
foreach ($taskItem in @('SP2BuildAssistant.dll','build-manifest.json')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot ('bin\' + $taskItem)) -Destination (Join-Path $taskFull 'bin')
}
foreach ($taskDoc in @('Installation.md','Quickstart.md','CLI-Usage.md','Precision-Workflow.md','Designer-Screenshots.md','Visual-Usage.md','Centers-Usage.md','Release-0.5.0.md','Release-0.7.8.md','SDK-0.7.8.md')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot ('docs\' + $taskDoc)) -Destination (Join-Path $taskFull 'docs')
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot ('docs\zh-CN\' + $taskDoc)) -Destination (Join-Path $taskFull 'docs\zh-CN')
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'skills\sp2-build-assistant') -Destination (Join-Path $taskFull 'skills') -Recurse
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'skills\sp2-build-assistant') -Destination $taskSkill -Recurse -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'install-skill.ps1') -Destination $taskSkill
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'skills\README.md') -Destination (Join-Path $taskSkill 'README.md')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'skills\README.zh-CN.md') -Destination (Join-Path $taskSkill 'README.zh-CN.md')
# Python bytecode is local build output, not a release dependency.
Get-ChildItem -LiteralPath $taskStage -Directory -Recurse -Filter '__pycache__' | ForEach-Object {
    $taskResolvedCache = [System.IO.Path]::GetFullPath($_.FullName)
    if (-not $taskResolvedCache.StartsWith([System.IO.Path]::GetFullPath($taskStage) + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected cache path.' }
    Remove-Item -LiteralPath $taskResolvedCache -Recurse -Force
}
Compress-Archive -LiteralPath $taskFull -DestinationPath (Join-Path $taskDist ('SP2BuildAssistant-' + $Version + '.zip')) -Force
Compress-Archive -LiteralPath $taskSkill -DestinationPath (Join-Path $taskDist ('SP2BuildAssistant-Skill-' + $Version + '.zip')) -Force
Get-FileHash -LiteralPath (Join-Path $taskDist ('SP2BuildAssistant-' + $Version + '.zip')),(Join-Path $taskDist ('SP2BuildAssistant-Skill-' + $Version + '.zip')) -Algorithm SHA256 | Select-Object Path,Hash | ConvertTo-Json
