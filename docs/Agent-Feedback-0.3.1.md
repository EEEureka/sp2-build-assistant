# 0.3.1：Agent 反馈修订

日期：2026-10-02。针对 DLL / CLI 0.3.0 的 DSH 反馈；实际加载状态与验收边界见 [验证记录](../Verification.md)。不引入 DLL 热更新，不改变保存飞机的访问范围。

## 本版范围

| 台账 | 修订 | 验收边界 |
|---|---|---|
| FB-008 | 跟踪批次内零件生命周期；报告 ID 复用；拒绝旧数字和旧临时引用 | 纯逻辑回归通过；原生删除/新增/连接及失败回滚需加载新 DLL 后实机验收 |
| FB-009 | 小目标/遮挡自动细节图，联合总览始终保留；已有 perGroup 图也参与推荐 | 实际渲染核心的合成网格用例通过；当前飞机的新 DLL 捕获待验收 |
| FB-004 | 输入/输出 schema、共享零件/挂点定义、成功/失败/异步/文件回执区别 | 使用实际 0.3.0 返回验证兼容；新增字段通过离线用例，仍需新 DLL 读回 |
| FB-007 | commands list 明确 CLI 与 operation 映射；新增 --operation；保留旧查询 | CLI 离线可验收，不依赖新 DLL |
| FB-001/002 | 射线命中内嵌零件身份，明示全碰撞体命中、距离排序、未按零件去重、无插件条数上限 | 实机旧接口缺口已确认；新字段待加载后核验 |
| FB-003 | 明确 name/type/typeName 差别，摘要提供原生类型名称 | 不修改玩家名称，不根据名称推断物理归属 |
| FB-015 | 补充导弹子件缩放的原点偏移说明 | 文档修订，不开放未经验证的导弹参数写入 |
| FB-016 | 返回和 manifest 增加比例策略与跨次比较说明 | 自动取景保持原行为，未新增固定 pixelsPerMetre |
| FB-018 | 挂点 normal / jointAxisLocal / jointAxisWorld 明示方向语义、坐标系、无归一化保证 | 来自 DSH 第一轮独立验收；对照原生 AttachPointData 与桥接返回代码核实 |
| FB-019 | 离线子命令帮助、分组帮助，完整公开文件输出、实例与图片目录参数 | 来自 DSH 第一轮独立验收；帮助区分直接参数和快捷写入 JSON 内字段 |

FB-005/006 的任意删除影响分析、FB-010 的精简选择输出、FB-013 的导弹参数化接口另行研究。FB-014 的恢复后 revision 变化沿用现有规则：恢复等价校验和严格指纹是两个指标，必须使用恢复后 identity。FB-011/012 不新增强制吸附或推测的 supportingPartId。未知 assembly 根拒绝、已支持根的成员边界、批次守卫和恢复机制保留。

## ID 复用与引用

游戏继续分配空闲 ID。每步操作之后比较当前 ID 集合并记录创建/删除，覆盖单件删除、assembly 删除、对称扩展和多件模板；原生飞机重建保留逻辑 ID，不因 Unity 对象被重新创建而判成新零件。记录依据是每一步，不能用整批前后的 ID 集合差替代。

成功结果增加：

```json
{
  "temporaryIds": {"newPod":214},
  "invalidatedTemporaryIds": [],
  "reusedPartIds": [{
    "partId":214,
    "previous":{"id":214,"type":"Missile-Procedural","name":"Old missile","typeName":"Missile"},
    "current":{"id":214,"type":"Targeting-Pod","name":"Targeting Pod","typeName":"Targeting Pod"},
    "deletedAtOperationIndex":0,
    "createdAtOperationIndex":1,
    "temporaryIds":["newPod"]
  }]
}
```

这是结构示例，不是本版实机操作记录。下标从 0 开始，身份摘要记录该次创建时刻，后续仍可能重命名或再次删除。最终 `temporaryIds` 只列存活绑定。

删除后继续引用旧数字 ID 返回 `stale_part_reference`；旧临时名返回 `deleted_temporary_reference`。新零件使用新的 temporaryId，不能在同一批次改用复用后的数字。错误进入已有整批恢复机制，不静默改到替代件。跨批次仍需重新读回；本版没有跨撤销/重启的永久 GUID。

## 命令发现与输出

