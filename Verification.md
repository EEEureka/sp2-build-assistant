# 验证与部署记录（CLI / skill / DLL 0.5.0）

最新交付（2026-10-05）：**0.5.0已完成代表场景验收、正式部署与加载核对**。94个必需适配字段证据、250轮752项长测、正式DLL功能及原生对照通过；通过插件正常退出后台游戏，939个玩家文件不变。发布物、限制、内存观测和哈希见[0.5.0最终报告](docs/Verification-0.5.0.md)。以下均为历史版本记录。

最新实测（2026-10-02，用户再次重启后）：**0.4.11 已加载并通过截图常用流程和动态挂点修复验收**，buildId `4c2ed599-e6da-411b-a214-f1311690ef0e`、PID6756。25张请求图实际查看，14个实时挂点与geometry一致，独立复核81/81通过；飞机/选择/撤销历史未变，仍42件，场景仅1实例。FB-042关闭。渲染中取消、强制渲染异常和异常场景截图未做故障注入。**本轮没有新DLL变更，不需再次重启。** [完整验收](docs/Verification-0.4.11.md)。下述“待加载”均为此前部署时的历史状态。

2026-10-02：0.4.10 已加载并完成原序列实机复验：同批多次重建、CLI undo、原生 UI undo、失败整批恢复、checkpoint rollback 均恢复指纹且容器只含一个飞机实例，FB-041关闭；有效 inputControllers 默认值/下标/模板读出通过，FB-040关闭。已换装完整双涡桨，42件/41连接，全连通；独立构型复核39项通过，实际打开窗口与推荐图。未試飞，独立 Spoiler 未完成。详情见 [本轮报告](docs/Agent-Feedback-0.4.11.md)。

0.4.11 新增原生设计器截图和实时挂点坐标修复（FB-042）。274项离线回归、106项通用契约、32项形状契约、17项截图/挂点专项契约、127份本轮真实返回契约及 skill 验证通过。新截图渲染、相机恢复及动态挂点有效值仍需加载新DLL后实测；不把离线通过当作实机验收。

0.4.11 已部署并读回：全局CLI版本0.4.11；构建与游戏目录DLL SHA256均为 `3EB3A44332A308850CBCD57FFD0447C1CC01944935306C8CC80FCC09FBF56EB7`；12个CLI/skill文件安装哈希一致。运行中仍为0.4.10、buildId `7c97a0cd-2f52-4b47-b793-74eec1dec1ee`。部署前后42件载具身份、rev1及指纹完全不变，sceneIntegrity healthy；新命令对旧DLL明确返回unsupported_bridge_feature。没有自动重启。部署证据在 [deployment.json](tests/artifacts/releases/0.4.11/deployment.json)。

以下为历史部署/验收记录；原先“待重启”的结论由上述最新实测覆盖。

已部署并读回：CLI 0.4.10、运行中 DLL 0.4.8；磁盘 DLL SHA256 **05565B4EC589E00AC1A72EA2FF89B65BB68CED7500C14B8FF3BA66E4E7151953** 与构建一致，安装 skill 所有文件一致。部署后 Aircraft 仍 rev28 / 30 件 / 原指纹，诊断选择已清空，未重启或继续写飞机。证据 `tests/artifacts/staged-build/direct-0.4.8/release-0.4.10/deployment.json`。已部署不等于运行时修复通过。

0.4.10：**S13 完整场景验收撤回，待修复后实机复验**。用户截图及实际 UI 点选证实上下两套可拾取模型；同 ID #23，selection 的 Y=2.0，当前 parts.get 的 Y=3.034964，当前 XML 仍30件。修复同帧连续 Replace 依赖按名称删除的生命周期缺陷，undo 使用受控替换；status 增加 sceneIntegrity，异常场景拒绝写入/捕获，旧对象选择不再冒充当前部件。构建、253 项离线回归（含10项生命周期复现/恢复测试）、105 项通用契约、32 项形状契约及 skill 校验通过。重启后的原操作序列和真实窗口验收尚未进行；涡桨换装待场景复验后继续。详见 [0.4.10](docs/Agent-Feedback-0.4.10.md)。以下保留此前记录。

