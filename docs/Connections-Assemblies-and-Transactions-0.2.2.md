# 连接、组件删除与事务：DSH 反馈核查（0.2.2）

日期：2026-10-02。核查对象是当前设计器 Super Wasp test（352 件），运行 DLL 为 0.2.1。本轮不重启游戏、不编辑当前飞机；新增 DLL 需下次重启生效。

## 1. 连接与定位分开

DSH 对“不吸附”的观察正确。工具调用 `MovePartTool.ConnectPartToAttachPoint → PartScript.ConnectToPart`，这条路径建立原生连接并通知部件回调，没有通用的移动/旋转对齐步骤。

连接挂架与翼下挂载物后，外观位置仍需通过 `part.add` 的 position/rotation 或独立 `part.update` 位姿修改。连接点不重合可以是作者的有意设计，不应据此强制移动。原生部件回调仍可能调整程序化附件，因此完成后要读回位姿。“只建立 Fixed 关节”不能推广到所有部件；转轴、铰链等仍遵循原生关节语义。

按用户要求，连接实现保持不变，只补充 skill 和文档。本轮未重新测量 DSH 提到的 0.56 米，不将其当成全局容差或自动对齐规则。

## 2. 连接、空间位置和受力含义

这是任务语义区分问题，不是 BFS 算法本身有错：

| 要回答的问题 | 应使用的证据 | 不能据此推断 |
| --- | --- | --- |
| 两件是否直接相连、经哪些件连通 | connections、BFS/最短路径 | 在哪个机翼下方、零件几何是否贴合 |
| 某挂架上方命中哪件、距表面多远 | 当前坐标系方向、parts geometry、designer raycast | 唯一的受力支撑件或作者语义上的归属 |
| 某原生复杂部件由哪些从属组件构成 | 已确认的原生 modifier 归属 | 所有连通零件都属于这个组件 |

本轮只读实测：从 `[-2.252138,4.5,-1.679502]` 向世界 +Y 发射 2 米射线，首先命中 Main Wing #19，距离约 0.050536 米；从 `[-3.448788,4.5,-2.094502]` 发射同方向射线，首先命中 #19，距离约 0.002504 米。这支持 #225/#238 所在位置上方是 #19，不能证明图路径经过的 Intake 是或不是物理力传递路径。

因此不添加未经定义的“实际支撑件”字段。skill 明确要求先判断问题问的是连接还是空间位置；空间查询要说明射线起点与方向，避开自身碰撞体，必要时多点采样，不能把单条射线结果直接写成确定的支撑归属。

## 3. 显式原生组件删除

默认 `part.delete` 继续只删指定件；`symmetric:true` 按原生组包含对称零件。默认没有子件级联。

新增两个入口，要求 **运行中的 DLL 至少为 0.2.2**：

```powershell
sp2build designer status --json
sp2build parts assembly --id 229 --json
sp2build parts assembly --id 229 --symmetric true --json
```

`parts.assembly` 返回 identity 和 assembly：rootPartId、rootPartIds、memberPartIds、childPartIds、parts、externalConnections、membershipSource。这是当前快照中的删除范围，可让 agent 先核对哪些件会删除、哪些连接会断开。真正执行仍须带该会话与当前 expectedRevision。

删除操作示例（放入 batch.apply 的 operations 数组）：

```json
{"kind":"part.delete","partId":229,"assembly":true,"symmetric":false}
```

本版范围：

- 程序化导弹弹体：本体及直接连接、原生归属明确的导弹组件，包括鳍、翼、进气口和装饰件等。
- JWing：机翼及直接归属它的 ControlSurface 部件。
- 挂架、其他机翼、油箱、武器、机身不因为普通连接而自动加入；不沿图递归。
- 不支持任意自定义子装配或整条“分支”的自动推断；对这类任务列出明确 partId，放入同一批次逐件删除。
- 必须指定组件根；指定某个子件不自动升级为删除整个父组件。
- `symmetric:true` 扩展根的原生对称组，再分别计算每个根的子件。显式对称删除沿用游戏原生删除语义，包括组内设置了 symmetryDisabled 的成员。
- 未知/不一致归属，或子件还连到范围外部，返回 `assembly_ambiguous`；不支持的根返回 `assembly_not_supported`。
- 先计算完整范围并检查主驾驶舱保护，再删子件和根。删除结果必须与计划一致，否则整笔事务恢复；成功时 `actualChanges[].deletedPartIds` 返回全部被删除 ID。

在当前飞机的离线快照中，同型导弹 #229 的范围为 `[229,230,234,235,239,240]`，即弹体加 5 个子件；挂架 #103 留在范围外。这是范围算法的真实数据回归，不能替代新 DLL 的游戏内删除验收。

`batch.preview` 仍只检查请求结构，不能替代 `parts.assembly` 的具体范围查询。CLI 0.2.2 与运行 DLL 0.2.1 混用时，原有命令保持可用，新入口会被旧 DLL 拒绝；安装 CLI 不等于运行中 DLL 已更新。

## 4. 七操作批次及回滚

核查了 DSH 的真实操作 `b347cddac0d148799661630def67b94d`：

- actualChanges 包含删除 #215、#216、#217、#226、#227、#214，以及连接 #225 与 #358，共 7 项。
- 前一次提交 revision=3，该批提交后 revision=4；原生历史新增一个 `SP2Build b347cdda` 节点。
- 该次成功，没有触发失败恢复。证据：`tests/artifacts/feedback-operation2.json`、`feedback-history.json`。

源码中 batch.apply 在开始检查会话、版本并记录整架飞机 before 快照，顺序执行所有操作，统一验证表达式与几何，最后创建提交撤销节点并读取新指纹。每个操作不会各加一次 revision；净状态未变时，revision 也不保证增加。

运行异常时，catch 恢复整批之前的飞机和历史位置，再核查恢复结果。之前 0.2.1 实机验收已覆盖“先改名、后非法裁剪”的失败恢复，前面的改名也被撤销；见历史验收报告及 `tests/artifacts/v02-9e32aa3187/acceptance.json` 中 invalid transaction rollback。

这里的事务是进程内快照补偿。游戏崩溃、进程被杀或恢复本身失败时不能保证恢复成功；必须检查 `rollbackResult.restored` 与 stateUncertain。恢复中的原生浮点重建也可能改变 revision，失败后不能沿用旧 expectedRevision。输入结构或版本在执行前被拒绝时尚未编辑，无需把它当成发生了回滚。

## 验证与发布状态

0.2.2 独立 DLL 编译通过；69 项离线检查通过，其中新增 15 项组件范围测试、2 项 CLI 合同测试。原有连接实现、默认单件删除和批次事务逻辑未改变。用户要求保留当前游戏，因此本轮没有在当前飞机写入测试，也没有重启；assembly:true 的游戏内删除/撤销/失败恢复需在下次加载后验收。