```powershell
sp2build commands list
sp2build commands schema --command parts.get
sp2build commands schema --command connections.connect
sp2build commands schema --operation connection.connect
sp2build commands schema --operation shape.update
sp2build visual capture --help
sp2build connections connect --help
```

`commands`、`operationKinds` 保留；新增 `commandDetails`、`operationDetails`，给出执行方式和 schema 查询命令。`entityKind` 区分命令与操作。旧 `--command connection.connect` 继续工作，并标注 `legacyQuery:true`。自同名快捷命令如 shape.update 也可以通过 --operation 明确获取 operation 结构。

输出 schema 使用 JSON Schema 2020-12，`properties.data` 描述实际嵌套路径，`$defs` 只返回被引用的公共定义。`outputSchema` 对应最终结果；`asyncOutputSchema` 对应 --async 受理；`savedOutputSchema` 对应 --output 的 stdout 回执，输出文件内容仍是最终结果。operation.wait/result 的结果随最初命令而变化，需查询该命令的 schema。动态原生形状和目录元数据由 shape.schema/catalog.schema 进一步定义，不把未知属性宣称为可写。

`contractVersion` 是 CLI 契约版本，`designer status.pluginVersion` 才是已加载 DLL。为支持升级过渡，新增输出字段在 schema 中允许缺省；新 CLI 不表示旧 DLL 已具备新行为。

`--help` 返回离线帮助对象，包含全局参数、仅特定命令可用的参数，以及当前命令的参数/JSON 输入方式；帮助对象不使用被查询命令的业务 outputSchema。`--output-dir` 适用于 visual.capture 或取回捕获结果的 operation.wait/result；`--output` 是 JSON 结果文件，两者用途不同。提前发生的 CLI 错误可能仅返回 stdout 错误而不创建结果文件。

挂点 `normal` 与 `jointAxisLocal` 是零件局部方向，`jointAxisWorld` 经 TransformDirection 转换到世界坐标，只应用旋转。三者均无量纲，不是欧拉角；桥接器没有归一化它们，调用者不能默认长度为 1。原生 AttachPointData 从 XML 读取 normal/jointAxis，默认均为向上方向；不根据默认值推断所有实际值均归一化。

## 视觉推荐与射线

DLL 0.3.1 默认 details:auto。综合各联合图块的可见长度、相对长度、可见像素数，任一视角达到 96px、15%、1024 像素时视为具有可读视角；否则生成独立细节图。auto 通常选择 isometric，没有该视角时使用最佳现有视角。perGroup 保留全部分组视角，并从中挑选有用的细节图。阈值是初始启发式，平台再次缩图可能影响可读性。

`recommendedImages` 仍为路径数组，首项 overview；`imageRecommendations` 提供原因、分组、视角和比例。`detailStatus` 明示未生成的原因。auto 受 1600 万像素预算约束，超预算保留总览并报告 budget_exceeded；它不保证所有分组一定生成细节。每个 detail 保持内部真实几何，但中心和比例独立；判断多个对象相对位置仍看联合视图。

`scalePolicy=fit_scope_each_capture` 说明每次捕获重新取景。即使使用同一 frame，也不能直接比较像素长度；使用该视图 pixelsPerMetre 或 frameToPixelRows 换算到米。

射线保留 `partId/distance/point/normal`，增加 `part:{id,type,name,typeName}` 和 `query` 说明。同一零件可因多个碰撞体重复出现；Unity 可能不返回包含射线起点的碰撞体。命中是几何交点，不证明承力支撑关系。

## 开发验证

`tests/run-unit-tests.ps1` 验证引用生命周期、复杂形状、快照恢复语义、assembly 范围、视觉渲染和 CLI 契约。`tests/validate_contracts.py` 使用仅开发需要的 jsonschema 校验实际返回；加 --live 时只通过全局 sp2build 查询当前飞机，不发起写入、捕获或检查点操作。CLI 运行依然只依赖 Python 标准库。

DSH 已通过其既有工作会话完成两轮独立只读验收：首轮检验发现接口/schema/skill，提出 FB-018/019；补丁后复核确认两项已解决并更新台账。当前游戏桥接不可用，DSH 和开发侧均未把新 DLL 行为记为实机通过。剩余参数化导弹编辑、删除影响分析、精简选择输出与 revision 差异查询没有纳入本版。
