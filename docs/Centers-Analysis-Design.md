# 当前飞机三心：场景、接口与呈现设计

日期：2026-10-02。状态：**首阶段已实现于 0.4.0，离线验证后部署；按用户要求，本轮不启动游戏验收**。本文保留场景、源码依据和后续设计；实际命令契约与首版边界见 [三心使用手册](Centers-Usage.md)。

用户确认：读取当前飞机的升力中心、推力中心、重心；重点帮助 Agent 理解三者相对位置及其对设计判断的意义，并授权首版实现及部署。后续力向量、载荷预测、气动求解仍为规划。首版比较以数值前后差为准，图片仅绘制当前样本；贡献排序暂为固定规则。

## 1 建议结论

提供一个主入口 `sp2build craft centers`，以**当前设计器的三心为基准**，同时交付：

1. 默认摘要：三心、坐标系、相对偏移、统计范围、算法含义和可判断范围；一次调用即可回答“谁在谁前面/上面/左边，相差多少”。
2. 按需展开：质量、机翼与推进源的贡献，帮助解释“为什么在这里、哪个部件值得检查”。
3. 按需出图：同一次采集的真实飞机网格加三心标注，生成侧/俯/前视图及三心局部放大图。
4. 修改前后比较：比较已有三心报告与当前打开飞机的新报告，主要展示三心相对关系的变化。

**三心布局分析与静稳定性计算分开。** 首版能精确说明游戏设计器标记及几何偏移；不能把设计器 CoL 当作整机中性点，或凭一张布局图返回 `stable:true`。

## 2 Agent 使用场景

| 场景与玩家问题 | Agent 真正需要的内容 | 建议呈现/调用 |
|---|---|---|
| 初检：“这架飞机三心合理吗？” | CoL/CoT 相对 CoM 的纵向、横向、垂向差；口径及缺失项 | 默认摘要，必要时三视图；输出布局事实和待验证点 |
| 改翼、移发动机、加配重：“改完往哪个方向变了？” | 前后中心与相对间距，统一算法、坐标和载荷配置 | 保存 before 报告，修改后带 baseline 查询；列出变化量 |
| 挂载不对称：“挂上吊舱后为什么往一边偏？” | 左右质量偏置，选中零件/原生组件的质量和力臂 | `--detail contributors --metric mass`，焦点高亮；不从名称猜零件类型 |
| 油门耦合：“加油门为什么抬头/偏航？” | CoT 偏移，以及各推进源的实际作用点、方向和可比推力 | 首版报告位置；没有经过验证的力向量时，不推导俯仰/偏航力矩 |
| 垂直起降、多发动机、混合动力：“悬停推力对得上重心吗？” | 合推力方向、作用线、关于 CoM 的合力矩，推进类型和启用条件 | 三心可辅助定位；混合权重/缺少方向时明确不可判定，不能以点重合证明可悬停 |
| 燃油/弹药/投放变化：“燃油耗尽或投掉挂载会怎样？” | 明确资源假设下的质量分布与 CoM 变化 | 后续无写入工况预测；当前先支持实际编辑后的报告对比，不能把 EmptyMass 当空油质量 |
| 针对选中件：“这个机翼对升力中心影响多大？” | 原生升力标记的权重份额、部件位置及与全机 CoM 的关系 | 焦点过滤贡献，保留全机三心；不把局部三心冒充全机结果 |
| 真正静稳定性：“静稳定裕度多少？” | 给定工况与操纵约束下的整机中性点或俯仰力矩导数、参考弦长 | 单独的后续气动分析；首版返回 not_assessed 及缺失依据 |

## 3 源码核查：三个数值的实际含义

### 3.1 重心 CoM

`GroupCenterOfMass` 按每件 `LoadedMass` 和 `part.transform.TransformPoint(part.CenterOfMass)` 计算加权中心。**不能用零件原点、包围盒中心或所有零件的简单平均代替。** `PartData.LoadedMass` 为 `(PartType.Mass + ModifierMass) * MassScale`，内部质量到 kg 使用 `Constants.MassScale = 0.01`；不能直接把内部值标成 kg。

`AircraftScript.RebuildAircraftStructure` 从主驾驶舱建立连接图，将其成员写入 `Aircraft.Parts` 并构建 `CenterOfMass`。未连通零件保留在 `InitiallyDisconnectedParts`。因此默认应复现原生口径，并返回实际参与/排除的范围，而非默认把设计器画面上的全部散件算进去。无主驾驶舱、总质量为零、非有限输入需要明确 unavailable/partial，不能将原生回退原点解释成有效重心。

