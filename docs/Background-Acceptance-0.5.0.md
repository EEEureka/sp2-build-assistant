# 不占用桌面的后台验收

2026-10-04：用户要求后续不使用 computer use，以便同时使用电脑。此约束覆盖模拟鼠标/键盘、激活窗口等替代方式；不用 Win32 输入模拟绕过它。保留现有真实鼠标测试的历史证据。

## 最新进展（dev23，2026-10-05）

宿主1.0.5加入受固定测试构型守卫的`mesh-lifetime-reference`：以未修改的原生Burst实现和插件修补实现比较14组完整网格输出，并在小型合成网格上各转换100次统计默认堆增量。实机结果为原路径+286143字节、修补路径+0字节；过滤/不过滤输出均一致。这是T18发现原生MeshGL析构缺失后的独立参考，诊断代码不进入正式DLL。C17前后四视图、30轮编辑恢复已完成，新的250轮长测仍在执行；不据此局部结果宣布整版通过。

宿主1.0.4已加入诊断入口`heap-inventory`，仅允许已打开的命名测试副本。独立原生`SP2HeapProbe.dll`在单次调用中统计默认Windows堆的已用块、空闲块和区域提交量；不遍历第三方私有堆、不读取内存内容、不强制GC或压缩堆。按[HeapWalk](https://learn.microsoft.com/en-us/windows/win32/api/heapapi/nf-heapapi-heapwalk)约定，遍历持锁、结束释放锁，超出预算标记为部分结果。它不能涵盖自定义分配器、其他堆或GPU内存，区域提交量也不包含没有REGION标志的大块分配。12项独立检查及无钩子dev22的实机调用已通过；仍需结合受控对照归因，不能单凭此计数宣布T18通过。两个测试DLL均不进入发行包。

`tests/precision_heap_observation.py`随后区分空闲、只读查询与编辑/恢复；`tests/process_gpu_memory.ps1`记录当前PID的Windows GPU计数器。不同计数器有重叠，不与OS私有字节相加。它们补充归因，不替代T18连续验收。

宿主1.0.6的`load-function-tree-control`仅在原生加载测试副本期间暂用游戏已有的函数树执行路径，finally恢复原开关。1.0.7增加`expression-template-reference`，在真实Unity Mono内对照原始Parser反向补丁和候选编译模板；只用自建上下文，检查重复求值和对象绑定，未驱动玩家输入或飞行遥测。宿主及所有原生参考入口仍不进入发行包。

宿主1.0.3增加专用进程的物理输入隔离：原生 `AllowKeyboardInputs` 返回false，跳过 `Designer.HandleInput`，禁止从剪贴板/URL加载。原因是1.0.1长测在第79轮被会话变化中断，日志出现 `Loading URL: HELLDIVERS`，而飞机仍是C17副本；没有证据证明加载了该名称的飞机。batchmode本身不足以防止桌面快捷键影响这个游戏。新宿主已在实机确认拦截计数增长，导航16项及三个视图通过；它不改变普通游戏的玩家输入，也不修改桥接DLL方法。原中断长测只有78个完整循环，不计为250轮通过；939个存档文件保持不变。

dev22修复起落架样式编辑忽略modifier同步禁用标志的问题。原生面板开关作为独立参考，4种开关/传播组合完整XML对照及恢复共7项通过；无钩子DLL缩放恢复9项、隐藏验收入口拒绝3项通过。新版长测使用1.0.3宿主重新开始，尚未据此关闭T18。

用户随后明确授权通过插件打开/关闭游戏、加载飞机、进入设计器和选择组件，继续禁止 computer use。新增正式工具入口 `designer.crafts`（原生存档目录元数据）和 `designer.control`（enter/load/select/menu/quit）。工具仍仅编辑原生设计器中已经加载的飞机，不提供离线存档读写。调用约束见 skill 的 `references/designer-navigation.md`。

`tests/host/start.ps1` 在独立运行目录启动真实 Unity 游戏，使用 `-batchmode` 保留 GPU、不创建交互窗口。进程尚未启动时 DLL 无法执行，因此仅进程引导由测试启动器完成；进入游戏后的操作均经全局 CLI 与插件。没有模拟键鼠或激活窗口。运行目录包含到原生游戏资源的只读使用联接，不能递归清理以免误触原文件。

独立测试插件 `tests/host/AcceptanceHost.cs` 只在 batch-mode 且明确设置一次性认证凭据时启用。它调用原生加载器打开预先通过游戏建立的固定测试副本，阻止该测试进程的 Save/Autosave/Quicksave/SaveCraft，以保护玩家文件。它不进入正式发行包；认证文件不进入证据分发。1.0.1宿主可配合原始0.4.11和新版桥接DLL，不对桥接DLL任何方法打补丁，保留原始传输端口和编辑逻辑。旧DLL原文件哈希保留，性能准备耗时另列。

dev21已完成16项导航/选择检查及原生三视图实看；94个必需属性适配字段均有正向原生参考和负向用例，详见 `knowledge/native-adapter-evidence.json`。17个原生起落架样式完整状态对照通过。dev19、dev20、dev21三个测试进程退出后各审计939个玩家存档文件，均无新增、删除或内容改变。以下dev19灰图等失败记录保留，不由后续通过覆盖。

已运行：`dev19-background-native-ui` 8项原生属性/Undo/Redo/重载检查通过；`dev19-designer-control-b` 16项原生导航、选择、守卫和恢复检查通过。其末尾截图返回成功但实际为灰图，Unity日志有D3D11 `0x887A0005` 创建buffer/texture失败；该图不计作视觉通过。经产品 `designer.control quit` 退出并确认进程结束，独立新进程恢复正常渲染。故障原因尚不能归为插件或显卡驱动中的某一个。

`dev19-night-emission-c` 已执行实际GPU分支对照：用原生Enviro使用的 `_DAY_NIGHT_VALUE`（0夜/1日）驱动材质shader，6张原生图均已打开；对应分支约200801像素明显变化，非对应分支逐像素相同。完整飞机和原uniform恢复通过。这证明材质昼夜发光分支，不证明飞行天气或真实时间推进。此前两次测试准备错误（SolidColor颜色级finish字段/只涂不可见槽）和一次缺Pillow分析依赖均保留，未列为通过。

原生参考现在绑定真实 PartPropertiesPanel/GenericPartProperties 控件，因此包含铰链的动态MaxRange和资源选项；输出 `native_ui_controls_api_not_desktop_input`。仍不证明鼠标拾取、拖拽量化、屏幕布局。`dev18-native-field-matrix` 145通过/2失败，失败来自参考脚本使用静态0..1范围；dev19正在复验和扩充，不据此前数量宣称完整字段认证。

## dev17历史状态（以下是当时记录）

- 当前打开的是 `VLS128s`，1539 件，运行 dev16；与此前三件 F2 验收副本不同。因此本轮在它上面只做读取和恢复相机的截图，没有属性写入、切换载具、保存或重启游戏。
- dev17 增加开发验收专用 `sp2build acceptance native --input REQUEST.json`。普通 CLI 命令和 GUI 均可继续使用；新入口必须实际加载 dev17 验收 DLL，部署文件不等于加载。
- DLL 更新仍需重启。没有实现热更新，也没有通过进程注入绕过这一限制。首次进入设计器/切换保存的测试飞机目前没有后台入口；不能据本文宣称全流程无人值守已经完成。
- 发布构建通过条件编译移除后台原生参考 setter、异步动作及反射发现代码，仅保留 `acceptance_build_required` 拒绝入口。此入口不是正式版的新通用编辑接口。

## 可以迁移的操作及证据边界

| 操作 | 后台方式 | 本轮状态 / 能证明什么 |
| --- | --- | --- |
| 原生截图、固定取景、模型检查 | 已有 `designer capture`，打开输出文件 | dev16 已在当前1539件构型连续读取/截图；无需前台窗口或桌面截图 |
| 属性、完整状态和内存采样 | 已有查询，配合只读进程内存计数 | 四组各6轮；14项状态/相机检查通过，不等于长期内存已通过 |
| 原生 Undo / Redo | `acceptance native` 的 `undo` / `redo`，调用游戏 Designer 方法 | dev17 已实现、编译；实机待加载。检查原生历史目标及会话语义，不冒充点击按钮 |
| 原生重载当前测试副本 | `reload` 以当前内存中的原生 XML 调用 `Designer.LoadXml` | 不接受路径、外来XML或保存的其他载具。应保持内容、建立新会话、使旧检查点过期；实机待验收 |
| 属性参考值与回调对照 | `inspect` / `property` 使用游戏自己的 ConfigurableProperty 发现及 Changing→SetValue→Changed 链 | 首版仅数值滑块/微调控件、布尔/枚举控件。独立于生产 PropertyRegistry/NativePropertyAdapter；不经过实际屏幕控件，不能证明UI布局、量化步长或输入格式 |
| 材质/贴花等自定义面板 | 仍需逐类开发独立原生参考路径 | 不将通用原始字段赋值宣称为完整面板等价；颜色/资源/嵌套Pose暂不由本测试setter写入 |
| 鼠标真实拾取 | 历史实鼠标证据保留；自动化可测射线/碰撞体 | 射线不能替代鼠标事件/遮挡/焦点链验证；新增鼠标交互测试暂停，不使用后台鼠标注入 |
| 夜间真实发光 | 尚未完成后台场景条件适配 | ThemeScript把日/夜发光分别传入材质数据；改变设计器天空或声明 `IsNight` 不足以证明夜间shader分支被执行 |
| 0.4.11性能比较 | 仍需独立且两版相同的基线恢复机制 | dev17命令不在原版0.4.11内，不能说已解决旧版对照；不能补改旧版后冒充原发布版本的测量 |

## 后台原生入口

所有请求必须提供新 requestId、当前 session/revision 和精确的 `expectedCraftName`。当前飞机的名称还必须以 `SP2Build 050 Precision Lab` 开头。玩家当前的 `VLS128s` 会被拒绝。入口不会自动改名或打开别的飞机。

先查询：

```powershell
sp2build designer status --json
sp2build commands schema --command acceptance.native
sp2build acceptance native --input native-inspect.json --json
```

`native-inspect.json` 示例（ID和版本守卫必须从当前副本重新取得）：

```json
{
  "craftSessionId": "FROM_CURRENT_SNAPSHOT",
  "expectedRevision": 1,
  "expectedCraftName": "SP2Build 050 Precision Lab F2",
  "requestId": "UNIQUE_REQUEST_ID",
  "action": "inspect",
  "partId": 4,
  "modifierType": "ProceduralWindowData",
  "modifierIndex": 0
}
```

`inspect` 返回原生 `member`（如 `_height`）、控件类型、可见性、当前值和 `referenceSetterSupported`。写入使用 `action: "property"` 加上 `member` 与 `value`；每次仅操作一个原生modifier的一项属性，关闭该次属性的对称传播并恢复原对称开关。生产工具的 `properties.set` 仍使用 `ProceduralWindow[0].height`，两种命名故意独立，避免拿同一个适配器作为自己的参考答案。

Undo/Redo/reload请求只含公共守卫、精确副本名、requestId及action。任务通过同一CLI队列执行，可查询operation状态；重试相同requestId不会重复执行。后台原生修改失败后可能标记stateUncertain，须读取错误和当前状态，使用已有明确检查点恢复，禁止继续写入。这里不隐式调用生产恢复算法来掩盖原生参考路径失败。

## 可复用脚本

- `tests/precision_background_readonly.py RUN 6`：空闲/属性/快照/原生截图四组诊断，当前任意已打开飞机都可使用；状态变化会停止，不回滚可能来自玩家的修改。
- `tests/precision_background_native.py RUN`：严格要求已加载dev17且当前为原始三件F2；新增临时窗体，检查原生参考setter、Undo/Redo、生产setter完整XML对照，再回滚原始三件，最后原生重载及旧session拒绝。**本轮仅准备，未冒充已经实机运行。**
- `tests/verify_native_acceptance_build.ps1`：直接检查两种编译产物，证明发行构建没有原生修改实现；不启动游戏。

Python仅运行测试编排脚本；脚本内部的游戏操作始终通过已安装的全局 `sp2build`，没有改为直接调用CLI源码。可选JSON Schema验证依赖在 `tests/.deps` 内，不加入CLI运行依赖或修改全局Python环境。

后续关闭对应验收项仍需：加载dev17→确认测试副本→运行后台参考与生产路径对照→审阅图像/网格及完整状态→恢复并核对。编译成功、契约测试通过以及历史UI证据均不能替代新入口的实机执行。
