# S03 追加说明：CLI / skill 0.4.5，DLL 0.4.4

FB-031 核实：默认 summary 下不返回贡献行是已设计并已有调用示例的行为；原始响应已经有 `contributors.requested:false`。建议“增加 requested=false”不成立，也没有证据说明来源数据丢失。`total` 是过滤后分页前的来源数，与 `returned` 的本次行数不同；`--metric` 本来只过滤指标。猜测 `--contributors` 或 `--detail true` 导致的调用失败属于调用方输入错误。

采纳其中减少误读的建议：CLI help 的 `--detail` 描述明确要求 `--detail contributors`；输出 schema 给 requested/total/items 增加语义说明；skill 同步补充。响应结构与 DLL 行为保持兼容，无需重启游戏。请 DSH 核对帮助和 schema 后继续 S04，台账应保留上述归因，不把文案改进记作丢失数据的修复。
