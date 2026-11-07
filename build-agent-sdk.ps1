param(
    [string]$Python,
    [string]$GameDir = $env:SP2_GAME_DIR,
    [string]$Csc,
    [string]$PackageName,
    [string]$WorkerWheelhouse=(Join-Path $env:USERPROFILE '.sp2build\workers\wheelhouse\1.0.0-cp312-win_amd64')
)
$ErrorActionPreference='Stop'
if(-not $Python){$Python=(Get-Command python.exe -ErrorAction Stop).Source}
if(-not (Test-Path -LiteralPath $Python -PathType Leaf)){throw 'Create an isolated Python environment first or pass -Python.'}
& (Join-Path $PSScriptRoot 'build.ps1') -GameDir $GameDir -Csc $Csc
if($LASTEXITCODE -ne 0){throw 'SDK plugin build failed.'}
$sdkVersion='0.7.8a1'
if(-not $PackageName){$PackageName='agent-sdk-'+$sdkVersion+'-'+(Get-Date -Format 'yyyyMMdd-HHmmss')}
if($PackageName -notmatch '^[A-Za-z0-9._-]+$'){throw 'Use a simple package directory name.'}
$sdkPackageRoot=Join-Path $PSScriptRoot ('dist\'+$PackageName)
if(Test-Path -LiteralPath $sdkPackageRoot){throw 'Package directory already exists.'}
New-Item -ItemType Directory -Path $sdkPackageRoot | Out-Null
Push-Location $PSScriptRoot
try {
    # Versioned resources are already staged in this release source snapshot.
    & $Python -m pip wheel --no-build-isolation --no-deps --wheel-dir $sdkPackageRoot ./sdk
    if($LASTEXITCODE -ne 0){throw 'SDK wheel build failed.'}
} finally { Pop-Location }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'bin\SP2BuildAssistant.dll') -Destination $sdkPackageRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'sdk\sp2model\resources\release-info.json') -Destination $sdkPackageRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'sdk\README.md') -Destination $sdkPackageRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'sdk\README.zh-CN.md') -Destination $sdkPackageRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'sdk\API.md') -Destination $sdkPackageRoot
foreach($sdkNewDocument in @('Modeling-Workflow.md','Modeling-Semantic-Workflow.md','Modeling-Reference-Features.md','Advanced-Native.md','Services.md','Hard-Surfaces.md','Knowledge.md','Knowledge-Funky.md','Updates.md')){Copy-Item -LiteralPath (Join-Path $PSScriptRoot ('sdk\'+$sdkNewDocument)) -Destination $sdkPackageRoot}
$sdkReadmePath=Join-Path $sdkPackageRoot 'README.md'
(Get-Content -LiteralPath $sdkReadmePath -Raw).Replace('(../docs/Implementation-Route-A-SDK-0.7.1.md)','(Implementation-Route-A-SDK-0.7.1.md)') | Set-Content -LiteralPath $sdkReadmePath -Encoding utf8
New-Item -ItemType Directory -Path (Join-Path $sdkPackageRoot 'examples'),(Join-Path $sdkPackageRoot 'skills\sp2-modeling-sdk') | Out-Null
foreach($sdkExample in @('build_body.py','task_body.py','task_repeat.py','modeling_task.py')){Copy-Item -LiteralPath (Join-Path $PSScriptRoot ('sdk\examples\'+$sdkExample)) -Destination (Join-Path $sdkPackageRoot 'examples')}
foreach($sdkSemanticExample in Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'sdk\examples') -Filter 'semantic_*.json'){Copy-Item -LiteralPath $sdkSemanticExample.FullName -Destination (Join-Path $sdkPackageRoot 'examples')}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'sdk\skills\sp2-modeling-sdk\SKILL.md') -Destination (Join-Path $sdkPackageRoot 'skills\sp2-modeling-sdk')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'sdk\sp2model\resources\skill') -Destination (Join-Path $sdkPackageRoot 'skills\sp2-build-assistant') -Recurse
New-Item -ItemType Directory -Path (Join-Path $sdkPackageRoot 'worker-wheelhouse') | Out-Null
$sdkWorkerManifest=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'sdk\sp2model\_services\reference-worker-wheels.json') -Raw | ConvertFrom-Json
foreach($sdkWorkerWheel in $sdkWorkerManifest.packages){
    $sdkWorkerPath=Join-Path $WorkerWheelhouse $sdkWorkerWheel.filename
    if(-not(Test-Path -LiteralPath $sdkWorkerPath -PathType Leaf) -or (Get-Item -LiteralPath $sdkWorkerPath).Length -ne $sdkWorkerWheel.size -or (Get-FileHash -LiteralPath $sdkWorkerPath).Hash -ine $sdkWorkerWheel.sha256){throw ('Locked worker wheel missing/mismatched: '+$sdkWorkerWheel.filename)}
    Copy-Item -LiteralPath $sdkWorkerPath -Destination (Join-Path $sdkPackageRoot 'worker-wheelhouse')
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'sdk\sp2model\_services\reference-worker-wheels.json'),(Join-Path $PSScriptRoot 'sdk\sp2model\_services\reference-worker-requirements.lock') -Destination $sdkPackageRoot
New-Item -ItemType Directory -Path (Join-Path $sdkPackageRoot 'deployment') | Out-Null
foreach($sdkDeployment in @('install_073.py','verify_sdk_install.py')){Copy-Item -LiteralPath (Join-Path $PSScriptRoot ('deployment\'+$sdkDeployment)) -Destination (Join-Path $sdkPackageRoot 'deployment')}
# Evidence lives in the repository, not in the distributable. Keep package
# links useful without bundling profiles, credentials or game dependencies.
foreach($sdkDocFile in Get-ChildItem -LiteralPath $sdkPackageRoot -Filter '*.md'){
    $sdkDocText=Get-Content -LiteralPath $sdkDocFile.FullName -Raw
    $sdkDocText=$sdkDocText.Replace('../docs/','').Replace('../tests/artifacts/','../../tests/artifacts/').Replace('../tests/agent_modeling/','../../tests/agent_modeling/')
    Set-Content -LiteralPath $sdkDocFile.FullName -Value $sdkDocText -Encoding utf8
}
$sdkFiles=Get-ChildItem -LiteralPath $sdkPackageRoot -File -Recurse | ForEach-Object { @{name=$_.FullName.Substring($sdkPackageRoot.Length+1).Replace('\','/');bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash} }
$sdkSources=Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'sdk\sp2model'),(Join-Path $PSScriptRoot 'bridge') -File -Recurse | Where-Object {$_.FullName -notmatch '__pycache__' -and $_.Extension -in '.py','.cs','.md','.json','.lock'} | ForEach-Object { @{path=$_.FullName.Substring($PSScriptRoot.Length+1);sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash} }
$sdkSources+=@('sdk\pyproject.toml','build.ps1','build-agent-sdk.ps1','cli\sp2build.py','cli\shape_contracts.py','cli\precision_contracts.py','cli\modeling_contracts.py','cli\build_review_cli.py','cli\build_loop.py','cli\contracts.py') | ForEach-Object { @{path=$_;sha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $_) -Algorithm SHA256).Hash} }
$sdkSources+=@('tools\build_parts_knowledge_077.py','tools\build_funky_knowledge_077.py','deployment\stage_knowledge_077.py','deployment\stage_resources_073.py','deployment\install_073.py','deployment\verify_sdk_install.py','deployment\skills\sp2-build-assistant\SKILL.md','knowledge\v077\parts.json','knowledge\v077\funky.json','knowledge\v077\manifest.json') | ForEach-Object { @{path=$_;sha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $_) -Algorithm SHA256).Hash} }
$sdkGameHash=(Get-FileHash -LiteralPath (Join-Path $GameDir 'SimplePlanes 2_Data\Managed\Game.dll') -Algorithm SHA256).Hash
$sdkBranch=git -C $PSScriptRoot branch --show-current
$sdkCommit=git -C $PSScriptRoot rev-parse HEAD
$sdkDirty=@(git -C $PSScriptRoot status --porcelain).Count -gt 0
$sdkPythonVersion=& $Python -c 'import platform;print(platform.python_version())'
@{version=$sdkVersion;route='agent-sdk';contract='sp2model/1';releaseStatus='development';acceptanceHooks=$false;testHostIncluded=$false;gameAssemblySha256=$sdkGameHash;source=@{branch=$sdkBranch;commit=$sdkCommit;dirty=$sdkDirty};dependencies=@{buildSetuptools='84.0.0';python=$sdkPythonVersion;runtimeThirdParty=@();worker=$sdkWorkerManifest};files=@($sdkFiles);sources=@($sdkSources)} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $sdkPackageRoot 'manifest.json') -Encoding utf8
Compress-Archive -Path (Join-Path $sdkPackageRoot '*') -DestinationPath ($sdkPackageRoot+'.zip')
[pscustomobject]@{package=$sdkPackageRoot+'.zip';sha256=(Get-FileHash -LiteralPath ($sdkPackageRoot+'.zip') -Algorithm SHA256).Hash;installation='isolated SDK/game runtime only'} | ConvertTo-Json
