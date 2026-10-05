# 0.3.1 验证与部署记录

日期：2026-10-02。目标游戏 0.7.8.103 / XML 25 / Windows Mono / BepInEx 5.4.23.5。

## 已完成

- DLL 编译成功，SHA-256：`60EF5764E4C6A5FEFD1B5EA2C5606D6E5422BF0900F7F3D1844A9BFC169AFECC`。
- DLL MVID：`085d3750-1a87-4596-8af2-ff2f52b69685`。
- 独立 DLL 已部署至游戏 BepInEx/plugins；全局 CLI 为 0.3.1；`~/.agents/skills/sp2-build-assistant` 已同步。源文件与安装的 DLL、三个 CLI 模块、skill 文件共 8 个文件逐一哈希一致。
- 离线测试 144 项通过：引用生命周期 14、形状 30、快照 12、assembly 15、视觉 45、CLI 28。覆盖旧数字/临时引用拒绝、同类型连续复用、多件模板复用、重建不误失效、小目标/遮挡细节图、资源预算跳过、命令发现与离线帮助。
- JSON Schema 契约验证 104 项通过。使用旧 DLL 0.3.0 的实际只读返回验证，包括选择、目录、挂点、射线、快照、变量、历史等，以及先前真实 visual capture。另验证成功/失败/异步/文件回执，故意错误的路径/类型会被拒绝。
- 安装后的全局命令发现、普通命令 schema、operation schema、version 及三种帮助共七项冒烟检查通过。
- skill-creator quick_validate 通过。开发验证依赖安装在临时虚拟环境中，CLI 无新增第三方运行依赖。
- 已打开合成小目标的 overview 与 g1-isometric PNG，确认总览维持相对位置，自动细节图能显示总览中难以看清的小模型。
- 已通过用户授权的 DSH 后端向其既有工作会话发起两轮只读验收。第一轮确认输出路径、CLI/operation 映射、异步/文件回执与 skill 指引，并提出 FB-018/019；修订后第二轮复核挂点向量语义及五种帮助调用全部通过，无新增问题。DSH 自行去重更新其 tool-feedback.md，将两项移至 FB-R10/R11；新 DLL 行为仍保留待实机验证。本轮没有创建持续轮询任务。

## 首次部署时的实机边界（历史记录）

本轮只通过全局 CLI 读取当前设计器，没有对飞机发起写入、检查点、撤销、恢复、切换飞机或捕获请求。旧 DLL 最后读回为 0.3.0 / MVID `3c86faf6-5b70-4667-8b7f-a32f96b3392f`，Super Wasp test 会话 revision 9。

部署后复查时游戏进程已不存在，designer status 返回 bridge_not_running。因此当时 **0.3.1 新 DLL 尚未完成加载及实机验收**；复制到磁盘不等于已加载。本轮没有实现热更新，也没有主动关闭或重启游戏。

当时待验证项目：

1. 新 DLL 版本/MVID、射线新增 part/query 字段与同 revision 零件读回一致。
2. 临时测试件删除—新增，核对 reusedPartIds；新 temporaryId 连接/修改成功，旧数字/旧临时名失败且整批恢复。
3. missile/wing assembly 范围、普通删除默认行为，以及选中件删除后 ID 复用不会选到替代件。
4. 当前真实网格的小目标、多组、遮挡和预算案例；实际打开推荐 PNG，核对零件及联合空间关系。
5. 每组写入测试前建立检查点、停止并发编辑，完成后独立复读验证恢复。游戏不可用时不得将这些项目记为通过。

## 证据与资料

- tests/artifacts/unit-0.3.1.log：144 项功能测试。
- tests/artifacts/contracts-0.3.1/report.json：104 项契约检查及实际返回。
- tests/artifacts/deployment-0.3.1.json：安装哈希、全局命令检查、游戏不可用结果。
- tests/artifacts/visual-unit/auto-small/：合成渲染图片与 manifest。
- tests/artifacts/dsh-0.3.1-request.json、dsh-0.3.1-latest.json：DSH 第一轮验收请求和结果。
- tests/artifacts/dsh-0.3.1-final-request.json、dsh-0.3.1-final-latest.json：修订后复核请求和结果；认证信息未写入发布包。
- [修订内容和兼容规则](Agent-Feedback-0.3.1.md)、[调用手册](CLI-Usage.md)、[视觉手册](Visual-Usage.md)。

历史实机记录：[0.3.0](Verification-0.3.0.md)、[0.2.2](Verification-0.2.2.md)、[0.2.1](Verification-0.2.1.md)。历史通过不能替代新版实机验收。

## 2026-10-02 补充实机验收

用户启动游戏后，确认 DLL 0.3.1 / MVID 085d3750-1a87-4596-8af2-ff2f52b69685 已加载。DSH 完成八类常用场景及默认删除连接父件的补充测试：目录/挂点、空间射线、两组小目标图与 pick、机身形状与真实可选体积、机翼/控制面/对称、变量和输出、ID 生命周期及事务拒绝、undo/rollback。全部所测项目通过。

DSH 完成后的独立 CLI 复读为 revision 47；与 revision 1 基线完整 XML 比较通过，仅九个零件有约定范围内的 Euler 重建差异。351 个零件、357 条连接、9 个全局 Setter 一致，无临时测试件或测试变量。首轮后追加的父件删除测试期间曾读到临时件，该中间快照不是最终结果。

证据：tests/artifacts/live-0.3.1-20261002/ 的 baseline.json、final.json、final-comparison.json、dsh-final.json；DSH 工作区 acceptance-0.3.1/REPORT.md 及原始请求/返回。全量非空选择、径向对称、多实例、其他控制面样式及运行时飞行表达式未覆盖。新反馈 FB-020/021/022 和 FB-014 的说明问题集中进入 0.3.2。
