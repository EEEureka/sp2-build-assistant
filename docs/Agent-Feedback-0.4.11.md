# 0.4.10 实机复验、涡桨换装与 0.4.11 修订

后续更新：用户保存重启后已加载0.4.11，原生截图常用流程、相机恢复和动态挂点修复实机通过，FB-042关闭。详见 [0.4.11验收](Verification-0.4.11.md)。以下保留发布前的发现、修订和部署过程，其中待加载状态已被本次复验更新。

2026-10-02。本轮全部由 Codex 直接调用全局 sp2build，未调用 DSH。0.4.10 已实际加载，buildId `7c97a0cd-2f52-4b47-b793-74eec1dec1ee`，PID42672，游戏0.7.8.103/XML25。

## 已通过的运行时复验

FB-041：先确认重启后的单实例，再执行同批多次 Replace → CLI undo；多次 Replace → 非法表达式中途失败并整批恢复；再次多次 Replace → checkpoint rollback。每步 sceneIntegrity 都是 healthy，含 inactive 的实例数和 active 数都为1；恢复后的原始指纹一致。实际游戏窗口也没有旧模型。随后在42件涡桨构型上做两次重建改名，点击**游戏原生撤销按钮**，出现 Undo complete，正式名称与基线指纹恢复、容器仍1个实例。此原生撤销切换了 Aircraft 对象，所以 CLI 会话换新，旧检查点失效，符合会话语义。

FB-040：parts.get、shape.get、未放置小型涡桨 catalog.schema 的有效 inputControllers 已实测。覆盖零/单/双控制器、索引路径、名称/用途；写 zeroOnDeactivate=true 后 XML 省略字段，但新有效读出仍为 true；撤销/回滚恢复正式 false。最终螺旋桨的 Manual Pitch 与 Reverse Thrust 可直接区分。

证据目录：[0.4.10 直接验收](../tests/artifacts/staged-build/direct-0.4.10/)。`acceptance/checks.json` 保存生命周期/输入检查，`native-ui-undo/checks.json` 保存原生撤销复核。测试脚本曾误用 checkpointId 而非 checkpoint 返回字段 id；这属于验证脚本错误，已修正并从尚未执行的 rollback 继续，非工具反馈。最终独立构型复核 [review.json](../tests/artifacts/staged-build/direct-0.4.10/final-verification/review.json) 39项通过。

## 正式双涡桨构型

原军用喷气 #23/#24 已删除。使用原生 `Aircraft Propulsion / Turbo Props / Small Turboprop` 模板 `tpl-0107631356a369e6`，每侧7件，保留短舱、整流罩、涡轴、两个排气、减速箱和螺旋桨。

| 作用 | 右侧 | 左侧 |
| --- | --- | --- |
| 翼下短舱根件 JFuselage-2 |31|38|
| 整流罩 |32|39|
| 小型涡轴核心 |33|40|
| 减速箱 |35|42|
| 四叶桨 |36|43|
| 外侧排气 / 内侧排气 |34 / 37|44 / 41|

根件位置 `[±2.6,3.34,0.65]`，连接各自主翼表面点；autoResize=false，连接后形状/姿态保留。14件分为7个对称组，整体为42件/41连接、全连通、16对启用的对称部件。Turboshaft输入Throttle；原生桨距类型Auto，手动桨距与反推通道明确Disabled且min=max=0，避免继承模板VTOL输入。机械端点类型与拓扑保留，没有按错误元数据强行移动桨轴。

总质量约2293.372 kg，燃油392 L。两侧标称桨径2.54 m；以当前设计器桨叶 mesh AABB 绕轴旋转的保守圆柱范围计算，旋转半径上界1.28333 m，距机身侧面约0.6667 m，距三胎底水平面约0.4343 m；桨叶最靠后的Z仍比主翼/缝翼整体最前包围盒前0.9337 m，比主起落架前1.8334 m。原生右翼短舱局部射线可同时命中短舱与机翼，真实窗口已看图，短舱位于翼下、桨位于前方。**这些只是当前桨距、起落架伸展、水平姿态下的静态检查，不涵盖全桨距/顺桨、压缩行程、抬头离地或试飞**。

