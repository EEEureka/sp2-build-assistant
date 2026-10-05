# SP2 Build Assistant 0.5.0 落地计划

设计日期：2026-10-03，代码基线0.4.11。2026-10-04状态：已实施并部署开发构建，正在实机验收，尚未正式发布；当前结果见[验收状态总览](Acceptance-Status-0.5.0.md)及[实施记录](Execution-0.5.0.md)。本文保留原始范围和标准，不因部分测试通过自动标记完成。

本版目标是让 Agent 能在当前设计器飞机上，可靠完成机头、驾驶舱玻璃、翼面、吊舱和机械附件等区域的精细调整，并能测量结果、比较版本和恢复退步。本版将交付可操作的局部精修流程；不把“自动从照片建成完整 C17”列为交付承诺。

依据：[C17 能力评估](C17-Precision-Building-Assessment.md)。对应的测试步骤、容差、独立证据与发布门槛见 [0.5.0 验收方案](Acceptance-Plan-0.5.0.md)。本文中的示例保留设计时的命名；已实现的准确字段及输入格式以已安装 CLI 的 `commands schema`、`properties.describe` 和[精修手册](../skills/sp2-build-assistant/references/precision-building.md)为准。

## 1 用户预期和本版交付边界

| 用户预期 | 本版必须交付 | 完成后能证明什么 | 仍不承诺什么 |
| --- | --- | --- | --- |
| 知道任意可用零件能改哪些属性 | 所有当前可用模板均可查询有效能力；同一字段区分可写、只读、依赖实例、尚不支持 | AI 无需靠试错判断工具是否允许编辑，也不会把 XML 可读误当成可写 | 所有游戏内部字段都允许写；第三方 Mod 未经验证的属性自动可写 |
| 精细调整重要组件 | 现有机身/机翼能力，加窗体、贴花、文字、材质、整流罩和机械基础属性适配 | 本版字段清单内能表达、写入并验证实际效果 | 所有旧式/导弹/仪表/动画属性在本版一次性补齐 |
| 精确摆放多个组件 | 局部坐标、枢轴旋转、显式部件组刚性变换、镜像与可选挂点/轴对齐 | 无需自行推导每个世界坐标；组内相对关系可保持 | 通用约束求解器、任意曲面自动贴合、连接自动吸附 |
| 不断微调至目标 | 稳定截图、局部测量、版本差异、固定视图与可执行 skill 流程 | 在可表达、可测量、有尺度的局部任务中收敛到预设容差 | 从未知透视照片唯一还原三维形状；任意 CAD 精度 |
| 工程安全和效率 | 生效读回、影响清单、完整恢复、同类编辑合并重建、性能数据 | 在测试范围内改动可控，未涉及区域保持，反复调整有合理代价 | 几何预演完全无副作用、飞行稳定性/适航或完整动画扫掠保证 |

**是否达到预期：** 本版以“能参与高还原度工程、对支持范围内的局部进行精细控制”为通过目标。若用户将预期定义为“AI 独立复制整个 C17 的全部细节”，本版仍不够；参考标定/自动拟合、完整动画及剩余复杂族需要后续版本。不能用局部验收通过替代整机能力证明。

## 2 修改位置和工作包

以下路径相对于 `SP2BuildAssistant/`。`Game/` 仅作为反编译参照，不修改游戏源码。继续使用独立 DLL、全局 `sp2build` 和可导入 skill。

