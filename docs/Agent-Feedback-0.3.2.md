# 0.3.2：DSH 实机反馈修订

日期：2026-10-02。先完成 0.3.1 的八类场景及补充删除测试，再集中修订。当前部署、实机验证边界见 [Verification.md](../Verification.md)。

## 反馈核查与处置

| 反馈 | 核查结论 | 本版处理 |
|---|---|---|
| FB-020：输出来源键名不一致 | 属实，旧 outputs.list 使用 parts[].modifiers，variables.list 使用 sources[].outputs | 新增显式 structured 模式，两者统一为 sources[].modifiers；默认旧模式保持兼容 |
| FB-020：视觉组字段名不一致 | index 与 groupIndex 命名不同属实；但 0.3.1 已可按相同的零基索引关联，不必推断文件名 | groups[].groupIndex 作为规范字段；保留等值的 index 别名 |
| FB-021：必须遍历 XML 树 | 属实，连接与全局 Setter 读取成本较高 | structured 模式返回数值化连接行和带当前索引的 Setter 行 |
| FB-022：重排含义不明 | 属实，CLI schema 缺 items、语义和样例 | 补完整契约；运行时严格拒绝小数、数字字符串、重复、缺失、越界索引 |
| FB-014：失败仍可能改变 revision | 实测成立；不能推导成“每次失败必定递增” | 说明 revision 是 XML 内容版本；失败恢复结果增加前后 revision 和 revisionChanged |

原生重排实现原先调用 `Values<int>()`，可能把小数或数字字符串转换成整数；现在要求 JSON integer，并验证完整排列，避免隐式转换改变求值顺序。其余写入与回滚语义不变。

## 结构化读取

```powershell
sp2build connections list --view structured
sp2build variables list --view structured
sp2build outputs list --view structured
sp2build outputs list --part 20 --view structured
sp2build commands schema --command variables.list
```

需要**已加载的 DLL 0.3.2**。不传 view（或 `--view legacy`）保留原接口；结构化模式标记 `data.view="structured"`。输出 schema 在 `properties.data.oneOf` 分别描述两种模式，并使用共享的 `Connection`、`Setter`、`OutputSource`、`OutputDefinition`、`OutputBinding` 定义。

连接结构示例（不是新版 DLL 实机返回）：

```json
{"view":"structured","connections":[{"partA":15,"partB":16,"attachPointsA":[0],"attachPointsB":[1]}],"count":1}
```

每一行仍是游戏原生连接，一侧可能含多个挂点 ID。连接是拓扑关系，不表示吸附、支撑或树的父子所有权。此模式不输出原始 XML；需要额外原生字段时使用 legacy。

变量结构示例（省略 identity；此示例没有部件输出源）：

```json
{
  "view":"structured",
  "setters":[{"index":0,"variable":"ThrottleMix","function":"clamp(Throttle,0,1)","priority":0,"activator":null}],
  "setterCount":1,
  "sources":[],
  "sourceCount":0
}
```

实际只返回有输出定义的零件，source 包含 `partId/type/typeName/name/modifiers`，其 `modifiers[]` 包含 `modifier/definitions/bindings`。两种命令的 sources 结构相同，避免重复解析不同字段路径；outputs.list 可通过 part 限定零件。setter.index 是当前序列的零基位置，删除或重排后必须重新查询。缺少 activator 返回 null；不替调用者猜测运行时值。

## 变量重排

```powershell
sp2build commands schema --operation variable.reorder
```

对于现有 `[A,B,C]`，`{"kind":"variable.reorder","order":[2,0,1]}` 表示变为 `[C,A,B]`。order 是“按新顺序排列的全部旧索引”，不是目标位置映射或交换对。必须覆盖所有当前 Setter，整数、各一次；空列表仅在没有 Setter 时合法。写入仍需批次会话、revision 和 requestId 守卫。

## 失败后的版本与视觉组

恢复操作允许每轴 0.0001° 的原生 Euler 重建误差，revision 的严格指纹仍可能变化。0.3.2 的 rollbackResult 增加 `beforeRevision/currentRevision/revisionChanged/revisionMeaning`；失败后的下一次写入使用顶层 identity 或新状态查询，不能复用旧 revision。预校验拒绝、无实际变化等情况不一定递增。

`groups[].groupIndex`、`detailStatus[].groupIndex` 和 `imageRecommendations[].groupIndex` 都从 0 开始；groups[].index 是兼容别名。0.3.1 应用可直接以 index 关联，`g1-` 文件名的一基编号无需参与计算。

## 验证范围

0.3.1 已由 DSH 实机测试并由 Codex 独立复读，恢复到 351 件、357 连接、9 个全局 Setter，完整 XML 无超出容差的差异。0.3.2 的 170 项功能检查、104 项旧返回 schema 兼容检查和 10 项结构化契约正反例通过；含真实基线 XML 的连接、Setter 投影及严格排列拒绝。DSH 已复核新版 CLI/schema/skill，并确认旧 DLL 请求 structured 时明确拒绝，未发现新增问题。新版 DLL 的实际加载和 structured/重排负例/视觉组字段复测需在桌面解锁后完成，不能以编译或磁盘部署代替。
