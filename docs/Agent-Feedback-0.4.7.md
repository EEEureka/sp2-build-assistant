# S05 反馈核实与 CLI / skill 0.4.7

日期：2026-10-02。DLL 维持 0.4.6；本次只修改 CLI schema 与使用说明，不需要重启游戏。

## 采纳的说明改进

- FB-036：`part.add.rotation` 是模板旋转增量，原调用手册已经说明，因此“完全未文档化”不成立。但 operation schema 仅标数组，未直接解释。0.4.7 在 operation、快捷命令、批次嵌套 schema 中说明 rotation 增量、position 首件目标位置、temporaryId 仅绑定首件，skill 编辑参考同步补充。垂尾模板自带 Z=90°；零增量保留它的竖直姿态。
- FB-037：省略 visual groups 使用玩家当前选择，空选择返回 selection_empty，是现有且已文档化的默认行为，不是参数漏校验。0.4.7 将默认选择、空选择错误和整机 selector 例子直接写入 groups schema，并强化 skill 的最短调用说明。仍允许省略 groups，不改变运行时默认范围。

## 未成立的反馈与修正

FB-038 声称 S05 重建刷新了既有 12 件的 drag/dragArea，证据使用了错误基线。其引用的 S04/retest-0.4.6/snapshot-after-step4.json 实际是临时试验中的 rev10、17 件，并非已恢复的 rev11、12 件。正确基线 final-snapshot.json（rev11）与 S05 snapshot-final.json（rev14）、snapshot-after-lower.json（rev15）对比，既有 12 件完整 Part 子树逐一相同，drag/dragArea 也相同。因此本轮刷新现象未成立，应撤回；通用语义差异查询建议已经由 FB-017 覆盖，不另计为新缺陷。原生 PartDrag 确实读写这两个字段，但源码存在派生字段不证明此次发生了刷新。

核对证据：tests/artifacts/staged-build/S05-review/fb038-baseline-audit.json。最终 rev15 总质量 1068.1177226826549 kg，起点 1030.8694055303931 kg，增加 37.248317152261734 kg，等于 #13 和 #14 的质量之和。报告应采用同一 revision，不能混用早期近似值。

## 本阶段验收

S04 的 0.4.6 运行时复验由协调端独立检查 72 项通过。S05 建造垂尾 #13、方向舵 #14，最终 14 件 / 13 连接；55 项独立检查通过。最初垂尾根部后段悬空来自布局选择，已将根部从 y=3.075 调整到 y=2.858，方向舵原生随动，侧视/斜视缝隙消除，局部射线确认根部与机身相交。Yaw、控制范围、原 12 件和对称组保持。设计器 CoL 对竖直翼的世界 up 投影接近零，不据此断言方向稳定或飞行性能。

105 项契约检查及 skill 校验通过，安装后 CLI / skill 文件与源文件逐一哈希一致，DLL 哈希保持不变。DSH 已用全局 sp2build 确认版本、两项 schema 描述和 skill 段落，并完成整机捕获及实际读图；0.4.7 复验通过，继续 S06 副翼。证据见 DSH staged-build/S05/retest-0.4.7/ 与协调端 tests/artifacts/staged-build/S05-review/deployment-0.4.7.json。
