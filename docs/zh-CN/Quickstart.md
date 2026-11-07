# 让 Agent 完成第一次建模任务

[English](../Quickstart.md) · 简体中文

安装配套插件、CLI 和 `sp2-build-assistant` skill。把 skill 交给能在游戏所在 Windows 电脑上执行命令的 Agent，再在设计器中打开测试载具或工作副本。

## 给 Agent 一个可验收的目标

第一次可以从一个局部开始。例如，请 Agent 做如下检查。

> 检查当前飞机两段机身之间的接缝。先定位两件并测量间隙，告诉我准备改什么。保持周围几何不变，调整后按同一视角复拍，并报告剩余间隙。

## Agent 的操作步骤

1. **确认目标。** 使用 `sp2build designer status` 与 `sp2build designer selection` 读取会话和选中件。用 `sp2build parts get --id 42` 查询实际目标件，把示例 ID 换成实读结果。可用 `sp2build catalog categories` 查零件库，再用 `sp2build craft snapshot --output baseline.json` 记录初始状态。
2. **选取验证方式。** 涂装、透明窗或遮挡使用[原生截图](Designer-Screenshots.md)。用[局部精修指南](Precision-Workflow.md)里的几何命令量间隙、截线或位置差异。
3. **实施局部编辑。** 按 [CLI 手册](CLI-Usage.md)构造请求，填入当前 `craftSessionId`、`expectedRevision` 和新的 `requestId`，并先建检查点。用 `sp2build batch preview --input batch.json --request-id PREVIEW_REQUEST_ID` 预检查请求结构，再用 `sp2build batch apply --input batch.json` 执行。把 `PREVIEW_REQUEST_ID` 换成不同于执行请求的新 ID。
4. **复查并迭代。** 复读目标件和连接，按同一视角复拍并复测。结果不合预期时可恢复检查点。切换载具或重启游戏后，重新获取会话并建立检查点。

任务超时后先查询原操作或请求 ID，再决定下一步。直接使用新 ID 重试可能再次执行编辑。

需要保留设计时，请使用游戏的保存流程。JSON 快照用于检查当前设计器状态。使用 Funky Trees 时，可先运行 `sp2build funky describe --name clamp` 查询示例函数，编译通过后再在游戏中验证实际输入和输出。