0.4.9 更新（2026-10-02）：用户授权后改由 Codex 直接建造，不调用 DSH。DLL 0.4.8 的 S06 输入配置修复已实机通过；后续襟翼、缝翼、BrakeFlap、双发动机/燃油、三点起落架、变量/输出完成，30 件 / 29 连接无孤立，10 个对称组启用。几何/拾取热刷新、失败整批恢复、undo/rollback、ID 复用提示、限定 assembly 删除实测通过。独立 Spoiler 仍未实现，未试飞。0.4.9 新增有效输入配置读出（包含 XML 省略的默认值），构建、243 项离线回归、105 项通用契约、32 项形状契约及本轮返回契约/7 项新字段合成用例、skill 校验通过；新 DLL 运行时读出待重启验证。详见 [直接验收报告](docs/Agent-Feedback-0.4.9.md)。

0.4.9 **已部署**：全局 `sp2build version`=0.4.9；磁盘 DLL SHA256 **43FDD95E1A31780661ABCED65BCA5B7D6B1B7B6ABD1990B2002F34BCDEECA769**，与构建产物一致；安装 skill 所有文件哈希一致。运行中仍加载 0.4.8，未重启游戏。部署后飞机仍为 rev28 / 30 件且指纹未变。全局 commands schema 已返回新的 InputController 定义。部署实读证据在 `tests/artifacts/staged-build/direct-0.4.8/release-0.4.9/`。以下为历史部署记录。

0.4.8 更新（2026-10-02）：S06 双侧主翼外段控制面保留，飞机共 16 件 / 15 连接；60/60 独立证据检查通过，但两侧仍是 Pitch，S06 暂不通过。已修复原生输入控制字段被缺失元数据阻挡的问题，并增加目录扩展说明和输入编译验证。构建、243 项离线回归、105 项通用契约、32 项形状契约及 skill 校验通过。部署后仍需用户保存并重启；运行中 0.4.6 不能验证此修复。详见 [S06 反馈与复验计划](docs/Agent-Feedback-0.4.8.md)。以下为既有阶段记录。

S04 后续实测：用户已重启加载 0.4.6，普通/镜像翼先加控制面再连根部、同表面多个控制面、重叠拒绝及恢复全部通过，协调端 72/72 证据检查通过，恢复到新会话的 12 件基线，实际打开最终整机和尾翼图。S05 完成垂尾/方向舵共 14 件 / 13 连接，布局缝隙已修正；55/55 独立检查通过。0.4.7 仅更新 schema/skill 说明，DLL 不变；详见 [S05 反馈核查](docs/Agent-Feedback-0.4.7.md)。以下 0.4.6 首次部署说明为重启前历史记录。

0.4.6 更新（2026-10-02）：S04 已建造 12 件 / 11 连接，左右平尾与升降舵的 56 项独立证据检查通过，已实际打开整机与尾翼细节图。发现 wing.control.add 抢占未连接机翼根部（FB-032），已修为使用原生表面接收挂点，并新增挂点 ID 与模板来源返回。构建、215 项离线回归、105 项通用契约、32 项形状契约通过；skill 校验通过。新 DLL 运行时复验待用户保存、重启后进行，S04 尚未通过，不进入 S05。详见 docs/Agent-Feedback-0.4.6.md 与 tests/artifacts/staged-build/S04-review/。


0.4.4 更新（2026-10-02）：S03 首次镜像错误已从游戏与插件源码确认，修复查询/创建/几何校验的旧对称配置，并在受保护写操作前刷新原生缓存。原生 flipped 翼质量中心 Y 清零问题仅增加版本限定警告；snapshot 的 XML 保存时边界元数据增加说明。详情见 [0.4.4 修订](docs/Agent-Feedback-0.4.4.md)。