| 工作包 | 修改现有文件 | 拟新增文件 | 实现方式和解决的问题 | 验收映射 |
| --- | --- | --- | --- | --- |
| W1 截图可靠性 | `bridge/DesignerCapture.cs`、`DesignerViewPlan.cs`、`Transport.cs`；`cli/contracts.py` | `bridge/CameraState.cs`；`tests/CameraStateTests.cs` | 先定位 FB-043 的差异，再做完整相机状态保存/恢复与语义容差比较；失败带结构化诊断；固定取景描述可重用 | T01、T02、T16 |
| W2 有效属性契约 | `bridge/BuildRuntime.cs` 的 Catalog/Schema/PartInfo/ValidateAttribute；`AdvancedEditing.cs`、`InputControllerFields.cs` | `bridge/PropertyRegistry.cs`、`PropertyDescriptors.cs`、`NativePropertyAdapter.cs`；`knowledge/editable-coverage.json` | 合并 UI 声明、原生 metadata、有效值和已验证适配器；模板与实例共用一份实际可写契约，消除 schema 与写入器矛盾 | T03、T04、T05 |
| W3 外形和装饰属性 | `bridge/AdvancedEditing.cs`、`ShapeCodec.cs`、`BuildRuntime.cs`；沿用表达式/ID 防护 | `bridge/CarverProperties.cs`、`DecalProperties.cs`、`AppearanceProperties.cs` | 窗体/切割目标、文字/投影贴花、材质槽与局部材质编辑；动态资源列表及关联校验 | T06、T07、T08、E1、E2 |
| W4 机械基础属性 | 同 W2 的分派与事务入口、`InputControllerFields.cs` | `bridge/MechanicalProperties.cs` | 整流罩长度、活塞、铰链/转轴、起落架腿/轮子/舱门的尺寸、行为配置与局部铰链姿态；保留原生依赖 | T09、T10、E3 |
| W5 局部位姿和组 | `bridge/AdvancedEditing.cs`、`BatchReferences.cs`、`VisualScope.cs` | `bridge/TransformCore.cs`、`TransformEditing.cs`、`PartGroups.cs` | 显式成员、局部基准、枢轴、刚性组变换；处理原生随动件和镜像，阻止重复应用 | T11、T12、E2、E3 |
| W6 几何测量 | `bridge/VisualCapture.cs`、`DesignerGeometry.cs`、`VisualCore.cs`、`VisualScope.cs` | `bridge/MeshSnapshot.cs`、`GeometryMeasure.cs`、`SectionMeasure.cs` | 从已有真实网格采样提取共享不可变快照；提供最近点、截线、接缝见证点、局部法线与对称误差 | T13、T14、E1、E2 |
| W7 迭代事务和差异 | `bridge/BuildRuntime.cs` 的 Mutate/Apply/Replace/ReadSettled、`SnapshotState.cs`、`ReplacementLifetime.cs` | `bridge/EditPlan.cs`、`CraftDiff.cs` | 增强预检查和影响报告；新属性/位姿的纯数据修改可合并一次重建；原生依赖操作设重建边界；输出实际变化和执行阶段耗时 | T15、T16、T17、T18 |
| W8 CLI 和 skill | `cli/sp2build.py`、`contracts.py`、`shape_contracts.py`、`visual.py`；`skills/sp2-build-assistant/SKILL.md` 与现有 references；安装/打包脚本 | `cli/property_contracts.py`、`geometry_contracts.py`；`references/precision-building.md`；相应契约测试 | 全部功能走 CLI，输出 schema、help、operation 映射一致；按目标查询能力；发布迭代方法与恢复流程 | T19、T20、E1–E3 |

按 W1/W2 → W3/W4 → W5/W6 → W7 集成 → W8 发布完成。W8 的契约先随各工作包维护，skill 最后按实际能力定稿；不能先发布未实现命令。

## 3 有效属性契约如何实现

### 3.1 属性发现不等于开放任意反射写入

原生证据已确认：`GenericPartPropertiesScript.GetConfigurablePropertiesList` 扫描 `DesignerProperty*`；`ConfigurableProperty.SetValue` 处理转换和镜像，具体 UI 控件还会调用 `OnGenericDesignerPropertyChanged`。因此，仅反射赋值或仅改 XML 都不能普遍等价于玩家修改属性。

注册表为每个语义属性定义稳定 `propertyId`、所属 modifier/index、原生字段及 XML 映射、读有效值的方法、单位/坐标系、静态与动态校验、依赖、镜像策略、执行适配器、刷新需求。原生 Overload、UI 声明和序列化证据分别保留来源；不要覆盖成一份含糊的 native schema。

查询状态采用 `editable`、`readOnly`、`conditional`、`unsupported`、`unknown`。`unsupported` 表示工具尚未支持，不能冒充游戏只读；`conditional` 必须返回缺少的宿主/资源/实例条件。静态模板无法求动态范围时返回原因及所需实例条件，不伪造最终边界。目录查询不创建场景零件、执行 setter 或改变选择。

