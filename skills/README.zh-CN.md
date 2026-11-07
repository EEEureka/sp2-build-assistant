# 安装 SP2 Build Assistant skill

[English](README.md) · 简体中文

这个 skill 说明本机 AI Agent 如何通过 `sp2build` 操作 SimplePlanes 2 设计器。在交给 Agent 建模任务前，先安装同版本的完整工具并启动游戏。 [v0.5.0 发布页](https://github.com/EEEureka/sp2-build-assistant/releases/tag/v0.5.0)

在解压目录打开 PowerShell 并运行安装器。

```powershell
.\install-skill.ps1
```

自定义 Agent 技能目录可用 `-SkillRoot` 指定，也可手工复制 `sp2-build-assistant` 文件夹。Agent 需要能在运行游戏的 Windows 电脑上执行 `sp2build`。
