# 直接建造验收与输入配置读出补丁（0.4.9）

**后续更正：本报告的完整场景验收结论撤回。** 用户随后发现两套飞机模型，实际点选证实旧场景对象残留；30 件当前 XML 和单机导出图未覆盖该问题。0.4.10 修复生命周期并增加场景检查，重启后待原序列复验。用户还要求将军用喷气动力替换为涡桨，尚待场景恢复后实施。最新状态见 [0.4.10 诊断与修订](Agent-Feedback-0.4.10.md)，下文保留当时的数据层验证记录。

日期：2026-10-02。按用户最新授权，Codex 直接使用全局 `sp2build` 建造和验收，本轮未调用 DSH。运行时验收使用 DLL 0.4.8；0.4.9 补丁已构建、部署并通过离线验证，新读出需要下次游戏启动后复验。

## 当前飞机与阶段结果

Aircraft 已从本轮起点的 16 件继续建到 **30 件、29 条连接，全部连通，无临时测试件残留**。原有机身、主翼、平尾/升降舵、垂尾/方向舵保留，完成副翼输入修复及下列后续建造。十个对称组全部 enabled。最终模型和三心推荐图已实际打开检查。

| 阶段 | 构型及验证结果 | 原始证据目录（相对 tests/artifacts/staged-build/direct-0.4.8） |
| --- | --- | --- |
| S06 | #15/#16 正式绑定 Aileron；合法输入/激活表达式、反向 min/max、invert/Axis/Output 通过。五类非法输入批次均撤销前序合法改名，并恢复原指纹；正式输入配置回滚后保留 | S06-retest |
| S07 | #17/#18 Fowler 襟翼，展向 0.35–2.55 m、弦比 0.30、35°；同批添加/temporaryId 输入设置/对称建组通过；重叠范围被拒且恢复；35→30→35 同步往返指纹一致 | S07 |
| S08 | #19/#20 前缘 Slat，展向 0.4–5.4 m、弦比 0.12、20°；与后缘面共存；0.41 非法弦比被拒且恢复 | S08 |
| S09 | #21/#22 原生 BrakeFlap，展向 2.7–3.35 m、弦比 0.28、上下制动偏转各 60°；两个控制器可分别配置，网格/拾取碰撞器有效。**独立 Spoiler 未完成，不能算扰流板阶段全通过** | S09-research、S09-brakeflap、S09-brakeflap-finish |
| S10 | #23/#24 双军用喷气发动机，左右翼挂载，Throttle 输入；双翼 fuelFraction=0.12，燃油状态同步；CoT 两个贡献源 | S10 |
| S11 | #25/#27 主支柱、#26/#28 主轮、#29 前支柱、#30 前轮；LandingGear 输入、主轮 Brake/前轮 Yaw；三胎底共面、根部接触用局部射线验证 | S11、S11-layout、S13-gear-contact |
| S12 | 全局 BuildFlapCommand/BuildBrakeCommand；#3 输出 Speed→BuildSpeed、PosY→BuildAltitude；变量新增/修改/重排/删除、输出改名/解绑、原生 undo、检查点 rollback 与非法表达式恢复通过 | S12 |
| S13 | 临时机身 1→4→1 m：扩展区域从不命中→命中→不命中，网格和编辑器碰撞器同步刷新；删后同批新增 ID 复用有 reusedPartIds；临时机翼 assembly 删除精确移除翼及两个控制面，外接机身保留；最终回滚精确恢复正式飞机 | S13-runtime、S13-final |

S09 边界：当前原生目录查询 Spoiler 无结果；反编译 `ControlSurfaces/Spoiler.cs` 的放置/范围调整仍为未实现，未覆盖自身 hingePos/length 的保存。当前工具可写四种原生样式为 StandardFlap/FowlerFlap/BrakeFlap/Slat。BrakeFlap 是双面制动襟翼，不能宣称已经提供独立上翼面扰流板；以后需要单独设计支持方案。

个别中断属于验收脚本错误，已修正，不登记产品缺陷：catalog.schema 的真实路径为 `data.templates[].parts[]`；BrakeFlap 的三个网格共用一个编辑器碰撞器，不需要每个网格一个碰撞器。侧视图疑似起落架根部间隙经局部射线和分组图否定：支柱根部高于翼下表面约 0.023 m，保留原布局。

## 三心与交付快照

