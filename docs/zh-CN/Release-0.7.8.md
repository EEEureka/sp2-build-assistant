# SP2 Build Assistant 0.7.8

[English](../Release-0.7.8.md) · 简体中文

发布于 2026 年 11 月 7 日。本版包含供 Agent 操作 SimplePlanes 2 设计器的 **插件 0.7.8** 与 **Python SDK 0.7.8a1**。

下载 [sp2build-0.7.8.zip](https://github.com/EEEureka/sp2-build-assistant/releases/download/v0.7.8/sp2build-0.7.8.zip) 和 [SHA-256 校验文件](https://github.com/EEEureka/sp2-build-assistant/releases/download/v0.7.8/sp2build-0.7.8.sha256)，按 [安装指南](SDK-0.7.8.md)配置。完整 ZIP 包含插件、SDK、Agent skill 和参考处理组件的离线依赖。

## 包含的能力

- 通过 `sp2model` 查询原生零件、规划和实施限定范围的建模编辑，使用逻辑部件绑定、任务日志和明确的恢复流程。
- 机身与机翼建模、受支持的机构和控制面编辑、硬表面精修、原生测量和设计器截图。
- 整理后的原生零件与 Funky Trees 知识索引，也可从指定游戏实例查询实时有效属性和可写条件。
- 用 `updates check` 查询 GitHub 公开版本，用 `updates status` 检查本地版本和组件，用 `updates guide` 获取对应安装位置的升级步骤。
- 中英文项目说明与安装指南。

## 安装要求

使用 Windows x64、BepInEx 5 Mono 和 64 位 Python 3.12。安装器会核对所选游戏 `Game.dll` 与清单中的哈希。游戏构建变化后，请使用与其匹配的安装包。

SDK 包版本保留为 `0.7.8a1`，与本包插件 `0.7.8` 配套。更新查询提供可用版本信息，安装和重启由用户明确执行。

## 验证与范围

插件与 SDK 代码对应此前已验收的 0.7.8 制品。本轮发布整理调整了用户文档与包内容，插件 DLL、SDK wheel 及锁定的参考处理依赖保持相同。已核对包哈希，并在独立测试目录验证安装、命令发现与知识资源。

部分高级知识说明仍有未覆盖语义。编辑具体部件前应查询实时有效属性。外观、机构动作和飞行表现分别通过对应的游戏检查确认。

[v0.7.8 源码标签](https://github.com/EEEureka/sp2-build-assistant/tree/v0.7.8)包含对应版本的产品源码。`release-sources.json` 记录已验证的源码输入和制品哈希。打包脚本采用可配置路径，并收录面向用户的说明。
