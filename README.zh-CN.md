# SP2 Build Assistant

[English](README.md) · 简体中文

SP2 Build Assistant 让 AI Agent 能直接使用 **Windows 上的 SimplePlanes 2 飞机设计器**。你描述想造什么、哪里需要改，Agent 读取当前设计，在游戏里建造或修订，再把实际测量结果交给你验收。

## Agent 怎么使用

1. **准备工具。** 安装 BepInEx 插件和配套命令行工具，把随包提供的 `sp2-build-assistant` skill 交给能在本机执行命令的 Agent。Skill 说明如何读取设计、实施编辑和验证结果。
2. **打开载具，交代目标。** 在设计器中打开载具或工作副本，告诉 Agent 要做哪一部分、哪些地方要保留，以及如何验收。
3. **由 Agent 在设计器内建造。** Agent 调用 `sp2build` 或新版 `sp2model`。游戏内插件通过原生设计器接口读写载具，并返回结构化结果供 Agent 复查。
4. **查看结果并继续迭代。** 可以要求 Agent 提供同视角的前后截图、测量值和改动摘要，再针对偏差局部修订。由你在游戏里检查最终外观和实际表现。

> 精修当前飞机两段机身之间的接缝，保留舷窗和其余机身的位置。先量接缝，再局部调整，最后按同一侧视角复拍并报告剩余间隙。

## Agent 能做什么

- **理解当前设计。** 读取零件、几何、位置、挂点、连接、材质和控制绑定。搜索游戏零件库，查询具体零件支持哪些属性。
- **搭建和精修组件。** 增加、定位、镜像、连接和编辑零件。调整机身截面、机翼、控制面，以及受支持的材质和机构参数。
- **配置载具逻辑。** 查询变量和部件输出，编辑受支持的绑定，在实机测试前检查 Funky Trees 表达式。
- **验证并迭代。** 获取设计器原生视角和网格分析图，测量截面、间隙和接缝，对比检查点，必要时恢复。也可以读取设计器的重心、升力中心和推力中心，辅助判断布局。

## 开始使用

1. [安装与连接](docs/zh-CN/Installation.md)
2. [让 Agent 完成第一次建模任务](docs/zh-CN/Quickstart.md)
3. [查阅 CLI 手册](docs/zh-CN/CLI-Usage.md)

专项工作流见[局部精修](docs/zh-CN/Precision-Workflow.md)、[原生截图](docs/zh-CN/Designer-Screenshots.md)、[网格分析](docs/zh-CN/Visual-Usage.md)和[三心分析](docs/zh-CN/Centers-Usage.md)。

当前仓库基线对应 [0.5.0 版本说明](docs/zh-CN/Release-0.5.0.md)。如果已取得 0.7.8 安装包，请从 [SDK 安装与建模指南](docs/zh-CN/SDK-0.7.8.md)开始。
