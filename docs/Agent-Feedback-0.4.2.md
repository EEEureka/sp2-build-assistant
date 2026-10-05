# S01 反馈核实与 CLI / skill 0.4.2

日期：2026-10-02。DLL 仍为 0.4.0；本轮只补调用契约和说明，不改变游戏行为、不需要重启。

S01 机身完成：Aircraft，revision 10，6 件 / 5 连接；主干、机头过渡及锥体、尾部过渡及锥体总长 11.7 m。协调端使用全局 CLI 重新采集当前快照、5 件形状、6 件几何、质量贡献，前后 XML/身份一致；实际打开 DSH 四视图。没有进入飞行场景。

## FB-025 的成立范围

调用说明需要更明确，但没有证据证明批次提前报告了未完成的几何刷新。

- `centers-after-connect.json` 在 revision 7 已返回 #4 12.7209157 kg、#6 7.0699446 kg；最终两个锥体长度减半后分别为 6.3604578 / 3.5349723 kg。因此 DSH 报告中“rev7 仍与提交参数一致”不成立，不能把之后才读到的长度变化全部归入返回后的事件。
- 当前源码 `JFuselageScript.OnConnectedToPart` 会在 autoResize=true 时复制相邻截面和 offset，执行 AlignToSlice，然后关闭 autoResize。这属于原生连接回调；手动设尺寸不会自动关闭该标记。
- revision 8 的 `Craft Repositioned` 是另外一次原生历史步骤。`Designer.Save` 在 AutoRecenter 开启时会平移整机；单靠历史名称、选择为空，无法区分自动保存或玩家保存。
- 每次写入已在完成时读取 identity。增加“再读一次”或任意延长等待，都不能锁住后续保存或玩家操作。保留乐观并发检查，遇到冲突重新读取；按同一 revision 检查几何，用相对位置区分全机平移和形变。

0.4.2 在 connection.connect 输入 schema、autoResize 属性说明、写入输出 identity/validation 描述、skill 与编辑参考中明确上述语义。DSH 应据此纠正台账和报告的混合时间线，复验说明后继续 S02。射线包含挂点 BoxCollider：本轮侧向首命中比网格面外凸 0.025 m，属已知 all-collider 口径；没有证实碰撞体刷新失败。

证据：`tests/artifacts/staged-build/S01-review/` 为协调端新鲜只读采样与独立核查；DSH 原始输出及阶段报告在 `D:/codeSpace/sp2_craft_edit/staged-build/S01/`。
