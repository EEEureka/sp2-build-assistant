# 复杂零件与设计器接口：0.2

日期：2026-10-01。本文记录本轮五项需求的源码调研、接口设计、实现范围与验收方法。入口统一为 `sp2build`，操作对象始终是玩家当前打开的编辑器飞机。DLL 更新需要重启一次游戏；之后编辑飞机应在当前设计器内刷新，无需保存、退出或重开飞机。

## 需求与验收

| 需求 | 本轮实现 | 验收依据 |
| --- | --- | --- |
| 区分关节活动端和外壳 | `connections points`、`parts get` 返回 rotor/housing、关节轴、关联零件 | 依据 `JointRotatorData.AttachPointIndex`，它是数组下标，不能当作连接点 ID |
| 修改后外观和拾取同步 | 原生重建完成后重绑 MeshCollider、同步物理、重建 EditorCollider；保留选中 ID | 长度变化后比较边界，并从新增体积位置做射线命中测试；不能仅用 XML 判定通过 |
| 当前玩家选中零件 | `designer selection` | 无选择时返回 null，不猜测最后编辑的零件 |
| 复杂零件可读可编辑 | `shape get/schema/update`，Fuselage 邻接同步，机翼控制面便捷新增 | 严格字段白名单、类型/范围/组合检查、原生翼型解析、原生生成失败恢复 |
| 对称关联 | `symmetry get/link/unlink/create/enable` | 原生分组写入飞机 XML；镜像角点、左右切面、翼型翻转需正确，撤销/回滚恢复分组 |

## 复杂零件盘点

判定条件是存在重复截面、相互约束的几何参数、嵌套状态、多个部件共同生成一套几何，或动画/姿态/目标绑定。单纯参数数量多的普通发动机不能直接等同于多截面几何。

扫描当前工作区反编译代码和游戏导出的完整目录，整理为 11 类。机器可读清单保存在 `knowledge/complex-parts.json`，覆盖 81 个源码文件、1003 条带文件及行号的参数证据，并保留相应零件模板的原生 metadata、默认状态和介绍。统计按类别累计，继承基类可能重复。目录基线为 0.7.8.103，动态字段和 Mod 仍需运行时查询。

```powershell
sp2build knowledge complex --json
sp2build knowledge complex --family landingGear --json
sp2build catalog schema --type GearLeg-1 --json
```

