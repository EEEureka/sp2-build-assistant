# 0.2.1 验收记录

日期：2026-10-01。游戏 0.7.8.103 / XML 25 / Windows Mono / BepInEx 5.4.23.5。

最终结果：32 组实机功能/边界测试、真实鼠标拾取验收和 52 项离线检查通过。机器汇总见 `tests/artifacts/final-0.2.1-report.json`。

## 当前部署

- 独立插件 `SP2BuildAssistant.dll` 0.2.1 已部署，并由代理通过游戏正常退出、重新启动、返回原飞机设计器后确认加载；无需玩家再次重启。
- 当前运行构建 MVID：`7d738145-f68b-4f25-89cc-8c7b247cc9ea`。
- DLL SHA256：`E02335EA022CF801AAAEADE9DC2FFD4CAB91DFD847C7CE8AAA761AB8DB7EB744`。
- 全局 `sp2build version --json` 返回 0.2.1；CLI 位置为 `%USERPROFILE%/.sp2build/bin/sp2build.cmd`。所有实机脚本通过这个全局命令调用。
- 未修改 Game 反编译参考代码或游戏原程序集。验收仅操作打开的飞机；临时零件在每组结束后恢复检查点。重启使用游戏自己的设计器退出保存流程，没有用外部工具编辑存档。

## 首轮发现与统一修复

先完整执行 0.2.0 的 23 组主验收，19 组通过，4 组控制面新增失败；未中途部署补丁。原始记录：`tests/artifacts/v02-dda1220994/acceptance.json`，同目录保存请求、响应和原始 BepInEx 日志。

StandardFlap、FowlerFlap、BrakeFlap、Slat 共享同一问题：建立连接时游戏同步调用 `JWingScript.FindControlSurfaces → UpdateMeshDesigner → WingBuilder.Generate`；插件在连接之后才写用户尺寸，导致原模板的控制面展长超出目标机翼，抛出 `Attempted to create an interpolated slice out of current range`。四次失败均成功恢复，未留下临时部件。

0.2.1 在连接前应用并校验控制面尺寸，按目标机翼换算铰线、检查展向范围和同侧重叠，再连接和重建。模板选择限定游戏内置零件，避免同类型用户子装配抢先匹配。该修复通过同一游戏中四种控制面的新增、修改和删除复测。

## 主验收：23 / 23 通过

原始记录：`tests/artifacts/v02-9e32aa3187/acceptance.json`，350 份编号调用结果及对应输入。

| 测试场景 | 结果 |
| --- | --- |
| 状态、快照、连接、空间查询、变量、输出、Funky Trees、历史和检查点查询 | 通过 |
| 完整目录、分类、子分类、搜索、原生说明和 schema；本实例 176 个目录项 | 通过，无 schema 导出错误 |
| 当前飞机各实际部件类型的详细读取、复杂状态、渲染/碰撞/编辑器边界 | 通过 |
| HingeRotator、SmallRotator、JointRotator 活动端/外壳端 | 3 组通过 |
| 类型化 Fuselage 拉长和缩短后的实际物理命中 | 新增区域可命中，缩短后旧区域不再命中 |
| 原始属性修改 Fuselage 长度 | 新区域可命中 |
| 显式 craft.refresh 与撤销 | 物理几何随撤销正确恢复 |
| Body、Curved、Cone 的尺寸、角、边、裁剪、平滑等补丁 | 3 组通过；Curved 中间截面非法裁剪被拒绝 |
| 连接/断开、相邻机身端面匹配及同步 | 通过 |
| 镜像组创建、禁用/启用、解绑/关联、左右切面换向、原始属性同步与删除 | 通过 |
| 机翼截面替换、NACA 翼型、插值、圆翼尖 | 通过；NACA0000 拒绝并恢复 |
| StandardFlap、FowlerFlap、BrakeFlap、Slat 新增/修改/删除 | 4 组通过 |
| 多操作事务中后续非法裁剪 | 前面的合法改名也一起恢复 |
| 全局变量增删改排序、部件输出绑定/修改/解绑 | 通过 |
| 重复 requestId、过期 revision | 重复返回同一操作，过期版本拒绝 |
| 最终部件数与选中状态 | 恢复到测试起点 |

