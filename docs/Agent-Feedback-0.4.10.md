# 重复飞机场景缺陷与选型修订（0.4.10）

后续实测更新（2026-10-02）：0.4.10重启加载后的原触发序列、CLI和原生撤销均通过，场景仅1实例；涡桨换装已完成。详见 [0.4.11验收记录](Agent-Feedback-0.4.11.md)。以下为修订前诊断及首次部署历史。

日期：2026-10-02。用户在直接建造验收后提供了编辑器出现两架飞机的截图，并要求将军用喷气发动机换为适合翼下布局的涡桨。本版继承 0.4.9 的有效输入配置读出，修复重建对象生命周期、增加场景检查，并补充组件选型流程。**CLI、skill、DLL 0.4.10 已部署并核对哈希**；运行中仍为 0.4.8，新 DLL 尚需重启后的实机验证。涡桨替换在场景修复复验后进行，当前未改动原飞机数据。

## 已确认：工具当前对象视图遗漏旧场景实例（FB-041，高）

飞机 Aircraft，session `c40fde362ce44cb6b6c89a4333d64a72`、revision 28、30 件；DLL 0.4.8，buildId `1e628a6d-7e92-4bd6-ae86-27289f3ea6c7`，游戏 0.7.8.103/XML25，PID13072。用户截图及 computer-use 实时窗口均可见上下错开的两套模型，UI 质量约 3653 kg / 392 L。开始时无选中零件；保存状态和玩家此前操作不能由接口确定。此前 history 记录整机居中，不能判断是自动还是手动保存。

调查仅执行只读 CLI 和 UI 点选，无拖动、删除或重建：

```text
sp2build designer status --json
sp2build craft snapshot --input snapshot-input.json --json
sp2build craft history --json
sp2build designer selection --json
sp2build parts get --id 23 --json
```

快照输入为 `{"includeXml":true}`。下方发动机被选中时，selection 的原始值为：

```json
{"id":23,"type":"Engine-Jet-Military-1","position":[1.4,2.0,-1.2]}
```

当前飞机的 parts.get 同 ID 返回：

```json
{"id":23,"type":"Engine-Jet-Military-1","position":[1.3999995,3.034964,-1.20000052]}
```

再点选上方发动机，selection 位置与当前 parts.get 一致。两者 Y 差 **1.034964 m**，对应 rev27→28 原生整机居中的位移。确认存在可拾取的旧对象，不能把它的数字 ID 用于当前飞机编辑。调查后已清空诊断选择。原始输出、完整 XML、目录候选及用户截图见 [调查证据](../tests/artifacts/staged-build/direct-0.4.8/duplicate-aircraft-investigation/0001-designer.status.json)，同目录 `0005-lower-engine-selection.json`、`0006-current-same-id.json`、`0009-upper-engine-selection.json` 和 `user-scene.png`。

先前 `S12/0024-craft.undo.json`、`S12/0027-craft.rollback.json`、`S13-runtime/0023-craft.rollback.json` 均有 `partCount:30`、`restorationVerified:true`。这些核对的是当前飞机 XML，**并没有证明场景无旧对象**。parts.geometry、designer.raycast、visual.capture 同样只遍历/保留当前 Aircraft，导致导出图看起来正常。此前 S13 的全机验收结论撤回；各属性/拓扑/恢复数据证据保留，不能推广为完整场景验收通过。

## 根因与修复

游戏 `Designer.AssignAircraft` 通过 AircraftContainer.Find("Aircraft") 删除第一个同名子对象；Unity Destroy 延迟到帧末才移除对象。同一批次内多次 Replace 时，后续 AssignAircraft 可能重复找到已经排队销毁的第一个实例。旧工具只禁用 outgoing，依赖原生按名字删除，没有对每个实际 outgoing 明确销毁，因此中间实例可残留。