来源：[GroupCenterOfMass.cs](../../Game/Assets/Scripts/Craft/GroupCenterOfMass.cs:33)、[PartData.cs](../../Game/Assets/Scripts/Craft/Parts/PartData.cs:108)、[AircraftScript.cs](../../Game/Assets/Scripts/Craft/AircraftScript.cs:1933)、[Constants.cs](../../Game/Assets/Scripts/Constants.cs:344)。

### 3.2 设计器升力中心 CoL

`Designer.RecalculateCenterOfLift` 对 `Aircraft.Wings` 调用 `GetProjectedAreaMoment(Vector3.up, out centre)`，权重为返回的投影面积乘 `LiftScale`。`JWingScript` 使用原生截面几何和四分之一弦线位置构造该面积矩。它不在这里求某个速度/迎角下的实际升力，也不计算升力曲线斜率、尾翼下洗、零升力俯仰力矩或整机中性点。

算法必须标为 `designer_projected_area_lift_scale`。贡献字段可叫 `nativeWeightFraction`，不能叫“实际升力百分比”，权重不能标 N。原生投影轴是**世界 +Y**；切换输出坐标系只变换呈现，不能悄悄改成新坐标系 +Y 重新算出另一个中心。

另一个名字很容易误导的接口是 `AircraftScript.GetAerodynamicCenter()`：其遍历调用 `GetCentreOfLift`，而当前 `JWingScript.GetCentreOfLift` 直接返回零权重/原点，**不可将这个接口作为新版程序化机翼的设计器 CoL 数据源**。

旧 `WingScript.GetProjectedAreaMoment` 在当前反编译文本中出现 `vector - vector`，按该文本会使投影面积归零；这是实现前需要对当前 DLL/IL 和实机核实的分支，暂不将其定性为所有版本的游戏缺陷。遇到旧翼/未知 Mod 应报告覆盖不足，不静默改用自创面积公式却声称原生一致。

来源：[Designer.cs](../../Game/Assets/Scripts/Design/Designer.cs:1231)、[JWingScript.cs](../../Game/Assets/Scripts/Craft/Parts/Modifiers/JWingScript.cs:163)、[WingScript.cs](../../Game/Assets/Scripts/Craft/Parts/Modifiers/WingScript.cs:168)、[AircraftScript.cs](../../Game/Assets/Scripts/Craft/AircraftScript.cs:1121)。

### 3.3 设计器推力中心 CoT

`Designer.RecalculateCenterOfThrust` 汇总 `IDesignerThrust` 的作用位置与标量权重，还加入旧 VTOL 喷口的加权位置。权重并不统一为物理推力：程序化喷气发动机使用海平面静推力估计；程序化螺旋桨使用 `Diameter² * BladeCount`；旧发动机使用 `Engine.Power`。原生 UI 已对混合类型、多种螺旋桨配置显示近似警告。

因此需保留 `native_weighted_position` 口径，返回发动机类型及权重含义，混合权重总和不能标为 N 或推重比。`IDesignerThrust` 本身没有推力方向，**CoT 点与 CoM 的距离不是推力力臂**；力臂是 CoM 到作用线的垂直距离。

范围也有特例：主循环遍历 `Aircraft.Parts`，但旧 `VtolManagerScript.Refresh` 通过 `GetComponentsInChildren(..., includeInactive:true)` 收集喷口/导流发动机，不显式按主驾驶舱连通性过滤。各中心需有独立参与范围；若发现 CoT 涉及未连通/非活动对象，输出原生口径例外。不能自行去重或缩小旧 VTOL 范围后仍宣称与原生标记一致；零喷口、潜在重复计入要做专项验证。

来源：[Designer.cs](../../Game/Assets/Scripts/Design/Designer.cs:1261)、[IDesignerThrust.cs](../../Game/Assets/Scripts/Craft/Parts/Modifiers/IDesignerThrust.cs:5)、[JetEngineScript.cs](../../Game/Assets/Scripts/Craft/Parts/Modifiers/Propulsion/Jet/JetEngineScript.cs:55)、[PropellerAssemblyScript.cs](../../Game/Assets/Scripts/Craft/Parts/Modifiers/Propulsion/Propeller/PropellerAssemblyScript.cs:296)、[EngineScript.cs](../../Game/Assets/Scripts/Craft/Parts/Modifiers/EngineScript.cs:17)、[VtolManagerScript.cs](../../Game/Assets/Scripts/Craft/VtolManagerScript.cs:30)。

