param(
    [string]$GameDir = $env:SP2_GAME_DIR,
    # A packaged agent host can redirect LocalAppData writes into its private
    # LocalCache. USERPROFILE keeps the installed CLI visible to other agents.
    [string]$InstallDir = "$env:USERPROFILE\.sp2build\app",
    [string]$Python,
    [switch]$InstallSkill
)
$ErrorActionPreference = 'Stop'
if (-not $GameDir) { throw 'Pass -GameDir with the directory containing SimplePlanes 2.exe.' }
$taskSourceRoot = $PSScriptRoot
if (-not $Python) {
    $taskPyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($taskPyLauncher) { $Python = (& $taskPyLauncher.Source -3 -c 'import sys; print(sys.executable)').Trim() }
    else { $Python = (Get-Command python.exe -ErrorAction Stop).Source }
}
& $Python -c 'import sys; assert sys.version_info >= (3,10)'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.10+ is required.' }
$taskDllSource = Join-Path $taskSourceRoot 'bin\SP2BuildAssistant.dll'
$taskDllTarget = Join-Path $GameDir 'BepInEx\plugins\SP2BuildAssistant.dll'
if (-not (Test-Path -LiteralPath (Join-Path $GameDir 'BepInEx\core\BepInEx.dll'))) { throw 'BepInEx 5 must be installed in the Mono game directory.' }
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
foreach ($taskDirectory in @('cli','skills','knowledge')) {
    $taskSourceDirectory = Join-Path $taskSourceRoot $taskDirectory
    if (Test-Path -LiteralPath $taskSourceDirectory) { Copy-Item -LiteralPath $taskSourceDirectory -Destination $InstallDir -Recurse -Force }
}
$taskDllAlreadyCurrent = (Test-Path -LiteralPath $taskDllTarget) -and ((Get-FileHash -LiteralPath $taskDllSource).Hash -eq (Get-FileHash -LiteralPath $taskDllTarget).Hash)
if (-not $taskDllAlreadyCurrent) {
    try { Copy-Item -LiteralPath $taskDllSource -Destination $taskDllTarget -Force }
    catch {
        # Windows can keep the loaded DLL mapped. Rename that exact plugin to a
        # non-DLL extension, then install the new file for the next game launch.
        $taskPreviousDll = $taskDllTarget + '.' + [guid]::NewGuid().ToString('N') + '.previous'
        Move-Item -LiteralPath $taskDllTarget -Destination $taskPreviousDll -ErrorAction Stop
        try { Copy-Item -LiteralPath $taskDllSource -Destination $taskDllTarget -Force }
        catch { Move-Item -LiteralPath $taskPreviousDll -Destination $taskDllTarget; throw }
        Write-Host 'A loaded DLL was preserved with a .previous extension. Restart the game to load the new version.'
    }
}
$taskBin = Join-Path (Split-Path -Parent $InstallDir) 'bin'
New-Item -ItemType Directory -Path $taskBin -Force | Out-Null
$taskCliPath = Join-Path $InstallDir 'cli\sp2build.py'
$taskLauncher = '@echo off' + "`r`n" + '"' + $Python + '" "' + $taskCliPath + '" %*' + "`r`n" + 'exit /b %errorlevel%' + "`r`n"
[System.IO.File]::WriteAllText((Join-Path $taskBin 'sp2build.cmd'), $taskLauncher, [System.Text.UTF8Encoding]::new($false))
$taskUserPath = [Environment]::GetEnvironmentVariable('Path','User')
if (@($taskUserPath -split ';' | Where-Object { $_.TrimEnd('\') -ieq $taskBin.TrimEnd('\') }).Count -eq 0) {
    [Environment]::SetEnvironmentVariable('Path', ($taskBin + ';' + $taskUserPath.TrimEnd(';')), 'User')
}
$env:Path = $taskBin + ';' + $env:Path
if ($InstallSkill) {
    $taskSkillTarget = Join-Path $env:USERPROFILE '.agents\skills\sp2-build-assistant'
    New-Item -ItemType Directory -Path (Split-Path -Parent $taskSkillTarget) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $taskSourceRoot 'skills\sp2-build-assistant') -Destination (Split-Path -Parent $taskSkillTarget) -Recurse -Force
}
$taskBuiltHash = (Get-FileHash -LiteralPath $taskDllSource -Algorithm SHA256).Hash
$taskInstalledHash = (Get-FileHash -LiteralPath $taskDllTarget -Algorithm SHA256).Hash
if ($taskBuiltHash -ne $taskInstalledHash) { throw 'DLL hash mismatch after deployment.' }
[pscustomobject]@{ Cli = Join-Path $taskBin 'sp2build.cmd'; UserPathRegistered = $true; Python=$Python; DLL=$taskDllTarget; SHA256=$taskInstalledHash; SkillInstalled=[bool]$InstallSkill } | ConvertTo-Json
& (Join-Path $taskBin 'sp2build.cmd') version --json
