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
# Allowlist excludes game assemblies, test snapshots, logs and instance tokens.
foreach ($taskItem in @('bin','cli','skills','knowledge','docs','README.md','install.ps1','install-skill.ps1','Verification.md')) {
    $taskSource = Join-Path $PSScriptRoot $taskItem
    if (Test-Path -LiteralPath $taskSource) { Copy-Item -LiteralPath $taskSource -Destination $taskFull -Recurse -Force }
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'skills\sp2-build-assistant') -Destination $taskSkill -Recurse -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'install-skill.ps1') -Destination $taskSkill
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'README.md') -Destination $taskSkill
# Python bytecode is local build output, not a release dependency.
Get-ChildItem -LiteralPath $taskStage -Directory -Recurse -Filter '__pycache__' | ForEach-Object {
    $taskResolvedCache = [System.IO.Path]::GetFullPath($_.FullName)
    if (-not $taskResolvedCache.StartsWith([System.IO.Path]::GetFullPath($taskStage) + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected cache path.' }
    Remove-Item -LiteralPath $taskResolvedCache -Recurse -Force
}
Compress-Archive -LiteralPath $taskFull -DestinationPath (Join-Path $taskDist ('SP2BuildAssistant-' + $Version + '.zip')) -Force
Compress-Archive -LiteralPath $taskSkill -DestinationPath (Join-Path $taskDist ('SP2BuildAssistant-Skill-' + $Version + '.zip')) -Force
Get-FileHash -LiteralPath (Join-Path $taskDist ('SP2BuildAssistant-' + $Version + '.zip')),(Join-Path $taskDist ('SP2BuildAssistant-Skill-' + $Version + '.zip')) -Algorithm SHA256 | Select-Object Path,Hash | ConvertTo-Json