属性描述还应区分常量与表达式输入。只在原生确实允许表达式的字段开放并使用对应解析器编译，编译成功不表示已在飞行环境求值；字符串外观字段不能被误当表达式。保留旧 native metadata 供追溯，新增有效契约作为工具权限依据；`shape.get` 未映射族的提示应指向新属性接口，避免继续让AI猜XML。

拟议命令：`properties.describe`（模板/类型/实例选一）、`properties.get`（当前实例）、`properties.set`（批次 operation）。实例查询返回 identity；模板查询返回游戏/模板/registry 版本。支持字段筛选、分页、按族查询，避免每次加载完整目录。

拟议属性描述示例：

```json
{
  "propertyId": "shroud.lengthScale",
  "type": "number",
  "unit": "ratio",
  "value": 0.93,
  "valueSource": "live_modifier",
  "editability": "editable",
  "limits": {"min": 0.75, "max": 1.5, "source": "native_ui_and_adapter"},
  "writeOperation": "properties.set",
  "dependencies": ["connectedEngine"],
  "refresh": ["mesh", "attachPoints", "collider", "editorPicking"]
}
```

该示例的语义名是新契约；`lengthScale` 为倍率，不能误标成米。属性真正进入 editable 的前提是适配器实现、合法/非法值测试和至少一个原生实机效果用例通过。

### 3.2 执行策略

先验证整个属性补丁，再选择注册的执行策略：

1. 经原生 UI 对照证明等价的序列化字段，写入工作副本并在提交时原生重建。
2. 需要原生 setter/回调的字段，使用具名适配器，在主线程和现有恢复边界内执行正确回调及镜像处理；不要求打开属性面板。
3. 材质、目标 ID、嵌套列表等结构项走专用适配器，不放行任意 XPath/XML 或私有字段。

每次返回 requested/effective 值、实际影响零件/字段及规范化原因。越界拒绝；合法的原生规范化若不等于请求值必须明确返回，不能静默夹紧后宣称精确设置成功。旧 `part.update` 保留兼容语义，但查询要明确“需专用入口”，尤其是 materials 等结构项。

适配器的单位与表示转换应单独测试，例如窗体“上宽/上偏移”与原生 upperSpan 两端值、UI百分比与0到1数值、投影器四元数与Part Euler。不能直接把显示标签当XML字段，也不能把UI滑块步长当作原生精度上限。

### 3.3 本版必须覆盖的字段组

下表是发布范围，不以“元数据里恰好有什么”决定交付。实现第一步生成逐字段清单，每个字段关联来源、读写策略和测试；下列必需组不能因实现困难改标 unsupported 后算作完成。

| 族 | 必需字段组和交互约束 |
| --- | --- |
| 现有 JFuselage/JWing/控制面 | 保留现有全部形状功能及 inputControllers；注册表指向已有 shape/控制器入口，不复制两份冲突规则；保持邻接同步、镜像和有效默认值 |
| Window/Carver | 上下宽度及偏移、height/depth、cornerRadius、penetration、hideGlass/透明设置、目标模式和自定义目标列表；每项说明参考轴和原生单位 |
| TextureDecal/TextDecal | 投影位置/四元数和尺寸、穿透深度、颜色/透明度/优先级、图案 ID、tiling/offset；文字/字体/字号/对齐；目标集合与随动行为。返回 Part 位姿和投影器位姿关系，不假定二者相同 |
| 材质与涂装 | 当前飞机 palette/slot 查询，单件/组选定槽赋值；克隆当前飞机材质再修改颜色、metallic、smoothness、昼夜 emission；已有原生纹理资源及纹理变换查询/合法赋值。共享材质修改须显式选择作用范围并返回受影响件 |
| JetEngineShroud | style/length/width/height，发布接缝/发动机依赖；radius 是否可独立改以原生依赖为准，派生时只读并指向应修改的引擎参数 |
| Piston/Rotator/Hinge | 原生范围内的尺寸/半径、行程或角度、速度、循环/方向/防断等配置，活动端/外壳/轴及输入；区分倍率、米和角度 |
| GearLeg/轮组 | 原生样式及兼容的支杆/扭力臂、尺寸/偏置、悬挂行程/弹簧/阻尼、轮胎/轮辋/宽度、转向/制动/抓地配置；绑定宿主和输入 |
| GearBay | 梯形轮廓/切割目标、舱门样式/厚度、自动铰链开关、两组局部铰链位置/四元数；保留已有 Animator，不能破坏其节点引用 |

