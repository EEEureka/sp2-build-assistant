# 旧版 0.5.0 安装、升级与故障排查

[English](../Installation.md) · 简体中文

最新版本为 [v0.7.8](https://github.com/EEEureka/sp2-build-assistant/releases/tag/v0.7.8)，新安装请按 [SDK 安装指南](SDK-0.7.8.md)配置。本页保留 0.5.0 的 `sp2build` 命令行包安装说明。

## 安装

1. 在 Steam 库中找到 SimplePlanes 2，通过「管理 → 浏览本地文件」打开游戏目录。选择包含 `SimplePlanes 2.exe` 的目录。
2. 准备 Windows x64 的 BepInEx 5（Mono），启动游戏一次，确认生成 `BepInEx/config` 和 `BepInEx/LogOutput.log`，然后关闭游戏。 [BepInEx 安装文档](https://docs.bepinex.dev/articles/user_guide/installation/index.html)
3. 安装 Python 3.10 或更高版本。 [Python Windows 下载](https://www.python.org/downloads/windows/)
4. 在 [v0.5.0 发布页](https://github.com/EEEureka/sp2-build-assistant/releases/tag/v0.5.0) 获取 `SP2BuildAssistant-0.5.0.zip`，解压后在包内打开 PowerShell。把第一行替换为 Steam 显示的游戏目录。

```powershell
$game = 'C:\Games\SimplePlanes 2'
.\install.ps1 -GameDir $game
```

需要给本机 AI 助手安装 skill 时，在安装命令后加 `-InstallSkill`。只补装 skill 可使用同一发布页的 `SP2BuildAssistant-Skill-0.5.0.zip`，解压后运行 `install-skill.ps1`。非默认 skill 位置可传入 `-SkillRoot`。

完整安装把 DLL 放入 `BepInEx/plugins`，把命令安装到当前用户的 `%USERPROFILE%\.sp2build`，并注册用户级 PATH。重新打开 PowerShell 和需要调用它的助手后，执行以下检查。

```powershell
sp2build version --json
```

## 确认连到游戏

启动游戏，打开一份可以试验的载具并进入设计器，再运行：

```powershell
sp2build instances list
sp2build designer status
sp2build capabilities
```

0.5.0 的验收环境使用 SimplePlanes 2 `0.7.8.103`、XML 25 和 BepInEx `5.4.23.5`。游戏升级后，以目标安装包的兼容说明和状态结果为准。

| 现象 | 检查方式 |
| --- | --- |
| 找不到 `sp2build` | 重开终端后运行 `Get-Command sp2build -All`，确认解析到预期的用户安装目录 |
| 找不到游戏实例 | 确认游戏已启动，查看 `BepInEx/LogOutput.log` 中插件是否加载 |
| 有多个游戏实例 | 查看 `instances list`，用全局 `--instance` 显式指定目标，再确认设计器载具 |
| 插件版本不对 | 关闭游戏，用同一版本 ZIP 安装 DLL 和 CLI，重启后重新查询 |

反馈故障时，优先提供工具版本、游戏版本、错误码和精简的复现步骤。分享日志前应去掉本机路径、实例令牌和私人载具信息。

## 更新和移除

更新前退出游戏，再运行目标版本安装器，启动后用 `designer status` 核对版本。移除时先退出游戏，然后移除 `BepInEx/plugins/SP2BuildAssistant.dll`。如需同时移除 CLI 或 skill，按安装位置处理相应目录和 PATH 项，并保留自己保存的工作文件。
