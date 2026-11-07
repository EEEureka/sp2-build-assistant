# Install the SP2 Build Assistant skill

English · [简体中文](README.zh-CN.md)

The skill teaches a local AI agent how to use the SimplePlanes 2 designer through `sp2build`. Install the matching full package and start the game before giving the agent a modeling task. [v0.5.0 release](https://github.com/EEEureka/sp2-build-assistant/releases/tag/v0.5.0)

Run the installer from PowerShell in the extracted skill archive.

```powershell
.\install-skill.ps1
```

Use `-SkillRoot` for a custom skill directory, or copy the `sp2-build-assistant` folder into that directory. The agent needs to be able to run `sp2build` on the Windows computer running the game.
