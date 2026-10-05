param([string]$SkillRoot = "$env:USERPROFILE\.agents\skills")
$ErrorActionPreference = 'Stop'
$taskSkillSource = Join-Path $PSScriptRoot 'sp2-build-assistant'
if (-not (Test-Path -LiteralPath $taskSkillSource)) {
    $taskSkillSource = Join-Path $PSScriptRoot 'skills\sp2-build-assistant'
}
if (-not (Test-Path -LiteralPath (Join-Path $taskSkillSource 'SKILL.md'))) { throw 'SKILL.md is missing from this package.' }
New-Item -ItemType Directory -Path $SkillRoot -Force | Out-Null
Copy-Item -LiteralPath $taskSkillSource -Destination $SkillRoot -Recurse -Force
[pscustomobject]@{ Skill = Join-Path $SkillRoot 'sp2-build-assistant'; Requires = 'Local Windows sp2build CLI and game DLL' } | ConvertTo-Json