离线构建通过；回归 **215 项**（C# 166 + Python 49）、输出/命令契约 **105 项**、形状契约 **32 项**全部通过。S03 对旧 DLL 的原始输出独立复核 **81/81**，并实际打开四视图。中间同步传播的自动核查依据为批次响应和恢复指纹，最终几何有独立回读；不把离线证据作为新 DLL 的运行时验收。

后续实测：用户重启后已加载 0.4.4。真实触发窗口获得焦点时原生保存居中，观察 nativeCacheStale=true 后第一次创建正确，同步开关独立回读与最终回滚均通过，协调端 39/39 项运行时证据检查通过，最终回滚指纹与新会话起点一致并查看最终三视图。S03 通过，可进入 S04。原生质量计算问题没有被修正，相关警告已实测。详细哈希与部署回读见 tests/artifacts/staged-build/S03-review/deployment-0.4.4.json（重启前）及 runtime-0.4.4-review.json。CLI / skill 0.4.5 仅补充 FB-031 的摘要/明细说明，不改 DLL；见 docs/Agent-Feedback-0.4.5.md。

后续 S02 更新（2026-10-02）：单侧主翼完成，7 件 / 6 连接；协调端对完整 revision 14 输出做 64 项检查通过，包含 schema、全机连通、形状/实际宽度、质量与升力来源、正确平移的射线命中。COL 有效且唯一来源为 #7，COT 无源；没有比较原生 UI 三心标记或验证飞行性能。CLI 0.4.3 修复 FB-026 未知缺值参数的误导诊断，49 项 Python 回归通过；DLL 未变，DSH 复验已通过。参见 [0.4.3 修订](docs/Agent-Feedback-0.4.3.md)。

后续 S01 更新（2026-10-02）：机身建造完成，协调端新鲜只读采样的 30 项跨来源核查通过；全部 6 件已连接，总长 11.7 m，质量约 331.518 kg，实际查看四视图。新增 CLI / skill 0.4.2 解释 autoResize 原生连接回调与完成后 revision 变化，DLL 仍为 0.4.0。DSH 反馈中混合时间线的部分已独立纠正；详见 [0.4.2 修订](docs/Agent-Feedback-0.4.2.md)。后续主翼等阶段仍待验收。

后续 S00 更新（2026-10-02）：用户已启动游戏，0.4.0 DLL 加载确认。DSH 在当前两件初始飞机上完成质量三心/无翼无推力/图片/未编辑基线对比/结构化读取，协调端独立复核；尚未验证有翼/推进源/编辑后比较等后续场景。反馈导致 CLI / skill 0.4.1 契约修订，DLL 不变，无需重启。详见 [0.4.1 修订](docs/Agent-Feedback-0.4.1.md) 与 tests/artifacts/staged-build/S00-review。以下为原 0.4.0 仅部署时的历史记录。

日期：2026-10-02。目标游戏 0.7.8.103 / XML 25 / Windows Mono / BepInEx 5.4.23.5。

**状态：首版三心功能已实现、离线验证通过，DLL、全局 CLI 和 skill 已部署。用户要求先部署、不打开游戏验收，本轮未启动/重启游戏，未调用游戏内查询或写入，也没有通过 DSH 做实机验收。磁盘安装成功不代表运行中的 DLL 已更新。**

## 交付

- `craft.centers`：三心坐标、三对相对关系、原生算法/权重/范围/覆盖说明；无有效源为 unavailable/null，覆盖不足为 partial。
- `--detail contributors`：mass/lift/thrust 明细、分页、全机份额及质量矩；focus selected、显式 parts 或原生 assembly 仅过滤/高亮，不改变全机结果。
- `--baseline`：完整报告文件比较；会话、算法、游戏版本、朝向与参考身份守卫；输出位置/相对向量/距离的变化，不把共同平移当作布局改善。
- `--images` 与 `visual.capture overlays.centers`：同采样真实网格与三心图，中心局部放大、远中心下的飞机外形补图，现有 raw/ID/像素拾取不被标注污染。
- 完整输入/输出 schema、全局命令发现、最低已加载 DLL 版本检查、CLI/skill/调用手册。