| 类别 ID | 场景与全部参数的分组方式 | 便捷接口设计与当前覆盖 |
| --- | --- | --- |
| fuselage | Body/Cone/Curved；offset、空心/玻璃、燃料/质量/浮力、碰撞设置；每截面的 size、cornerRadii/Stretch/Samples、edgeCurvature/Samples、trapezium、thickness、cutting、smoothing、syncSlices；锥尖 roundness、autoResize | 已实现具名角/边、截面索引、长度/宽/高、自动裁剪 null、邻接同步与匹配；派生 mass 不作为输入 |
| wing | span stations、每截面 airfoil/scale/offset/smoothJoin/bend/bendRadiusMultiplier/采样覆盖；整翼采样、翻转、燃料、气动倍率、涡流、Rounded Wingtip | 已实现截面补丁、完整截面替换、原生翼型解析、翼尖和整翼属性；读回关联控制面 |
| controlSurface | 跨距 range、两端 startPos、style；Standard/Fowler 最大偏转、Slat 偏转、BrakeFlap 襟翼/上刹车/下刹车偏转及速度；输入表达式、dummy 状态 | 已实现四种目录原生控制面，使用跨距米数和弦长比例；Spoiler/SplitFlap 只有源码结构，不开放便捷写入：原生序列化和编辑支持不完整 |
| legacyGeometry | 旧 Fuselage 的截面/填充/切面/进气道/材质密度；旧 Wing 的根尖前后缘、位置/厚度/攻角/翼型/集成舵面 | 保留原生属性及旧状态查询。拟单独实现适配器，不能用 JWing/JFuselage 同名字段直接覆盖 |
| carver | Window/Bay/MeshModifier 的宽高深、上下梯形宽、角半径、penetration、order、隐藏玻璃；PartTargeting 的目标模式/ID集合 | 方案：`dimensions + outline + cutTargets + appearance`；当前返回原生分组状态和 metadata，未实现专用几何写入 |
| landingGear | GearBay 门样式/厚度、自动或双铰链位置/四元数；GearLeg 尺寸、支杆、扭力臂、悬挂；Animator 的 NamedPose/Keyframe/percent/parent/位置/旋转/持续时间 | 方案：`leg + doors + suspension + poses[] + animation`，按姿态名称编辑，并检查父动画引用；当前为清单和原生接口 |
| wheel | 大小/宽度、轮胎/轮辋/偏置/双轮、制动与转向、弹簧/阻尼/行程/车高、摩擦曲线、发动机绑定 | 方案：`tire + rim + steering + brake + suspension + tractionCurve`，区分外观、悬挂几何和动态参数；当前为清单和原生接口 |
| missile | 游戏内程序化弹体/鼻锥/长度/半径/引擎/导引头；子部件位置/尺寸/角度/对称/附着范围 | 方案：`body + nose + modules[] + fins[]`，验证附件落在弹体允许区间；当前为清单和原生接口 |
| propulsion | PropellerAssembly 的桨毂/桨叶数/半径/弦长/扭转/桨距/共轴/反向；引擎与齿轮/传动/动力曲线 | 方案：`hub + blades + pitchControl + powertrainBindings`，分开几何和动力链；当前为清单和原生接口 |
| cockpit | Gauge 面板和指针输入/单位/零点/倍率/发光；ControlBase 轴/范围/屏幕映射；PosedGrip 姿态/控制绑定；IK 目标/权重 | 方案：`display + channels[] + bindings[] + poses + interaction`，先解析实际类型与动态绑定；当前为清单和原生接口 |
| articulation | Rotator/Hinge/Piston 关节活动点、关节轴、范围/速度、阻尼/循环/伸长、输入 | 已实现连接点功能角色；属性仍走原生 metadata。Piston 未经确认的端点不冒充已知 rotor/housing |

清单中的源码参数包含构造配置、派生值、版本迁移字段和序列化字段，**不是全部允许写入的白名单**。查完整字段及含义应结合该文件的 `nativeTemplates[].part.metadata`、`defaultState` 和 `sourceFiles[].parameters`。这同时覆盖当前飞机没有使用的零件。

## 读取接口

```powershell
sp2build designer selection --json
sp2build connections points --part 123 --json
sp2build parts geometry --id 123 --json
sp2build designer raycast --origin '[0,3,0]' --direction '[0,-1,0]' --distance 10 --json
sp2build shape get --id 123 --json
sp2build shape schema --family fuselage --json
sp2build shape schema --family wing --json
sp2build shape schema --family controlSurface --json
sp2build symmetry get --part 123 --json
```

新增输出结构示例，数值及 ID 为说明用途，不是实机验收证据：

```json
{"success":true,"data":{"identity":{"craftSessionId":"SESSION","revision":8},"selectedPartId":123,"part":{"id":123,"type":"JFuselage-1"},"shape":{"family":"fuselage","configuration":{"offset":[0,0,2],"length":2,"sections":[{"index":0,"role":"back","width":1,"height":1,"cutting":{"top":0.64,"right":null,"bottom":null,"left":null},"adjacent":null}]}}}}
```

连接点条目新增：`role`（rotor/housing/articulated/attachment）、`roleSource`、`jointAxisLocal/World`、`requiresPhysicsJoint`、`bodyIslandBoundary`、`mirrorId`、`surface`、`connectedPartIds`。未知关节只报告已有元数据，不根据零件名称猜活动端。

`parts geometry` 分开返回渲染边界、物理碰撞体边界和设计器缓存边界。它们不保证数值完全相同：碰撞形状可能是简化网格；重点是编辑后它们更新到一致的新状态。`designer raycast` 使用当前飞机可交互部件的实际 Collider，可用于检查新增体积能否被命中；它是世界坐标射线，不等同于带 UI 遮挡和屏幕吸附的鼠标事件。

