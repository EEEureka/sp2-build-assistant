# Installation and updates

English · [简体中文](zh-CN/Installation.md)

This page covers the 0.5.0 `sp2build` package. For an existing 0.7.8 package, follow the [SDK installation guide](SDK-0.7.8.md).

## Install the plugin, CLI and agent skill

1. In Steam, find SimplePlanes 2 and choose **Manage → Browse local files**. Use the folder that contains `SimplePlanes 2.exe`.
2. Install BepInEx 5 for Windows x64 Mono. Launch the game once, check that it created `BepInEx/config` and `BepInEx/LogOutput.log`, then close the game. [BepInEx installation guide](https://docs.bepinex.dev/articles/user_guide/installation/index.html)
3. Install Python 3.10 or later. [Python for Windows](https://www.python.org/downloads/windows/)
4. Download `SP2BuildAssistant-0.5.0.zip` from the [v0.5.0 release](https://github.com/EEEureka/sp2-build-assistant/releases/tag/v0.5.0). Extract it and open PowerShell in the extracted folder. Replace the example path with the Steam game folder.

```powershell
$game = 'C:\Games\SimplePlanes 2'
.\install.ps1 -GameDir $game -InstallSkill
```

The installer copies the DLL to `BepInEx/plugins`, installs the CLI under `%USERPROFILE%\.sp2build`, and adds its launcher directory to your user PATH. The `-InstallSkill` flag installs `sp2-build-assistant` for a local agent. Open a new PowerShell window and restart your agent session so both inherit the updated PATH.

If the CLI is already installed, you can install just the skill from `SP2BuildAssistant-Skill-0.5.0.zip` on the same release page. Extract it, run `install-skill.ps1`, and use `-SkillRoot` if your agent uses a different skill directory.

## Confirm the connection

Start the game and open a test craft or a working copy in the designer.

```powershell
sp2build version --json
sp2build instances list
sp2build designer status
sp2build capabilities
```

The 0.5.0 validation environment used SimplePlanes 2 `0.7.8.103`, XML 25 and BepInEx `5.4.23.5`. After a game update, check the compatibility notes for the package you plan to install.

| Symptom | Check |
| --- | --- |
| `sp2build` is missing | Reopen PowerShell and run `Get-Command sp2build -All`. Verify that it resolves to the expected user installation. |
| No game instance appears | Start the game and look for the plugin in `BepInEx/LogOutput.log`. |
| Several game instances appear | Use `instances list` and pass `--instance` with the desired PID or instance ID. Confirm the craft in `designer status`. |
| The loaded plugin version differs | Close the game, install the DLL and CLI from the same ZIP, and check the loaded version after restarting. |

When reporting an issue, include the tool version, game version, error code and a short reproduction. Remove local paths, instance tokens and private craft details from logs before sharing them.

## Update or uninstall

Close the game before updating or removing the plugin. Run the target package's installer to update and check `designer status` after restarting. To uninstall the plugin, remove `BepInEx/plugins/SP2BuildAssistant.dll`. The CLI and skill can be removed from their respective installation directories, along with the CLI's user PATH entry.

Continue with the [first agent-assisted task](Quickstart.md).
