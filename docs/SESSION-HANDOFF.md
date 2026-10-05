# 新会话接续背景

更新：2026-10-05。项目根目录：`D:\codeSpace\sp2\SP2BuildAssistant`。本文件是上一长会话的接续摘要；旧消息中的“待重启、待验收、请继续”大多已完成，不应重新执行。

Git远端：[私有仓库 EEEureka/sp2-build-assistant](https://github.com/EEEureka/sp2-build-assistant)，默认分支 `main`，`origin` 使用 HTTPS。当前机器已配置 Git Credential Manager；不要读取、打印或提交凭据。已验收构建的两个 ZIP 作为 `v0.5.0` 私有 Release 附件保存，而不是将游戏或测试runtime提交到仓库。

## 最新交付状态

**0.5.0 已实现、部署、验收和打包；本轮没有尚在运行的测试或等待用户处理的重启。** 接下来等用户的新任务，不主动重启游戏、重新验收或增加功能。Git/会话迁移是用户最新要求。

- 已部署正式 DLL，全局 CLI 为 `sp2build`，通用 skill 已同步。
- 正式运行的 `releaseStatus` 是 `released`，已核对 buildId `2d0160ab-8628-4aa6-95b5-d58d087e3e46`。
- DLL SHA256：`B3CC470896AFC6D4DCBBAC0C2F8E6F0895AC34AB53D5ED50CFE1EEDEB03591C5`。
- 最后的后台实机进程已由 `designer.control quit` 正常退出；939 个玩家存档文件核对无新增、丢失或修改。以后应查询实际进程，不把这个历史状态当成当前事实。
- [最终验收报告](Verification-0.5.0.md)、[状态与覆盖边界](Acceptance-Status-0.5.0.md)、[精修调用方法](Precision-Workflow.md)、[完整 CLI 手册](CLI-Usage.md)、[完整过程记录](Execution-0.5.0.md)。
- 冻结目标：[实施计划](Implementation-Plan-0.5.0.md)、[验收方案](Acceptance-Plan-0.5.0.md)。历史失败保留，不代表现版本仍未修好。

## 用户希望达到什么

为 SimplePlanes 2 提供跨 Agent 平台的建造工具。Agent 要理解整个飞机及局部组件、发现全部可用零件的参数，并安全精细地增删改部件、属性、位置、连接、变量和对称关系。最终希望辅助 C17 这类高还原度工程；不只是拼出大致轮廓。

已确定：**全部产品能力通过 CLI 提供，独立 BepInEx DLL 在游戏内执行，附可导入的 skill**。无需另做 MCP 层。未来可扩展游戏其他场景，当前产品重点仍是设计器中已加载的载具。查询存档列表和原生加载已获需求扩展许可，仍不直接编辑未加载的存档 XML。

用户最初提供过真实的 Fennec2 XML；随后用 Super Wasp、从零建造的双涡桨测试机和玩家 C17 验证。早期父工作区中失败的 CLI 探索不等于当前工具；当前完整实现集中在本目录。

## 已有能力和重要语义

1. **发现与读取**：当前飞机快照、拓扑、空间几何、部件参数、玩家选中件；完整原生零件库的大类/小类、列表、介绍、模板属性，包括当前飞机未使用的类型；版本化离线零件与 Funky Trees 知识。
2. **安全编辑**：增删零件、属性/连接编辑、批次事务、异步任务状态、撤销与检查点回滚；全局变量及部件输出绑定、命名。写操作使用当前 session/revision 和唯一 requestId。
3. **复杂形状**：机身截面、裁切/倒角、机翼与翼型、控制面、原生对称；用具名参数和合法性检查减少直接写 XML。更新后重建网格、碰撞和设计器缓存，不能把旧鼠标拾取区域当成正常限制。
4. **装配语义**：挂点给局部位置、法线/轴及可识别的机构归属；转轴/铰链需区分外壳和转动部分。连接只建立拓扑/关节，不自动把两个部件吸附重合。物理位置另用 transform 控制；不能用连接图 BFS 推断翼下支撑归属，需几何/射线与外观证据。
5. **范围与引用**：`parts assembly` 对有原生归属的支持类型返回明确范围与外部连接，`part.delete assembly:true` 显式删除这些范围；不支持的类型报错。ID 可能复用，批次返回 `reusedPartIds`；新件用新的 temporaryId，旧 revision 的 ID 列表不能直接沿用。
6. **外观理解**：`visual capture` 对一组或多组部件生成分析图，保留相对空间关系，必要时推荐细节图；颜色是分析色。`designer capture` 用原生相机和材质，支持方向、正交/透视及固定取景，之后恢复玩家相机。必须实际打开图片后才能说看过；屏幕菜单、鼠标、独立 gizmo 相机不合成。
7. **三心**：`craft centers` 返回质量/升力/推力中心、相对关系与来源，可附图和前后比较。设计器升力中心不是中性点，不能直接认证静稳定或可飞行性。
8. **0.5.0 精修**：有效属性 discovery、原生属性适配、窗体/文字/贴花/整流罩与选定机构参数、材质槽/纹理/发光、局部刚性组与坐标系/枢轴、挂点对齐、投射体位姿、网格间隙/截面/接缝/对称测量、差异和固定视图循环。
9. **无需桌面控制**：`designer crafts` 返回存档元数据；`designer control` 支持 enter/load/select/menu/quit。加载需新 session，丢弃当前编辑需显式守卫。插件不能在游戏尚未启动时自行启动自己；获授权的测试可用隐藏本地进程启动器。
10. **契约**：`commands list` 区分 CLI 命令和 operation kind，`commands schema --command ...` / `--operation ...` 查询各自 schema。例如 CLI `connections.connect` 对应 operation `connection.connect`。名称可改且不唯一，类型判断看 `type`，不用显示名猜引擎/挂架角色。

完整入口以当前 `sp2build commands list` 和 schema 为准；上述摘要不是参数契约。不要把历史临时开发 build 的名称或示例部件 ID 当成现状。

## 关键历史教训

- 早期 DSH 反馈推动了 ID 复用提示、细节图推荐、输出 schema、命令别名与射线命中信息改进。
- 曾出现双飞机残留，已引入场景实例健康检查和重建/恢复修复；只看部件数或导出网格不足以证明实时视口正常。
- 引擎选择曾不符合用户预期。现在 skill 要求综合用途、原生分类/介绍、组件簇和安装间隙选择，不能只挑容易调用的模板。
- 原生保存 AutoRecenter 会整体平移飞机及更新 revision；对称平面必须由原生主控/镜像偏移求得，不能用全机包围盒中心代替。已修复旧对称缓存带来的首轮错误。
- 用户起初允许与 DSH 后端交流，后来明确改为我们自行验收、不再调用 DSH。旧 token 不复制、不使用；`tests/dsh_feedback.py` 等仅保留为历史脚本。
- DLL 热更新曾讨论，用户决定暂不实现。源码/DLL更新仍需重启，飞机内容的实时刷新则必须正常工作。

## 0.5.0 证据和局限

- 94/94 必需通用适配字段有代表场景原生正向及负向证据；471 项非法输入、17 种腿样式的 27 项检查通过。**94 不是全部 4529 个类型/属性对已全面认证**。索引在 `knowledge/native-adapter-evidence.json`，历史目录分母在 `knowledge/editable-coverage.json`。
- E1 机头玻璃、E2 挂架/吊舱/贴花、E3 腿轮机构，各 3 个固定起点、各 2 轮局部收敛。是开发者自验，不是 DSH/外部 Agent 盲测，不是用户对整机外观的批准。
- 同一 874 件构型、8 件 raw 编辑，两版各 30 样本，中位数 11.971→3.874 秒，降低 67.64%；不外推所有操作性能。
- dev24 连续 250 轮、752 项状态/恢复检查通过；13 张原生图和曲线已实看。正式 DLL 另通过 3 项隐藏入口、9 项缩放恢复、16 项导航、18 项组合恢复、14 组网格原生对照及 55 项表达式对照。
- C#核心和74项Python测试通过；长测1283份及最终回归217份产品返回schema零错误。
- 修复两个累积来源：`NativeMeshLifetime.cs` 保证临时原生 MeshGL 析构；`DesignerExpressionLifetime.cs` / `ExpressionTemplates.cs` 对原生表达式使用有界模板、每次独立绑定常量。仅在已核查模块及 Designer 范围启用，未知模块禁用兼容补丁；不改变原生解析/求值规则。
- 内存验收仅针对固定有限工作负载。默认 Windows 堆/对象/模板不再持续累积，但私有内存不是平线：满容量后125样本净增281.596MB，含Unity扩容；末30轮OLS +0.372MB/轮。30次只截图最终私有保留+211.608MB，期间有释放，随后60秒空闲不变。扩容确切分配者未归因，**不可表述为全局无泄漏**。dev22/dev23失败未删。
- 本版不承诺从单张照片恢复真实尺寸、全目录/Mod属性完全可写、完整Animator关键帧编辑、机构全轨迹无碰撞、飞行稳定性认证或自动完成整机C17复刻。

## 工作区、部署和构建

| 用途 | 本机路径 |
| --- | --- |
| 独立项目 | `D:\codeSpace\sp2\SP2BuildAssistant` |
| 游戏/程序集 | `D:\apps\steam\steamapps\common\SimplePlanes 2` |
| 反编译只读参考 | `D:\codeSpace\sp2\Game` |
| 已部署插件 | 游戏目录下 `BepInEx\plugins\SP2BuildAssistant.dll` |
| 全局 CLI | `C:\Users\30023\.sp2build\bin\sp2build.cmd` |
| 已安装 CLI/知识/skill | `C:\Users\30023\.sp2build\app` |
| 通用 skill | `C:\Users\30023\.agents\skills\sp2-build-assistant` |
| 本地原始证据 | 本仓库 `tests/artifacts/precision-0.5.0/` |

游戏版本0.7.8.103/XML25/Windows Mono/BepInEx5；C#7.3、Roslyn与本地游戏程序集编译，CLI运行时Python3.10+标准库。`build.ps1`可传`-GameDir`和`-Csc`；机器默认路径见脚本。`install.ps1 -InstallSkill`部署DLL、全局入口和skill；`package.ps1 -Version 0.5.0`生成完整/skill ZIP。正式构建不得带`-AcceptanceHooks`。

源码分层：`bridge/`为主线程API/属性/几何/渲染/恢复；`cli/`为发现、传输、契约和命令入口；`skills/`为跨平台Agent说明；`knowledge/`为版本化元数据；`tools/`生成知识索引；`tests/`为离线测试及实机验收脚本。知识生成器及某些旧测试依赖本机只读源码/历史夹具；仓库克隆本身并不包含游戏或玩家飞机。

构建输出、`dist/`、测试依赖和`tests/artifacts/`不纳入Git。**不要递归删除测试runtime：内有指向真实游戏资源的junction。** 原始证据留在本机，远端保存摘要和复验代码；两份已验收0.5.0 ZIP保存为私有Release附件。

## 接续操作原则

先读根目录`AGENTS.md`。用户不希望工具占用桌面：不要computer use、窗口激活、键鼠模拟或调用DSH。已授权任务中可通过插件启停/加载/截图/选择，无法运行插件时用隐藏本地启动器；未获新任务时不主动启动游戏。

写入前确认当前飞机、session/revision和授权范围；实机回归只动命名原生测试副本，不直接修改保存的XML。程序成功、实机几何正确、图像看过和用户审美达标要分开表述。测试不通过先保存证据，定位后针对修复复验，不反复重跑已通过的无关矩阵。

新会话先简短确认已接续以上背景，等待用户的新需求即可。