### 3.4 能判断到哪里

纵向静稳定关注配平附近、操纵条件固定时，迎角扰动是否产生恢复俯仰力矩。常规符号下，判据涉及 `dCm/dα < 0`；等价的中性点/重心判断也要求明确模型和条件。设计器面积加权 CoL 不满足直接替代中性点的条件。也不能把 CoM–CoL 距离除以某段弦长命名为 staticMargin。

首版 `assessment.longitudinalStaticStability` 和 `assessment.trim` 均允许返回 `not_assessed`，附机器可读原因；同时给出已经确定的布局事实。工具不把“暂时不能判定静稳定”混成“读不到三心”。[MIT 静稳定性课程](https://live.ocw.mit.edu/courses/16-333-aircraft-stability-and-control-fall-2004/99dac83da0ad7eb8906ebac40e9e6ae1_lecture_2.pdf)；关于压力中心随迎角变化、气动中心与力矩的区别见 [NASA Aerodynamic Center](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/aerodynamic-center/)。

## 4 CLI 设计

以下入口已在 **0.4.0** 实现。保持现有 `group command` 形式；不新增 MCP，也不要求 Agent 调用 Python 源文件。

```powershell
# 一次获取三心、相对关系、来源与判断边界
sp2build craft centers

# 查影响重心最大的贡献项；limit/offset 只分页贡献，不改变中心统计范围
sp2build craft centers --detail contributors --metric mass --limit 20 --offset 0

# 解释玩家当前选中件；仍输出全机三心
sp2build craft centers --detail contributors --focus selected

# 同一次报告采集附带三心视图，文件交付沿用 visual capture
sp2build craft centers --images --output-dir ./centers-view

# 实际编辑前后比较：baseline 是工具报告，不是飞机 XML
sp2build craft centers --output before-centers.json
# 此处通过已有 guarded batch 进行用户要求的编辑
sp2build craft centers --baseline before-centers.json --output after-centers.json

sp2build commands schema --command craft.centers
```

| 参数 | 建议语义 |
|---|---|
| detail | summary（默认）/ contributors；中心、关系、关键缺失与判断边界始终返回 |
| metric | mass / lift / thrust / all，默认 all；只过滤贡献明细 |
| focus | all（默认）/ selected；精确零件集合或原生 assembly 用 JSON 输入；不暗中扩展整张连接图 |
| limit / offset | 明细分页，默认 20；返回 total/returned/truncated/nextOffset；部分清单不等于计算不完整 |
| frame | JSON 输入沿用现有 visual 的 world / part+partId；默认 world，返回真实矩阵、轴标签和朝向依据，忽略参考件缩放 |
| images | 可选布尔值；复用视觉采集及文件下载，读取结果与图片必须属于同一设计/几何状态 |
| baseline | CLI 读取此前此命令保存的完整成功报告，比较当前对象；无游戏存档访问、无恢复、无切换飞机 |
| craftSessionId / expectedRevision | 可选一致性守卫，复杂输入走 --input；给定则必须匹配，未给定则返回此次实际捕获身份 |

`--images` 内部复用 `visual.capture` 的采集/渲染核心，通过同一主线程采样取得中心和网格；不要在 CLI 先后做两个无守卫调用再拼接。现有 `visual capture --input ...` 可增加 `overlays.centers:true`，复用同一份 CenterReport 与算法，不能各自重算一套。

零件组控制高亮或模型上下文，**不改变全机三心的统计口径**。需要局部中心时，后续另设显式 scope，且标记 subset；首版不把它混入默认入口。

无选择时，三心仍返回，focus 状态为 no_selection。无升力面/无推进源时，该中心 position=null、status=unavailable 并列出原因，其他中心可以成功；不可用中心之间的关系为 null。无设计器、身份冲突或几何尚未稳定则用现有结构化错误机制。

## 5 输出契约与信息层次

### 5.1 默认报告

建议固定如下结构，避免 Agent 猜字段：

- `identity`：沿用 session/revision/fingerprint；另含 `analysisId/calculationVersion/gameVersion/capturedFrame/geometryStamp`。
- `basis`：native_designer、载荷为当前编辑器配置；不是飞行工况；原生升力投影轴 world +Y。
- `frame`：world/part、frameToWorldRows、右/上/前对应的轴与来源。世界 +X/+Y/+Z 的右/上/前仅是设计约定，不从模型形状推断实际机头；参考件可能也不朝机头，必须显式说明。
- `scope`：装配总数、主连通部分、未连通数量；每个中心的 contributorCount/排除原因/coverage。明细按需取，不在默认响应塞全量 XML。
- `centers.com/col/cot`：status、quality、method、positionWorldMeters、positionFrameMeters、contributorCount、reasonCodes。com 可附 massKg；col/cot 附权重语义，不能伪装成测得的力。
- `relations`：colFromCom、cotFromCom、cotFromCol，**都是名字前者减后者**。每项含 deltaFrameMeters、distanceMeters，以及显式的前后/左右/上下解释。解释只在坐标语义成立时生成。
- `assessment`：几何事实、静稳定/配平/推力力矩是否可评估，和缺失依据。不要提供没有物理模型支持的安全分数或稳定等级。
- `comparison`：未请求时 null；请求后说明是否可比，再给当前值、基线值、差值及解释。
- `warnings`：code/severity/message/relatedPartIds，可区分原生近似、范围例外、未知 Mod、无贡献、朝向约定等。
- `visual`：未请求时 null；请求后含 captureId、recommendedImages、manifestPath 和与本报告对应的 analysisId。

所有点使用相同的 frame 和米；判断重合的显示阈值需显式输出，例如 positionRelationToleranceMeters=0.001。此阈值只是避免把浮点噪声写成“偏左”，不表示静稳定裕度、安全容差或测量精度。显示可以四舍五入，JSON 数值保留计算精度。

下面是**虚构数值的核心字段节选**，不是当前飞机实测，也不是完整成功信封；假定设计 +Z 已确认指向机头：

```json
{
  "basis": {
    "mode": "native_designer",
    "loadCondition": "current_editor_configuration",
    "liftProjectionAxisWorld": [0, 1, 0]
  },
  "frame": {"kind": "world", "axisLabels": ["right", "up", "forward"], "orientationBasis": "designer_convention"},
  "centers": {
    "com": {"status": "valid", "quality": "native_mass_weighted", "positionFrameMeters": [0, 0, 0], "massKg": 4700},
    "col": {"status": "valid", "quality": "designer_proxy", "positionFrameMeters": [0, 0.25, -0.4]},
    "cot": {"status": "valid", "quality": "designer_proxy", "positionFrameMeters": [0, -0.12, -2]}
  },
  "relations": {
    "colFromCom": {"deltaFrameMeters": [0, 0.25, -0.4], "description": "升力标记在重心后方 0.40 m、上方 0.25 m"},
    "cotFromCom": {"deltaFrameMeters": [0, -0.12, -2], "description": "推力标记在重心后方 2.00 m、下方 0.12 m"},
    "cotFromCol": {"deltaFrameMeters": [0, -0.37, -1.6], "description": "推力标记在升力标记后方 1.60 m、下方 0.37 m"}
  },
  "assessment": {
    "longitudinalStaticStability": {"status": "not_assessed", "reasonCodes": ["designer_col_is_not_neutral_point", "pitch_moment_derivative_unavailable"], "staticMargin": null},
    "trim": {"status": "not_assessed", "reasonCodes": ["flight_condition_unspecified"]},
    "thrustMoment": {"status": "not_assessed", "reasonCodes": ["force_direction_or_scale_unverified"], "momentNm": null}
  }
}
```

schema 必须同时说明正常、部分可用、不可用、带明细、带图片、带比较的响应；嵌套结构使用具名 $defs，`data` 不留空对象。命令发现明确只读及最低 DLL 版本。旧 DLL 必须返回 unsupported_bridge_feature，不能输出空字段冒充支持。

### 5.2 贡献明细

每项携带 `part:{id,type,typeName,name}`、sourceId（含 modifier/喷口索引，避免同件多源冲突）、positionWorldMeters/FrameMeters、是否纳入及原因。

| 度量 | 额外字段 | 应解释成 |
|---|---|---|
| mass | massKg、massFraction、offsetFromComMeters、massMomentAboutComKgM | 当前质量与质量矩；它不是力矩 N·m |
| lift | projectedAreaSquareMeters（已确认单位时）、liftScale、nativeWeight、nativeWeightFraction | 原生设计器 CoL 的贡献；不是飞行升力份额 |
| thrust | propulsionType、nativeWeight、weightMeaning、nativeWeightFraction、directionStatus | 原生 CoT 标记的权重来源；未知方向保持 null |

原生权重份额只对已纳入且总权重有效的集合计算；混合权重、partial 结果明确归一化基准。被忽略的贡献不能伪造成 0。默认质量按绝对质量矩范数排序，升力/推力按原生权重排序，并返回 sort 定义；用户可切换质量排序。焦点过滤或分页不重新归一化全机份额。

不能仅按“质量最大”建议删件。移/删件预测涉及剩余总质量、位置和其他结构的变化；首版只给贡献依据，由已有受守卫编辑及前后比较验证。

### 5.3 修改前后比较

baseline 必须是同类报告，不接受飞机 XML。CLI 校验信封、字段类型、有限数和算法版本；基线是数据，不执行其中命令。默认要求同 craftSessionId、同口径和可对齐的 frame；跨重启/跨飞机只返回 comparison_not_comparable，不猜对应关系。新报告仍可正常读取，比较失败单独注明。

重点显示：

- CoM/CoL/CoT 的位置前后值，以及三个**相对向量/距离**的变化；整体平移不会被误称为三心关系改善。
- 参考 frame、原生投影轴相对飞机朝向、计算方法或统计范围改变时，标记 basis_changed，停止自动给“更稳定”的趋势结论。世界投影面积会随整机旋转改变，不能把这一变化去掉后声称仍是原生 CoL。
- 参考件删除/重建/ID 复用时，不用数字 ID 自动建立“同一参考件”身份；身份链无法验证则拒绝参考件配准。默认对比不依赖某个部件名称或 ID 的永久性。
- 不能把 changes 中两个总值相减直接归因为某件；只能报告实际变化，明确期间是否有其他编辑。

若日后支持 `%参考弦长`，必须给出弦长数值、来源、选定机翼范围和方法，字段命名为 geometricGapFraction；没有中性点时仍不叫 staticMargin。首版只用米，不自动选主翼或建议万能百分比。

## 6 图像呈现设计

默认图片无需每次生成，`--images` 时提供一张推荐拼图：**侧视图（纵向/垂向）、俯视图（纵向/横向）、前视图（横向/垂向）**，按需附三心区域局部图。可以保留已有斜视图作为外形辅助。

- 飞机浅灰、焦点件高亮；CoM 用红色圆、CoL 用蓝色三角、CoT 用黄色菱形，并直接标注 CoM/CoL/CoT，色盲或灰度场景仍可区别。颜色表示类别，不表示安全等级。
- 每视图带机头/坐标方向、米制尺和投影平面；三心保持原空间位置。标记描边或置顶须写清是信息叠加，不代表标记位于外壳表面。
- 同时显示 CoM→CoL 和 CoM→CoT 的投影虚线与分轴距离；图上投影距离和 JSON 三维距离各自注明，不能因前视图重合就称三点重合。
- 三点很近时用引线避让、联合局部放大；不人为把三点移开。局部图保留三者同一比例，注明与总览的比例差异。
- 标记在飞机轮廓外也保留，自动扩展取景范围；异常远离时总览加单独关系小图，避免飞机缩到无法辨认。不可用中心在图例写 N/A，不画在原点。
- baseline/current 同时绘制时，旧位置为空心、新位置为实心；只有坐标配准已验证才叠加。否则并列图并显著说明不可直接量像素比较。
- 源报告、网格、标记坐标、视图投影参数、每个标记像素位置及可见性写入同一个 manifest。overlay 与原有 Part-ID 图隔离，不污染 visual.pick，不将三心标记当零件返回。
- 小间距详情图进入 recommendedImages；用户只要数值时不强制下载图片。Agent 必须实际打开 PNG 后才声称已经看过。

示意布局（只说明信息位置，并非真实飞机截图）：

```text
┌──────────── 侧视 / +Z 朝右 ────────────┐
│            △ CoL                     │
│            ← 后方 0.40 m → ● CoM    │
│    ◇ CoT                  ↑          │
│    推力标记低于 CoM 0.12 m            │
└──────────────────────────────────────┘
俯视：展示左右偏置；前视：展示左右与高度。
图例：△ 面积加权升力标记，◇ 原生近似推力标记，● 质量重心。
```

## 7 分期及实现方式

**首版建议交付**：原生设计器三心 + 明确统计范围/来源 + 三对相对关系 + 贡献明细 + 报告比较 + 同快照视觉叠加。预计主要复用现有主线程队列、ReadSettled、身份守卫、文件交付和 CPU 网格渲染；新增独立 CenterAnalysis 模块与 CLI/schema/skill 文档。原生三心与当前接口数据基础充分，可行性高；复杂处主要是原生边界、异构推力与图像/报告一致性，不是加权平均本身。

不要读取三心 Gizmo 的 Transform 当唯一数据源：它受 UI 开关和刷新时序影响，原生不可用状态也可能回退原点。应提取原生公式所需的实时贡献，在主线程只读采样，避免调用会切换 Gizmo、选择、相机或运行飞行更新的方法。对有副作用/未验证的旧翼路径单独适配并报告覆盖。

**后续 A：物理推力布局分析**。按发动机类型验证方向、作用点、可比较的 N 单位、油门/反推/矢量/喷口分流语义，再计算 `F=ΣFᵢ` 与 `M_com=Σ((pᵢ-com)×Fᵢ)`，另计可用的反扭矩。不能将异构 DesignerThrust 当成 Fᵢ。非平行推力不能只返回一个“作用中心”：合力近零或存在不能由单一作用线表示的剩余力偶时保留向量/力矩与解释；不制造唯一点。

**后续 B：载荷假设**。对燃油/弹药等逐类定义资源质量与局部质量位置的只读适配。`EmptyMass` 不等于真实无燃油状态：ModifierMass 还可能包含结构与设备质量。假设工况显式保存，不通过实际清空燃油/删除部件再撤销来实现查询。

**后续 C：静稳定/配平分析**。明确速度、密度/Mach、迎角、侧滑、操纵面锁定/自由、推力和气动模型，验证小扰动俯仰力矩导数/中性点及参考弦。属于另一个求解能力，不能从当前三心字段直接推出。动态稳定、失速恢复和飞控闭环稳定也不纳入首版结论。

这些后续能力回应使用场景，但并非本次用户已经要求立即实现的功能，也不阻塞首版三心读取。

## 8 验收建议

1. 将计算结果与原生三心标记比较，检查主连通部分、未连通零件、隐藏件、零件缩放和局部 CoM 偏置；记录各中心实际成员，而不是只比坐标。
2. 对已知质量与位置的临时件做可手算重心案例，验证内部质量→kg、局部点→世界点；编辑后读取新值，恢复后回到基线。
3. 程序化机翼的移位、面积、后掠、二面角与 LiftScale 改动符合原生加权；竖直翼、零面积/无翼、旧翼及未知 Mod 不被当有效原点。
4. 程序化喷气、不同螺旋桨、混合类型及旧 VTOL 分别核对权重和范围，包含零喷口、未连通喷口、非活动对象及重复来源；不返回未经验证的 N 或力矩。
5. 几何更新未完成时不读陈旧值；发生会话/修订冲突时不混拼。三心报告与图片的 identity/geometryStamp/analysisId 一致，期间玩家编辑则标记陈旧。
6. 验证所有三对关系的正负方向和单位；三视图分别核对投影；近重合、遮挡、远离轮廓的中心均可辨认，Part-ID 图不被覆盖。
7. 贡献分页/focus 不影响三心与全局份额。无选择、无发动机、无主驾驶舱、零/负/非有限质量或权重有明确状态，禁止 NaN/Infinity JSON。
8. baseline 比较验证整体平移、frame 变化、整机旋转、参考件 ID 复用、跨会话和不同算法；报告文件读取不能改飞机或加载存档。
9. 输入/输出 schema 覆盖各分支，CLI/skill 仅在实现后发布命令。旧 DLL 明确拒绝。DSH 以真实任务验证一次摘要可回答位置、一次明细能定位贡献，不再手工猜单位/路径。
10. 只读前后比较飞机 XML、选择、相机和撤销历史；不能为获得三心而修改设计或飞行状态。测试写入继续按既有检查点恢复流程，并独立复读。

本方案没有对当前飞机给出三心数值或稳定性结论；没有将源码存在等同于实机已验证。