## 统一写入与撤销

所有新增编辑都是同一 `batch apply` 的操作，保留请求去重、会话/版本冲突保护、自动恢复、原生撤销和检查点回滚。便捷别名接受 `{requestId,craftSessionId,expectedRevision,operation:{...}}`；批次接受 `operations:[{kind,...}]`。可用 `commands schema --command shape.update` 查完整信封。

Fuselage 示例（保存为 UTF-8 `batch.json`）：

```json
{
  "requestId":"UNIQUE_REQUEST_ID",
  "craftSessionId":"SESSION_FROM_SNAPSHOT",
  "expectedRevision":8,
  "operations":[{
    "kind":"shape.update","partId":123,"symmetric":true,
    "patch":{
      "length":4,
      "sections":[{
        "index":0,"width":1.2,"height":1.5,
        "cornerRadius":{"topLeft":0.2,"topRight":0.2},
        "cornerStretch":{"topLeft":false,"topRight":false},
        "edgeCurvature":{"top":0.25},
        "cutting":{"top":0.64,"bottom":0,"left":null,"right":null},
        "smoothing":true,"syncAdjacent":true
      }]
    }
  }]
}
```

```powershell
sp2build batch apply --input batch.json --json
sp2build shape get --id 123 --json
sp2build parts geometry --id 123 --json
```

Fuselage 方向采用零件局部坐标：+Y 为上，+X 为右；角按 topLeft/topRight/bottomRight/bottomLeft；边与切割按 top/right/bottom/left。视角改变不改变这些名称。

- `length` 是局部 Z 轴截面间距绝对值，保留 offset.x/y 与原 z 符号；需要倾斜时传完整 `offset`，与 length 互斥。
- `sections` 是补丁数组，必须给唯一 index。Curved 有三截面，中间截面不支持裁剪/平滑/邻接同步；Cone 尖端只有裁剪能力。
- 非拉伸角半径单位为米，拉伸角为无量纲量，工具限制 0..1。几何允许的最大半径与截面尺寸及梯形有关，读取中的 `cornerRadiusNativeMax` 给出原生上限，实际生成会夹紧半径。
- thicknessFraction 限制 0.01..1；旧 `legacyThickness=true` 的零件不允许按比例写厚度，避免静默改变单位。
- cutting 的 null 表示原生自动值；数字是 0..1 比例。上下、左右裁剪各自相加必须小于 1。0.64 对应截图中的 64%。
- 两个相邻端面都启用 syncAdjacent 时，截面补丁同步到原生识别的相邻端面，同端相接时交换左右。启用标记本身不自动移动零件。
- 显式匹配相邻端面使用 `{"kind":"fuselage.match","partId":123,"sectionIndex":1}`：从已连接的邻面复制截面轮廓/厚度/裁剪，并启用双方平滑与同步。它不移动零件，不替用户创建连接，也不额外传播整个对称组。

机翼截面补丁：

```json
{"kind":"shape.update","partId":200,"patch":{"sections":[{"index":0,"chord":3,"airfoil":"NACA2412"},{"index":1,"spanPosition":4,"chord":1.5,"offset":-0.5,"airfoil":"NACA0012","bendDegrees":5}],"wingtip":{"stretch":1.2},"fuelFraction":0.25}}
```

替换截面拓扑用 `replaceSections`，与 sections 互斥。需要 2..32 截面，spanPosition 从零严格递增，间隔至少 0.001 米。根/尖 chord 和 offset 必须显式定义；根部 airfoil 必须有效，后续 airfoil 的 null 使用原生插值/继承。内部 chord/offset 可以为 null 表示插值。翼型调用当前游戏的 AirfoilRegistry 验证；不能把任意五位数或修改型 NACA 名称当作受支持翼型。wingtip 传 null 删除圆翼尖。

控制面是一件独立部件，读取机翼会同时返回关联控制面：