静稳定性、配平、推力力矩不在本版求解范围；旧翼/未知 Mod 未验证的读取分支明确排除。前后对比以 JSON 数值为准，图片只画当前样本。详见 [三心使用手册](docs/Centers-Usage.md)。

## 离线证据

| 检查 | 结果 |
| --- | --- |
| DLL 引用本机游戏程序集编译 | 通过 |
| 原有独立功能 + CLI 检查 | 170 项通过 |
| 新增三心算法、守卫、投影与图像检查 | 27 项通过 |
| 新增 CLI/基线/版本门槛/下载检查 | 15 项通过 |
| 功能检查合计 | **212 项通过** |
| 命令与历史输出 schema | 105 项通过 |
| structured 输出 schema | 10 项通过 |
| 三心生成报告与输入分支 schema | 16 项通过 |
| schema 检查合计 | **131 项通过** |
| skill-creator quick_validate | 通过 |
| 合成网格三视图 | 已打开 PNG 检查图例、中心形状、引线、三轴间距与比例尺；非游戏截图 |
| 全局命令 | 从 `C:\Users\30023` 运行 `sp2build version / craft centers --help / commands schema / commands list` 通过；71 命令、20 批次操作 |
| 安装读回 | DLL、CLI 四个模块、app 内 skill、agent skill 三心指引与源文件 SHA256 一致 |

主要离线产物位于 `tests/artifacts/centers-0.4.0/`：unit-tests.log、summary/contributors/partial/empty/comparison/not-comparable/with-images.json、manifest.json、合成图像、contract-validation.json、deployment.json。历史契约复核位于 tests/artifacts/contracts-0.4.0；这些测试数据不进入发行包。

执行过 `tests/run-unit-tests.ps1`、`tests/validate_centers_contracts.py`、`tests/validate_contracts.py`、`tests/validate_structured_contracts.py`；未使用任何 --live 测试选项。

## 磁盘部署

- DLL：`D:\apps\steam\steamapps\common\SimplePlanes 2\BepInEx\plugins\SP2BuildAssistant.dll`
- 全局命令：`C:\Users\30023\.sp2build\bin\sp2build.cmd`，用户 PATH 已注册；CLI 0.4.0，内部运行时 Python 3.14.2。
- CLI 和随附资料：`C:\Users\30023\.sp2build\app`
- Agent skill：`C:\Users\30023\.agents\skills\sp2-build-assistant`
- DLL 大小：312320 bytes。
- DLL SHA256：`EBC493BE28432FE8BFC5967A8887C2038E94748E74BF43A3A32AFC1AD0F81077`
- DLL MVID：`2508b86e-908e-411d-ae9a-1d41cf2a28cd`
- 发行包：`dist/SP2BuildAssistant-0.4.0.zip`；可单独导入的 skill：`dist/SP2BuildAssistant-Skill-0.4.0.zip`。

下次正常启动游戏后加载新 DLL。本轮不声称已加载 0.4.0，也不调用 designer status 验证。

## 待实机验收

1. 与游戏原生三心标记比较位置、范围、质量换算；包括未连通件、偏置局部重心、无翼/无推进源。
2. 程序化翼、喷气、螺旋桨与旧 VTOL 范围/权重、无喷口及混合类型行为。
3. 编辑后新报告与网格一致；报告和图片在玩家并发修改时拒绝或标记陈旧。
4. 三心读取前后 XML、选择、相机、显隐及撤销历史一致，程序化喷气性能缓存未变。
5. DSH 通过三心摘要、明细、图片和基线比较完成真实建造问答。

上述保留项源于用户本轮明确要求不打开游戏验收，不属于通过项。此前版本记录保留在 [0.3.2 记录](docs/Verification-0.3.2.md)；旧版实机结果不替代新功能验收。