字体/纹理/样式资源通过拟议 `resources.list` 分类别分页返回游戏可用 ID、原生名称及适用范围。材质克隆、编辑只属于当前飞机 Theme，禁止改变全局自定义主题/其他飞机；保留原生预留槽和容量规则，容量不足明确拒绝。

完整 Animator 时间线编辑、仪表指针/显示布局、导弹子组件和其他未列出的复杂族本版必须准确可查，暂不承诺全部可写。当前 40 类型以及所有可用模板都有能力条目；数量是采样基线，验收按当时完整目录计数，不写死 176。

## 4 位姿和部件组如何实现

拟议 `groups.resolve` / `transform.apply` / `transform.align`。组必须显式列成员或使用已有已知语义选择器，并返回展开后的 ID；不根据连通 BFS 自动认定整个机械子树。

变换输入指定 frame（world/part/craft/custom）、mode（delta/absolute）、平移单位、四元数或具名轴角，以及 pivot。delta 旋转矩阵 Q 的确定规则为 `p'=pivot+Q*(p-pivot)+translation`、`R'=Q*R`；局部基准先在同一前置快照转换到世界坐标，不能随着逐件编辑漂移。四元数检查有限、非零并规范化，返回有效旋转。

本版组变换仅做刚性平移/旋转，不加入组非均匀缩放。已有单件 scale 继续可查可用，但不能把缩放当作机身拉伸或机构尺寸调整的通用替代。

操作前解析原生宿主随动、镜像、窗体/贴花目标及组外连接，返回显式影响集；变换一次后验证实际位姿，避免机翼和原生随动控制面被移动两次。组成员不全、依赖矛盾或镜像目标重叠时返回可处理的冲突，不能只成功移动一部分。可选对齐限于明确挂点、轴和指定偏移；普通 `connection.connect` 保持原行为，含原生 autoResize 的影响需显示在预检查里。

组引用绑定 session/revision 与成员摘要。受控编辑可更新引用；玩家编辑、ID 复用或无法证明成员连续性时使旧引用失效并要求重新解析。**同 ID、同 partType 也不足以证明还是同一个对象。** 本版不往飞机里强塞跨会话 GUID，也不承诺重启后组句柄可用。

## 5 测量怎样服务微调

拟议 `geometry.measure` / `geometry.section` / `geometry.seam`；保留原来的 `parts.geometry` 和碰撞射线。

- 提取主线程上的真实 renderer/mesh 状态，在同一 revision 形成不可变快照；缓存键含 session/revision、姿态采样状态、成员、frame、几何来源与排除项。只在副本上计算，不调用 Unity 对象于后台线程。
- 对两组提供无符号表面最短距离及见证点；穿透深度/有符号距离若拓扑条件不满足则 unavailable，不能用最短距离 0 宣称“没有穿透”。
- 与指定平面相交获得截线/轮廓；接缝限用户指定区域，给配对见证点、法线夹角、max/RMS/采样密度。最近距离不能替代整条接缝误差，采样最大值不能冒充连续曲面严格上界。
- 明确 renderMesh/collider 来源、坐标/单位、模型采样分辨率、数值/离散误差、缺失网格及 complete 状态。非闭合网格可返回有效截线，但无法推断内部时标注；贴花、透明及 shader 外观另用原生截图验收。
- 输出小型结构化结果和可选见证点叠图/截线文件。默认不把几十万三角面送进 AI 上下文；调试导出也只来自当前打开飞机的样本。

本版不做自动照片标定、参考网格全局配准或参数优化器。AI 可用已知尺寸/截面目标逐步调整，测量工具负责回答“目前差多少”，下一版再让确定性拟合器承担搜索。

## 6 迭代可靠性和性能如何实现