```json
{"kind":"wing.control.add","wingPartId":200,"style":"StandardFlap","temporaryId":"aileron","patch":{"spanRange":[1,3],"chordFraction":[0.25,0.3],"maxDeflectionDegrees":20}}
```

工具自动选游戏内置模板，先按目标机翼校验并设置新控制面的范围、弦长比例，再建立兼容连接并重建几何。0.2.1 修复了默认模板尚未应用尺寸便连接、触发原生翼型插值越界的问题；用户保存的子装配不会替代内置控制面模板。已有关联部件用 `shape.update`；删除用 `part.delete`。新增仅作用于指定机翼，另一侧需要明确新增并建立原生对称分组。`spanRange` 是沿原始展向站位的米数；`chordFraction` 是控制面两端占当地弦长的比例（Slat 0.05..0.4，其余可编辑边缘控制面 0.05..0.8）。工具用原生弦长约束解算器校验跨多个截面的合法性，拒绝同边跨距重叠和需要静默夹紧的输入。实际翼型面积不是一个可独立写入的标量。

## 对称操作

```json
{"kind":"symmetry.link","partIds":[123,124]}
{"kind":"symmetry.enable","partId":123,"enabled":false}
{"kind":"symmetry.unlink","partId":123}
{"kind":"symmetry.create","partId":123}
```

每行是独立操作示例，不能不加判断地连续执行。link 要求同类型、尚未分组、位置与旋转符合设计器当前的镜像/径向配置；enable 对整个已有组启停；unlink 拆整个组，不删除零件；create 按玩家当前镜像/径向模式创建关联副本，**不自动克隆连接拓扑**。平面/径向轴是设计器设置，可通过 symmetry get 读取，本版不把它们混入飞机 XML 撤销事务。

`shape.update` 默认同步已启用的原生组，可传 `symmetric:false` 单侧修改。形状补丁会处理左右角、左右切割、横向偏移和翼型翻转。原生组成员与当前平面/轴不吻合时返回 `symmetry_geometry_mismatch`，不猜另一侧。普通 `part.update` 保持兼容，只有显式 `symmetric:true` 才传播；其位置/旋转/缩放不支持笼统同步，应单独给出各零件位姿。其他非几何属性按相同值传播，不自动推测表达式应否反号。

## 刷新修复与验证状态

原实现只等待 XML 指纹稳定；这无法证明物理网格及设计器缓存完成更新。0.2 在写入、撤销、回滚中统一加入：

1. 原生重建时立即停用旧对象，避免 Unity 延迟 Destroy 期间旧碰撞体仍参与命中。
2. 等待 Fuselage 原生生成队列、碰撞烘焙任务及网格/碰撞边界稳定；机翼原生生成失败视为失败。
3. 重新绑定 MeshCollider 的 sharedMesh，Physics.SyncTransforms，然后原生重建 EditorCollider 并刷新缓存版本。
4. 再次等待稳定，恢复原先选中 ID（若已删除则空选），之后生成撤销节点。

显式刷新也可用 `{"kind":"craft.refresh"}`；它是受相同会话/版本和撤销保护的批次操作。成功结果有 `validation.geometryRefreshed/physicsSynchronized/editorCachesRebuilt` 和当前 `selectedPartId`。

0.2.1 已在游戏 0.7.8.103 的 Jet Fighter - Adder（269 个零件）中完成 23 组主验收，全部通过，包括拉长/缩短后的实际物理射线命中、显式刷新、撤销、三种机身、四种控制面的新增/修改/删除、镜像组生命周期及回滚。52 项离线检查同时通过。详细边界与人工界面验收、原始证据目录和限制见 [Verification.md](../Verification.md)。不直接修改保存的飞机文件，也不以存档修改代替编辑器验证。

源码依据：`JFuselageData/Script`、`FuselageJob/SectionParams`、`JWingData/Script`、`InputWingSlice`、`AirfoilRegistry`、`ControlSurfacePartData` 与 `WingSurfaceClaims`、`JointRotatorData/Script`、`Assembly`、`Designer/EditorCollider`、`SymmetryUtility`，具体参数出处见机器清单。