随后的原生 Undo/RestoreFromUndoStep 直接 AssignAircraft，不会先禁用当前实例。若容器前面有残留对象，它会删除残留对象而留下原当前实例继续显示；新旧飞机重叠，之后原生居中只移动当前飞机，重影分开。本轮数据与这一机制吻合；离线模型复现了“同帧多次替换→帧末留下实例→原生撤销出现两个 active aircraft”。由于旧 DLL 没有场景实例清单，不能追溯每个旧对象的精确创建操作号。

0.4.10 修改：

- Replace 成功后明确销毁捕获的 outgoing 对象，不依赖同名 Find。赋值前失败才恢复旧对象；已发布新对象后失败，不重新激活旧实例。外层仍执行事务恢复。
- craft.undo 仍使用原生 UndoHistory 上一步，但通过同一受控 Replace 重建，保留原生历史游标与现有恢复流程。
- `designer status` / capabilities 新增 `data.sceneIntegrity`：统计当前设计器 AircraftContainer 中所有 AircraftScript（含 inactive）、当前对象、额外对象、active 数量，以及选中对象是否属于当前飞机。该查询只报告，不自动删除来源未知的对象；不声称覆盖容器外所有游戏对象。
- 写入前及完成/恢复后检查场景；异常返回 `designer_scene_inconsistent`。成功 validation 增加 `sceneIntegrityVerified:true`。visual/centers 路径也拒绝不一致场景，避免输出正常单机图掩盖重复模型。
- `designer selection` 对旧飞机选中对象返回 `selection_not_in_current_aircraft`，避免将旧模型 ID 当作当前零件。

## 发动机选型：已有信息被忽略，流程需要补足

原先主动选择了 `Military Jet Engine / Engine-Jet-Military-1`。名称和原生目录已经说明其类型，不能归因为工具隐藏了推进方式，也不能仅凭模型有可连接挂点就判定适合当前用户要求。喷气发动机并非在物理上都不能翼下安装；本次修改依据是用户明确要求涡桨以及期望布局。

实时目录在 `Aircraft Propulsion / Turbo Props` 提供 Small/Medium/Large Turboprop，附游戏原生介绍。小型/中型 schema 各有 **7 件**，包括短舱、涡轴核心、排气、传动和螺旋桨。partTypes 是去重后的类型列表，不能当作零件数；组件里的 Engine-Jet-Shroud 也不代表整个总成是喷气发动机。

优先候选为 Small Turboprop（`tpl-0107631356a369e6`），模板涡轴 horsepower=750；中型（`tpl-21a5a045d00e4403`）约4253。它们是原生配置值，不是整机性能结论。现有 schema 可以查询尺寸/朝向和控制输入，但不能在未放置时返回真实网格预览，也不能自动证明安装净空。下一轮先验证修复，再用检查点添加完整双侧小型总成，按实际桨盘扫掠范围、机身/机翼/起落架/地面净空、机械传动和操纵输入验证，确认后删除旧 #23/#24；数字 ID 必须按新会话重新识别。

已在 skill 新增 [组件选型流程](../skills/sp2-build-assistant/references/component-selection.md)：需求约束→原生类别/介绍→总成组成与单位→尺寸/挂载/净空→实际读图与回读。相同原则适用于起落架、武器挂架、旋转关节等。自己的选型错误不另凑一个工具缺陷编号；真实工具缺陷 FB-041 单独处理。

## 离线与运行时验收边界

构建通过；253 项离线回归（新增 10 项生命周期测试）、105 项通用契约、32 项形状契约、skill 校验通过。生命周期用例包含旧逻辑的重复飞机复现、跨帧多次连续替换、随后原生撤销、发布前失败、发布后失败与恢复。它们不能代替新 DLL 实机验证。

当前场景未清理、游戏未重启、未使用旧版本继续改造动力。0.4.9 已被本补丁取代。用户保存当前正式飞机并重启加载 0.4.10 后，需要核对 sceneIntegrity 为健康单实例；测试连续多次 Replace、失败恢复、undo/rollback，再结合真实编辑器窗口检查仅一架飞机；完成后继续涡桨替换和 0.4.9 输入配置读出验收。重启消除旧模型本身不算缺陷修复通过，必须走原触发序列复验。
