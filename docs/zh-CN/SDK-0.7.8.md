# 0.7.8 SDK 安装与建模

[English](../SDK-0.7.8.md) · 简体中文

本页适用于已经取得的 **0.7.8 插件和 0.7.8a1 SDK 完整 ZIP**。包内应有 `manifest.json`、插件 DLL、`sp2model` wheel、`worker-wheelhouse` 和 `deployment/install_073.py`。将插件、SDK、skill 与参考处理组件作为同一版本安装。

从 [v0.7.8 Release](https://github.com/EEEureka/sp2-build-assistant/releases/tag/v0.7.8) 下载 [sp2build-0.7.8.zip](https://github.com/EEEureka/sp2-build-assistant/releases/download/v0.7.8/sp2build-0.7.8.zip) 和 [SHA-256 校验文件](https://github.com/EEEureka/sp2-build-assistant/releases/download/v0.7.8/sp2build-0.7.8.sha256)。

## 安装到游戏目录

在 Windows x64 上准备与包匹配的 SimplePlanes 2、BepInEx 5（Mono）和 **64 位 Python 3.12**。参考处理组件使用包中为 Python 3.12 提供的离线依赖。安装器会对照清单中的 `Game.dll` 哈希检查游戏版本。

关闭目标游戏。在 PowerShell 中执行下面的步骤，将示例路径换成实际位置，并把哈希换成发布方提供的 ZIP SHA-256。安装器要求 ZIP 和解压目录同名且位于同一父目录。请解压到一个新目录。

```powershell
$game = 'C:\Games\SimplePlanes 2'
$zip = 'C:\Downloads\sp2build-0.7.8.zip'
$expectedSha256 = '填入发布方提供的 SHA-256'
$package = Join-Path (Split-Path -Parent $zip) ([IO.Path]::GetFileNameWithoutExtension($zip))
$tool = Join-Path $game 'SP2BuildAssistant'
$python = py -3.12 -c 'import sys; print(sys.executable)'

if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash -ine $expectedSha256) {
    throw 'ZIP SHA-256 不匹配'
}
Expand-Archive -LiteralPath $zip -DestinationPath $package
& $python (Join-Path $package 'deployment\install_073.py') `
    --package $package --expected-sha256 $expectedSha256 --game $game `
    --install-root $tool --skill (Join-Path $tool 'skills\sp2-build-assistant') `
    --python $python --isolated
if ($LASTEXITCODE -ne 0) { throw '安装失败，请检查安装器输出' }
$sp2model = Join-Path $tool 'bin\sp2model.cmd'
& $sp2model version
```

`--isolated` 将 SDK、skill 和参考处理组件留在指定的工具目录。DLL 仍会安装到所选游戏的 `BepInEx/plugins`，所以升级后需要重启该游戏。已有其他版本时，用上面的完整启动器路径可以明确选择新版。

## 第一次连接

启动游戏，在设计器打开测试载具。以下示例中的进程 ID 和名称要换成你当前的游戏实例及载具。

```powershell
& $sp2model instances list
& $sp2model doctor --live
& $sp2model inspect --instance 12345 --craft 'My test craft'
& $sp2model commands schema --command properties.describe
```

有多个实例时，给连接游戏的命令加 `--instance`。若游戏更新后安装器报告哈希不匹配，使用面向该游戏构建的包。更新查询通过 `updates check` 查看可用版本，安装和重启由用户执行。

## 用 SDK 做一轮建模

SDK 适合把重复工作写成 Python 任务。例如，可沿同一基准线规划一组机身截面，为部件指定逻辑名称，并声明预期长度、装配关系和误差。预览用于检查计划结构和写入范围。执行后，应回读实际网格和连接，按同一目标复测。关心材质、遮挡或倒角时，再结合原生视角检查。

包内 `examples/task_body.py` 默认只预览。以下命令以当前目录中的一个项目文件记录部件绑定。

```powershell
& $sp2model run (Join-Path $package 'examples\task_body.py') `
    --instance 12345 --craft 'My test craft' --project .\model-project.json
```

确认目标载具、尺寸与可写范围后，可用示例的 `apply` 参数执行。执行结果不明确时，使用 `resume` 查询原日志，避免重复提交。保存或重新打开后应重新确认部件引用。

本机 AI 助手可导入工具目录下 `skills/sp2-build-assistant`，并显式使用这个版本的启动器。包内的 `API.md`、`Modeling-Workflow.md`、`Knowledge.md` 和 `Knowledge-Funky.md` 进一步说明建模接口、零件属性和 Funky Trees。部分参数受原生零件类型和状态限制，几何验证与飞行测试分别进行。