同次三心报告：CoL相对CoM为后0.76998 m、上0.18319 m；CoT相对CoM为前1.84466 m、下0.07710 m。这些是原生设计器指标，不能当静稳定余量、真实推力数值或力矩求解。沿用原生flipped翼质量警告和多桨推力中心近似说明。整机图、原生窗口及三心推荐图均已实际查看。

最终数据会话 `dbed609a9d684fba9c7ed3ffad8f387a`、rev1，fp `4d62dfe775846f960c8917d2f361fcc6c1cdb050028858f1e3f65e1d12133723`。独立 Spoiler 仍未实现；现有BrakeFlap不冒充独立扰流板。未试飞。

## 新确认 FB-042：动态挂点返回定义位置，偏离实际句柄

载具/环境为上述42件构型、DLL0.4.10、游戏0.7.8.103、PID42672；原生撤销之后、当前无选择，编辑器保持完整飞机可见。是否玩家另有未保存更改无法由CLI判定，Codex未再执行依赖错误坐标的写入。

完整查询：

```powershell
sp2build parts get --id 35 --json
sp2build parts geometry --id 35 --json
sp2build parts get --id 36 --json
```

`parts.get #35` AP1 原始片段：`localPosition:[0,0.1141,-0.2663]`、`worldPosition:[2.6,3.58297586,1.89486492]`；同一指纹下 `parts.geometry #35` 实际 AttachPoint collider 中心为 `[2.6,3.468876,1.88289]`。数据位置与实际位置相差约0.11473 m。#36连接根点 `[2.6,3.468876,1.880372]`，与实际减速箱输出点仅差0.002518 m。涡轴排气挂点也受相同机制影响。

证据：`final-verification/0022-part-35.json`、`0015-geometry-35.json`、`0023-part-36.json`；各文件以目录实际编号为准，调用索引见calls.jsonl。源码 `Powertrain/UpdateAttachPointsScript.UpdateAttachPoints` 只移动 AttachPointScript.transform，没有同步 AttachPointData.Position；旧插件 Points 方法读的是后者。质量影响：AI会误判轴系错位并移动本来安装正确的零件；效率影响：额外geometry/源码核对。复现范围为两侧减速箱及排气定义/动态句柄差异，首次与最近核验均本轮。

0.4.11 改为按 AttachPointData 引用查找实时 AttachPointScript，localPosition/worldPosition优先从实时transform计算。新增positionSource与definitionLocalPosition；无实时句柄时明确标出定义回退。查询不修改游戏挂点或物理系统。修订已编译、旧输出与新字段契约通过，**实机有效值待加载后复验**。

## 0.4.11 新增原生设计器截图

用户新增需求：从玩家观察角度查看真实设计器场景，可选方位、角度、正交/透视。已实现 `designer capture`，完整调用和输出结构见 [使用文档](Designer-Screenshots.md)。新CLI可发现、schema可查询、skill同步提供；原生渲染/相机恢复必须在加载新DLL后验证。截图不合成屏幕UI和独立gizmo相机，保留native scene camera可见的所有实例；异常sceneIntegrity不阻止诊断截图。

离线验证涵盖18项取景规划、3项新增CLI路由/版本检查、输入/输出契约。相机临时渲染采用try/finally恢复并比对，取消与异常路径释放临时texture；这些代码结构和数学测试不是实机渲染成功的证据。下一次重启后验收：当前视角、三方向正交、自定义透视、局部取景、显式距离/半高、错误输入、下载完整性、相机与飞机/撤销记录保持，再复验FB-042动态挂点。

## 发布与部署

274项离线回归（222 C# + 52 Python）、106项通用契约、32项形状契约、17项新截图/挂点契约，以及本轮127份实际返回的最新输出契约验证通过。skill校验通过。0.4.11全局CLI、DLL和skill已部署，12个CLI/skill文件哈希一致；DLL SHA256 `3EB3A44332A308850CBCD57FFD0447C1CC01944935306C8CC80FCC09FBF56EB7`。运行中仍0.4.10、当前飞机身份与指纹未变；新CLI已验证对旧DLL的截图请求明确拒绝，没有发送新功能请求或重启游戏。部署证据 [deployment.json](../tests/artifacts/releases/0.4.11/deployment.json)。新DLL的原生截图和挂点修复等待用户保存当前42件Aircraft、重启并进入同一飞机设计器后验收。
