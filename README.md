# SP2 Build Assistant

独立私有仓库：[EEEureka/sp2-build-assistant](https://github.com/EEEureka/sp2-build-assistant)。接续开发先读[会话背景摘要](docs/SESSION-HANDOFF.md)。源码、知识、skill和测试脚本纳入Git；游戏资源、本地验收原件和生成输出保留在本机。已验收安装包见仓库的 `v0.5.0` Release。

最新发布 **CLI / DLL / skill 0.5.0**：新增有效属性发现和原生适配、窗体/文字/贴花/材质精修、局部刚性组定位、网格测量与固定视图比较，以及无需桌面键鼠的设计器原生导航。正式 DLL、全局 `sp2build` 和通用 skill 已部署并完成加载核对。

已完成 94 个必需适配字段的代表场景证据、E1–E3 局部精修、250 轮连续编辑/恢复，以及正式 DLL 必要回归。修复原生临时网格析构与重复表达式编译导致的累积；内存观测边界、历史失败及未覆盖能力均保留。详见[最终验收报告](docs/Verification-0.5.0.md)、[版本说明](docs/Release-0.5.0.md)及[验收总览](docs/Acceptance-Status-0.5.0.md)。

从[局部精修调用指南](docs/Precision-Workflow.md)开始，完整接口见[CLI 手册](docs/CLI-Usage.md)。Agent 使用“查属性与依赖→小改→固定视图→测量→差异/恢复”循环；局部能力通过不等于已证明自动复刻整架 C17。原始[能力评估](docs/C17-Precision-Building-Assessment.md)、[落地计划](docs/Implementation-Plan-0.5.0.md)和[验收方案](docs/Acceptance-Plan-0.5.0.md)作为历史目标与冻结标准保留。

Windows 上的 SimplePlanes 2 建造助手。所有 agent 功能统一由 `sp2build` CLI 提供；独立 BepInEx DLL 在游戏主线程执行原生编辑操作。无需 MCP 服务或额外常驻进程。CLI 与 DLL 通过带实例令牌的本机回环接口通信。

本版针对本机游戏 **0.7.8.103 / XML 25 / BepInEx 5.4.23.5 / Mono** 编译，CLI 使用 Python 3.10+ 标准库。DLL 更新仍需重启游戏，以 `designer status` 确认已加载版本。发布包在 `dist/`，可单独导入 skill；导入 skill 不等于安装 CLI。更早版本记录见[验证历史](Verification.md)。

0.2.2 新增明确原生归属的组件范围查询与 `assembly:true` 删除，默认单件删除不变；连接定位、空间归属和事务说明见 [DSH 反馈核查](docs/Connections-Assemblies-and-Transactions-0.2.2.md)。该功能已包含在 0.3.0 中，具体实机覆盖以验收记录为准。

新增几何刷新、选中零件、复杂形状及对称接口见 [0.2 扩展说明](docs/Complex-Parts-and-Designer-0.2.md)。

完整功能列表、调用参数、JSON 输入输出样例、错误处理和验证状态见 [CLI 调用手册](docs/CLI-Usage.md)。

0.3.0 提供 `visual resolve/capture/pick`：从当前真实网格生成三视图、斜视图、多个目标的联合总览及局部放大图，附空间变换和像素到零件的映射。使用分析配色，不还原原生涂装和透明 shader。调用、文件样例与限制见 [视觉检查手册](docs/Visual-Usage.md)；skill 已包含看图工作流。Agent 需通过自身的读图能力打开返回 PNG。

0.3.1 增加批次 ID 复用保护与事件报告、自动小目标细节图、命令输出 schema、CLI/operation 映射以及射线命中的零件身份。完整变更与验收边界见 [DSH 反馈修订说明](docs/Agent-Feedback-0.3.1.md)。

0.4.0 新增 `sp2build craft centers`：读取当前设计器的重心、升力中心、推力中心，提供相对位置、贡献分页、基线比较及同快照三心图。调用与边界见 [三心使用手册](docs/Centers-Usage.md)，场景依据见 [设计文档](docs/Centers-Analysis-Design.md)。这提供原生设计器布局信息；静稳定性、配平和推力力矩仍返回 not_assessed。

## 安装与 skill 导入

解压完整分发包后，在 PowerShell 执行：

```powershell
.\install.ps1 -GameDir '你的 SimplePlanes 2 游戏目录' -InstallSkill
```

安装器将独立 DLL 放入 `BepInEx/plugins`，将 CLI 安装到 `%USERPROFILE%\.sp2build\app`，将启动器放入 `%USERPROFILE%\.sp2build\bin` 并注册用户级 PATH，将 skill 放入 `~/.agents/skills/sp2-build-assistant`。使用用户主目录可避免从打包版 agent 安装时，文件被写入该 app 的私有 LocalCache。必须先装好 BepInEx 5。DLL 更新后重启游戏；新终端可直接执行 `sp2build`。

已经打开的 agent/终端可在其工具执行 shell 中刷新 PATH，然后继续使用同一 `sp2build` 命令；每次启动独立 shell 时可能需要重复刷新。无需改用 Python 源码入口：

```powershell
$sp2UserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($sp2UserPath) { $env:Path = $sp2UserPath + ';' + $env:Path }
sp2build version --json
```

只导入 skill，可解压单独 skill 包，执行 `install-skill.ps1`；使用自定义位置时执行 `install-skill.ps1 -SkillRoot '该 agent 的 skills 目录'`。也可直接复制包内 `sp2-build-assistant` 文件夹。支持 Markdown skill 且能执行玩家 Windows 本地命令的 agent 可以使用；纯云端 agent 需要另外具备该机器的命令执行连接。

## 基础命令

```powershell
sp2build version
sp2build instances list
sp2build designer status
sp2build capabilities
sp2build commands list
sp2build commands schema --command batch.apply
sp2build craft snapshot --include-xml --output current-snapshot.json
sp2build craft centers
sp2build craft centers --images --output-dir ./centers-view
sp2build catalog categories
sp2build catalog subcategories --category 'Aircraft Propulsion'
sp2build catalog list --category 'Aircraft Propulsion' --subcategory Jets
sp2build parts list --limit 10
sp2build variables list
sp2build outputs list
sp2build funky describe --name clamp
sp2build funky validate --expression 'clamp(Throttle,0,1)'
sp2build skill path
```

所有命令输出 UTF-8 JSON。请同时检查 `success` 与退出码。复杂输入通过 UTF-8 JSON 文件提交：`sp2build batch apply --input batch.json`。写入必须提供新的 `requestId`、当前 `craftSessionId` 和 `expectedRevision`；具体操作格式见 skill 的 `references/edits.md` 和 CLI schema。

支持当前飞机的状态、零件属性、连接点/拓扑、空间关系、全局变量和输出绑定查询；支持零件增删改、连接/断开、变量增删改/排序、输出绑定/改名/激活条件/解绑、原生撤销、会话检查点和回滚。零件库查询覆盖当前飞机未使用的模板，使用游戏原生大类、小类和介绍。运行时目录会包含当前加载的原生模板及用户子组件。

本地 `knowledge catalog` / `knowledge funky` 返回初版离线资料。零件目录的默认资料包含 160 个原生模板；运行时查询为当前可用内容的依据。离线 Funky Trees 资料尚未补齐所有输入变量及每个函数的完整语义说明。

## 边界和恢复

- 只操作编辑器当前打开的飞机。没有打开保存飞机、按保存文件路径编辑或写回其他飞机文件的命令。
- 批次失败会恢复执行前状态，结果带 `rollbackResult`。结果未知时先查询 `operation status/wait/result`，保持原 `requestId`；相同请求不会重复执行。
- `craft undo` 按玩家与 agent 共同的原生时间顺序撤销。检查点只在当前打开会话内有效；切换飞机或重启游戏后失效。
- 原生重建会产生微小 Euler 浮点差异，恢复校验容差为每轴 0.0001 度，其他字段仍需一致。版本指纹对旋转参数仍严格比较；原生生成目标集合按去重后的 ID 集合比较。
- 复杂编辑会重建当前飞机、刷新物理和编辑器缓存并恢复选中 ID。shape.update 默认同步原生对称组；part.update 需显式 symmetric:true。
- 通用属性写入使用原生 metadata；复杂几何优先使用 shape.update 的校验接口。未映射复杂类别提供完整清单和原生状态查询；结构 ID、零件类型、材料引用不作为普通属性开放。
- `batch preview` 当前只验证请求结构，实际原生约束在 apply 执行时验证。表达式检查只编译，不评估飞行行为。
- 任务结果至少保留 15 分钟，并在后续提交时清理；同一游戏进程内保留去重记录，最大 20,000 个任务。单会话最多 64 个检查点。

## 开发与验证

`bridge` 是独立 DLL 源码；`cli` 是 CLI；`skills` 是可导入 skill；`knowledge` 是离线资料。`build.ps1` 引用本机游戏和 BepInEx 程序集，不修改游戏源码或程序集。`package.ps1` 打包完整安装包和单独 skill 包，不包含游戏程序集、运行时令牌或测试飞机快照。

`tests/live_verify.py` 是对当前编辑器飞机的分阶段实机测试工具。它会临时修改飞机，必须先执行 read 建立检查点，并在结束时 restore；不应对玩家正在同时操作的飞机运行。基础独立检查：`./tests/run-unit-tests.ps1`。当前实机验证范围见 [调用手册的验证状态](docs/CLI-Usage.md#13-验证状态和源码依据)。

0.3.2 新增连接、变量及输出的 `--view structured` 读取，统一来源/视觉组字段，并严格校验变量重排；失败恢复结果说明 revision 的变化。见 [0.3.2 修订说明](docs/Agent-Feedback-0.3.2.md)。
