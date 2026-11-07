# Install and use the 0.7.8 modeling SDK

English · [简体中文](zh-CN/SDK-0.7.8.md)

Use this guide with the complete ZIP containing **plugin 0.7.8 and SDK 0.7.8a1**. The archive includes `manifest.json`, the plugin DLL, the `sp2model` wheel, `worker-wheelhouse`, and `deployment/install_073.py`. Install the plugin, SDK, skill and reference worker from the same package.

## Install into the game directory

Use Windows x64, a compatible SimplePlanes 2 build, BepInEx 5 for Mono, and **64-bit Python 3.12**. The reference worker uses the offline Python 3.12 dependencies in the package. The installer checks the game's `Game.dll` hash against the manifest.

Close the target game. In PowerShell, replace the example paths and enter the ZIP SHA-256 published with the package. Keep the ZIP next to a fresh extraction directory with the same base name.

```powershell
$game = 'C:\Games\SimplePlanes 2'
$zip = 'C:\Downloads\sp2build-0.7.8.zip'
$expectedSha256 = 'ENTER_THE_PUBLISHED_SHA256'
$package = Join-Path (Split-Path -Parent $zip) ([IO.Path]::GetFileNameWithoutExtension($zip))
$tool = Join-Path $game 'SP2BuildAssistant'
$python = py -3.12 -c 'import sys; print(sys.executable)'

if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash -ine $expectedSha256) {
    throw 'ZIP SHA-256 mismatch'
}
Expand-Archive -LiteralPath $zip -DestinationPath $package
& $python (Join-Path $package 'deployment\install_073.py') `
    --package $package --expected-sha256 $expectedSha256 --game $game `
    --install-root $tool --skill (Join-Path $tool 'skills\sp2-build-assistant') `
    --python $python --isolated
if ($LASTEXITCODE -ne 0) { throw 'Installation failed. Check the installer output.' }
$sp2model = Join-Path $tool 'bin\sp2model.cmd'
& $sp2model version
```

The `--isolated` flag keeps the SDK, skill and worker in the specified tool directory. The DLL goes into the selected game's `BepInEx/plugins` and loads at the next game start. Use the full launcher path to select this installation when multiple versions are available.

## Connect the agent

Give your local agent the `skills/sp2-build-assistant` folder installed under `$tool` and the full launcher path. Start the game and open a test craft. Substitute the current game PID and craft name below.

```powershell
& $sp2model instances list
& $sp2model doctor --live
& $sp2model inspect --instance 12345 --craft 'My test craft'
& $sp2model commands schema --command properties.describe
```

With several running instances, pass `--instance` to live commands. If installation reports a game hash mismatch after a game update, use a package built for that game version. `updates check` reports available versions. The user handles installation and restart.

## Run a modeling task

Use a Python task to repeat structured work such as placing fuselage sections along a common axis. Give the parts logical names, specify the expected dimensions and assembly relationships, and preview the proposed scope. After applying it, measure native geometry and read the connections again. Inspect native views when checking material, occlusion or bevels.

The bundled `examples/task_body.py` previews by default. This example records part bindings in a local project file.

```powershell
& $sp2model run (Join-Path $package 'examples\task_body.py') `
    --instance 12345 --craft 'My test craft' --project .\model-project.json
```

After confirming the craft, dimensions and write scope, use the example's `apply` parameter to execute. Use `resume` with the original journal if the outcome is unclear. Confirm part references again after saving or reopening.

The package includes `API.md`, `Modeling-Workflow.md`, `Knowledge.md`, and `Knowledge-Funky.md` for modeling APIs, parts and Funky Trees. Check the effective native properties for the relevant part and test flight behavior separately from geometry.