## 控制面边界补充：9 / 9 最终通过

四种控制面的超翼展输入均返回 `invalid_control_surface`，恢复后无新增零件；全翼展 `[0, span]` 四种控制面均能生成渲染网格和碰撞体。原始记录：`tests/artifacts/v02-954ce6035a/acceptance.json`。

同侧重叠被明确拒绝；相同范围的前缘 Slat 与后缘 Flap 能共存；另一段后缘 BrakeFlap 能共存；缩短机翼使控制面越界时操作失败并恢复。该组最后的撤销步骤首次因测试传入不存在的 `steps` 参数被 CLI 拒绝，已修正脚本，单独复测通过：`tests/artifacts/v02-3c9419890b/acceptance.json`。撤销仅移除最后添加的控制面，另外两个仍在。前一次失败是测试调用错误，保留原始失败记录，不需要追加 DLL 修订。

长流程达到既有 64 个检查点容量限制时，显式新建返回 `checkpoint_capacity`；后续验收复用开始时保留的检查点。自动 before-checkpoint 达上限会返回 null，普通编辑、原生撤销和已有检查点恢复仍有效。没有通过清除玩家数据规避上限。

## 界面与飞机恢复

使用 computer-use 实际点击飞机左翼，`designer.selection` 返回 JWing-1 / ID 58；原生设计器高亮与查询一致。0.2.0 主验收还确认该选择在多次修改/重建和恢复后保留。空白处点击后返回 null，与原始无选择状态一致。

在 0.2.1 中添加临时 Fuselage / ID 210，先观察长度 1 米的可见范围，再通过 CLI 改为 6 米。鼠标点击新增区域（截图坐标 957,390）后返回选中 ID 210；缩短至 1 米时仍保留选中 ID，再点原坐标后选中其后方的原飞机零件 ID 221，证明旧碰撞区域已释放。图像、高亮和物理射线证据一致。输入/响应位置见 `tests/artifacts/ui-geometry-state.json`，选中查询分别在 `ui-expanded-selection.json` 和 `ui-shrunk-selection.json`。最终已通过原检查点移除临时机身。

最终打开的仍是 Jet Fighter - Adder / 269 个零件，选择为空，stateUncertain=false。与本轮最初快照逐项比较，零件、连接、变量、属性均恢复；XML 并非字节一致：4 个零件的欧拉角有不超过约 0.00002° 的原生往返误差，一处自动生成目标集合的枚举顺序改变；正常退出保存时游戏 `Designer.Save` 重算了根级 size/boundsMin/boundsOffset（宽度缓存 9.890275 → 10.19337 米），这三个字段在重启后、补丁验收前已相同，后续没有改变。未放宽生产快照/版本校验规则。详细差异在 `tests/artifacts/acceptance-final-comparison.json`，最终快照和版本证据为 `acceptance-final.json`、`acceptance-final-status.json`。

## 离线验证与范围

- ShapeCodec 30 项检查通过：字段补丁、方向映射、镜像可逆、裁剪组合、类型/范围/未知字段、厚度单位、翼截面、翼型回调、控制面范围，以及历史真实飞机中 164 件复杂零件读取。
- SnapshotState 12 项检查通过：原生恢复旋转容差、位置严格性、变量顺序及生成集合规范化。
- CLI 10 项检查通过：便捷命令事务信封、操作 schema、射线参数、离线复杂零件目录。共 52 项离线检查通过。
- skill 格式已验证；本补丁不改变 skill 命令契约，继续要求使用全局 `sp2build`。
- 参数清单：11 类复杂部件、81 个源文件引用、1003 条参数证据；运行时目录仍为当前版本权威来源。
- 本轮对称实测为镜像；径向模式未作实机认证。11 类目录有读取和方案不代表全部都有专用写入接口；类型化写入仅覆盖文档列出的 JFuselage、JWing 和四种控制面。
- 未逐一穷举所有参数组合、第三方 Mod、其他游戏版本或飞行效果。检查点仅当前进程/飞机会话有效；重启不保留旧检查点。