W1 首先记录失败时 cameraBefore/After、fieldDiff、渲染阶段及恢复异常。检查 position/rotation、目标、投影、matrix、rect/aspect、clip、targetTexture 和原生控制器状态；整数/枚举/对象引用严格相同，位置与角度按验收容差比较。不能单纯放宽 DeepEquals 掩盖错误。连续多视图、失败、取消和恢复后下一帧均须测试。

`batch.preview` 增加 validationLevel 和检查清单：结构/已知字段/依赖/可确定范围/预期影响。对需要原生构建才能确认的项标 `pendingNativeValidation`，不改口声称具有隔离几何预演能力。新增 `craft.diff` 比较同会话检查点与当前对象，覆盖属性、位姿、连接、目标引用、输入、材质、变量及影响集外变化。

`EditPlan` 仅合并注册为“可安全串行作用于数据副本”的相邻操作；同字段按原操作顺序处理，动态范围按候选最终状态校验。原生 setter、创建、连接、删除及依赖必须落地时设 flush 边界，禁止为凑一次重建重排原操作。保持一批的恢复边界与原生撤销语义，复用 Replace 的生命周期修复。

完成结果增加 stageTimings、rebuildCount、effectiveChanges 和验证详情。只有在 ReadSettled、碰撞/编辑器缓存更新、选择恢复、唯一场景实例检查完成后才返回成功。任务超时沿用 operationId 查最终结果；不能用新 requestId 盲目重发写入。

## 7 执行里程碑

| 里程碑 | 具体交付 | 继续条件 |
| --- | --- | --- |
| M0 冻结目标与证据 | 从现有目录/UI/序列化生成逐字段 coverage 清单；固定测试构型、独立预期值、容差、命令名；记录 0.4.11 基线性能 | 无未解释的必需字段；方案中不确定的 UI 动态约束已归类；故障可诊断而非猜根因 |
| M1 可靠性与契约 | W1/W2；模板和实例能力查询、截图恢复及诊断、扩展契约测试 | T01–T05 通过；不再存在 materials 等“宣称可写实际拒绝”的矛盾 |
| M2 属性适配 | W3/W4，按窗体→贴花/文字→材质→整流罩/机构顺序 | 每族原生 UI 对照、真实外观和恢复通过；不可只凭单元测试标完成 |
| M3 空间编辑和测量 | W5/W6，先数值核心、再 Unity 采样与操作 | T11–T14 通过，误差指标可用独立算法核算 |
| M4 集成与效率 | W7/W8，固定视图、差异、局部迭代 skill，安装/版本协商 | T15–T20 通过；大型构型与故障回归无副作用 |
| M5 效果验收 | E1–E3 的完整任务及记录、最终支持矩阵 | 所有必需项和客观指标通过；主观外观待用户评价则明确保留状态 |

每个阶段遇到失败先确认并记录原因，继续与失败无依赖的测试，阶段结束统一修订补丁。已破坏恢复、对象身份或场景一致性时停止写入，不能继续用不可信状态测试；恢复后再续测。通过项不无理由重复，修改共用路径后执行对应回归。

本计划不承诺未经验证的工期；W2/W3 动态属性和 W5 原生随动是主要工程不确定性。若必需适配器无法安全实现，报告具体被阻断目标；不能静默降为 unsupported 后宣称 0.5.0 完成。

## 8 交付和后续边界

发布包含独立 DLL、全局 CLI、skill ZIP、版本化字段覆盖清单、调用文档、验收证据索引及已知限制。更新 `bridge/Transport.cs`、CLI、package/install 的版本并核对安装哈希；工具发现已加载 buildId 后才进入实机验收。代码构建、文件部署和运行时验收分别记录，DLL 仍需要重启加载。

已有用户授权的自动验收流程不依赖 DSH。本轮仅制定计划，**不执行部署、游戏重启或飞机写入**。当前 C17 原作保留为只读参照；后续写入验收在明确的测试飞机会话中进行，原作未被授权为可改测试样本时不得写入。保存测试副本、切换飞机仍是显式测试准备，不增加操作未打开存档的产品能力。

0.6 及以后再评估：参考图标定/误差叠图与拟合、完整 Animator/机构运动学和连续扫掠、导弹/仪表等剩余族、任意截面扩展或更高级约束。是否需要扩展原生形状表达，应由局部任务中无法达到目标的误差证据推动。
