# S04 反馈修订：CLI / skill / DLL 0.4.6

日期：2026-10-02。S00–S03 已通过；S04 已建造左右平尾及升降舵，控制面选点缺陷需新 DLL 复验后才进入 S05。

## 成立的问题与源码依据

`wing.control.add` 旧实现遍历零件挂点并选择第一个可兼容的接收点。JWing 根部 AP0 与表面 AP1 均可接收控制面的 Normal 类型；若机翼还未接入机身，空闲 AP0 被优先占用，机翼随后无法通过根部连接宿主。这个问题与是否 flipped 无关，也不应要求 agent 靠“先接机身再加舵面”的隐含顺序绕开。

本轮真实证据：`S04/part-11-after-mirror.json` 的 AP0/AP1 均空闲；`part-11-preconnect.json` 显示添加控制面 #12 后 AP0 被它占用，AP1 仍空闲。两个后续 connection.connect 被拒绝且批次回滚指纹不变；先移除控制面、连接机翼、再加控制面后，`part-11-after-elev2.json` 的 AP0 连 #5，AP1 连 #12。该恢复只证明绕开方式可用，不证明工具缺陷修复。

原生依据：`Game/Assets/Scripts/Design/Tools/JWingTool.cs` 创建对称控制面连接时将机翼 AttachPoints[1] 连到控制面 AttachPoints[0]。`AttachPointData.IsSurfaceAttachPoint` 标识表面接收点，`IsAvailable` 允许表面接收点在已有连接后继续接收。插件改为按这些原生字段识别兼容表面，不硬编码索引、不回退占用结构根部。

0.4.6 的 `wing.control.add` 结果新增 `controlAttachPointId`、`wingAttachPointId`、`attachmentBasis=native_wing_surface_receive_point`，schema 与 skill 一并解释。没有兼容表面时明确拒绝并走原有整批恢复。通用 connection.connect 的行为不变；已知挂点不可用/类型不兼容时的预期拒绝不算另一个缺陷。

## 验证与下一步

FB-033 的材质槽差异是事实，但当前证据不足以认定工具错误：#10 来自 Horizontal Stabilizer 多件模板，#12 是 helper 从独立 Standard Flap 单件模板创建；helper 没有从右侧控制面继承涂装的输入或承诺，link 也只建立同步组。0.4.6 返回所用 `templateId` 并补充默认来源说明，不自动覆盖已有材料。是否出现肉眼可见差异与是否需要复制涂装是另一个尚未实测的外观问题，不能由相同 style 推定。

FB-034 已核实并撤回：oblique 是 DSH 自定义视图对象的名字，不是内置字符串枚举；输出回显该名称不等于注册为内置相机。丢弃 direction/up 后裸传自定义名被拒符合 schema，无需添加猜测方向的别名。

新 DLL 构建及 215 项离线回归通过，0.4.6 的 DLL、全局 CLI 与 skill 均已部署。该回归套件不覆盖 Unity 内实际选点调用，不能替代新版本运行时验证。当前游戏仍加载 0.4.4；已完成本阶段其余独立检查，DSH 暂停在 12 件 Aircraft、revision 29，等待用户保存并重启后复验。

复验应覆盖：在当前飞机的可恢复检查点保护下，为一个尚未连接宿主的原生 JWing 先添加控制面，确认返回与独立挂点/连接读取均落在表面接收点，根部仍可接宿主；有控制面的表面可以继续增加不重叠控制面；错误/重叠输入仍应拒绝并恢复。对镜像翼也检查；最后恢复完整 S04 设计，确保无临时件。不得以旧版改变顺序后成功代替新版本首个操作成功。

## 重启后实际验收结果

2026-10-02 用户重启后已加载 0.4.6，buildId 4d48964c-6ef2-4254-88d6-1270528bee88。DSH 对普通翼与 flipped 翼均按“先加控制面、后连根部”成功，AP1 接收控制面而 AP0 保留给宿主。同一翼面添加两个不重叠控制面成功；重叠请求返回 control_surface_overlap，整批恢复且指纹一致。templateId 可从当前目录核实。结束回滚到本轮新检查点，恢复 12 件 / 11 连接、原材料与对称关系，指纹一致；协调端 72 项证据复核通过，并实际打开整机与尾翼联合图。FB-032 可标已解决(0.4.6)。

证据：DSH staged-build/S04/retest-0.4.6/；协调端 tests/review_staged_s04_runtime.py 与 tests/artifacts/staged-build/S04-review/runtime-0.4.6-review.json。注意 part-13-after-ctl2.json 等文件实际属于失败请求后的 rev6，不能用作成功重试 rev7 的挂点证据；第二控制面的成功采用 part-15-tempctl2.json（rev7）和 connections-after-step4.json / snapshot-after-step4.json（rev10，AP1 同时连接 14、15）。

FB-035 的 revision_conflict 是确实发生的保护拒绝，但“成功响应不锁定后续 revision”已在安装 skill 说明。history 中 SP2Build baseline 来自桥接在当前撤销头与快照不同时调用 CreateUndoStepAsync 的基线步骤，不是手工检查点名称，不能由该标签确定 rev5→6 的实际变更来源。本轮缺少两时刻完整 XML 差异，来源仍未确认；冲突响应附带当前身份可作为另一个易用性建议，不影响本轮挂点修复验收。