本轮最后读取会话 `c40fde362ce44cb6b6c89a4333d64a72`、revision **28**、fingerprint `f5a191bb7aefcd9f6ae9d0cc0e9b4100d7927e3befd3d6502ec65d3a7538c1ee`，stateUncertain=false；DLL 0.4.8，buildId `1e628a6d-7e92-4bd6-ae86-27289f3ea6c7`，游戏 0.7.8.103/XML25。游戏在 rev27→28 记录了 Craft Repositioned；30 个零件统一上移约 1.034964 m，最大剩余位置差约 2.34e-7 m，已按新坐标复核，未还原掉这次原生居中。

质量约 **3652.94 kg**。按当前 +Y 向上、+Z 向机头：设计器 CoL 相对 CoM 在上方 **0.449 m**、前方 **0.141 m**；CoT 在下方 **0.245 m**、后方 **1.905 m**。升力中心是设计器投影代理，不能据此判定静稳定、配平或可飞性；未进入飞行场景、未验证操纵效能。仍保留原生 flipped 机翼 CoM 数据的已知警告，不修改游戏物理来消除警告。

最终快照、连接、对称、变量、三心及交付检查点见 [S13-final](../tests/artifacts/staged-build/direct-0.4.8/S13-final/final-state.json)。检查点 `b70f92bb76974a05a6db0376f1f46f14` 仅属于本次运行会话，重启后失效，不代替玩家保存飞机。

![最终飞机三视图与三心](../tests/artifacts/staged-build/direct-0.4.8/S13-final/centers/e898a6979c58458a812b4521a059bdfe/overview.png)

## 确认的易用性问题与 0.4.9 修改

FB-039 的输入写入阻挡已在 0.4.8 实机解决。新增 FB-040：S06 对 StandardFlap 写入 `zeroOnDeactivate:true` 后，原生 XML 省略该默认值，`invertType:Axis` 也可能省略。0.4.8 的通用 XML 读出没有直接给出有效值，agent 需要额外查源码才能判断，尤其多控制器部件容易选错节点。此问题是**读出信息不足**，并非写入未生效。

0.4.9 从原生 `InputControllerData` 读取配置，不求值控制器和飞行遥测，也不从缺失的 XML 字段猜默认值。以下位置新增 `inputControllers` 数组：

| 调用 | 返回路径 |
| --- | --- |
| `sp2build parts get --id ID` | `data.part.inputControllers` |
| `sp2build shape get --id ID` | `data.shape.inputControllers` |
| `sp2build designer selection` | 选中零件的 `data.part.inputControllers` 和 `data.shape.inputControllers` |
| `sp2build catalog schema --id TEMPLATE_ID` | `data.templates[].parts[].inputControllers`，包括当前飞机没有使用的模板 |

结构示例（非 0.4.9 实机输出）：

```json
{
  "index": 0,
  "path": "InputController.State[0]",
  "name": "native controller name",
  "description": null,
  "input": "Aileron",
  "activationGroup": "0",
  "invert": false,
  "invertType": "Axis",
  "min": -1.0,
  "max": 1.0,
  "zeroOnDeactivate": true,
  "invertOnMirror": false,
  "serializedAttributes": ["activationGroup", "invert", "min", "max", "input"],
  "valueSource": "live_part_modifier"
}
```

`index/path` 与同类 modifier 的原生顺序对应，便于直接填写已有 `part.update`；没有控制器时返回空数组。`valueSource` 在目录中为 `isolated_template_modifier`，与实时零件区分。`serializedAttributes` 表示原生序列化器当前会输出哪些属性；省略属性不意味着 false。`name/description/invertOnMirror` 仅解释原生配置，不增加可写字段。已有原始 state、metadata 和写入接口保留。旧 DLL 缺少整个 inputControllers 字段时不能解读为空数组。

## 验证与下一次启动

- 构建通过；243 项离线回归、105 项通用契约、32 项形状契约通过。
- 本轮记录的 CLI 信封按新版契约校验通过；另有 7 项新读出合成契约用例（默认值省略、多控制器、目录/shape 路径、错误类型/索引/来源拒绝）。详见 [校验报告](../tests/artifacts/contracts-0.4.9/input-controller-and-build.json)。合成用例不作为新 DLL 实机验证。
- skill 依据 skill-creator 更新并校验通过；全局入口继续为 `sp2build`。
- 0.4.9 的新 DLL 读出尚未在运行中的游戏加载；部署记录另见 [Verification.md](../Verification.md)。下一次启动先确认版本、当前 30 件飞机、新身份，再只读核对控制面/BrakeFlap/轮子的有效配置、无控制器零件及未使用模板。需要验证默认值切换时使用新检查点，完成后恢复正式配置。

本次基础功能实测通过并保留飞机，但独立 Spoiler 功能缺口及 0.4.9 新读出的运行时复验仍未完成。
