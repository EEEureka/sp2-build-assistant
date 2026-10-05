# 0.3.2 验证与部署记录

日期：2026-10-02。目标游戏 0.7.8.103 / XML 25 / Windows Mono / BepInEx 5.4.23.5。

**当前状态：0.3.1 完成所测实机场景；0.3.2 已编译、离线验证并安装到磁盘，CLI/skill 已生效。游戏仍加载 0.3.1，新 DLL 的实机验收待桌面解锁后重启完成。**

## 0.3.1 实机验收与恢复

用户授权通过 DSH 后端测试常用操作并收集反馈。本轮先完成全部场景，再集中修订，未在测试中途更换 DLL。

| 场景 | 实测结果 |
|---|---|
| 目录、属性、选择与挂点 | 空选择正确；可查询未使用零件及原生介绍；铰链角色、坐标、轴方向字段一致 |
| 空间关系 | 射线结果的内嵌零件身份与快照一致；区分拓扑连通和几何交点 |
| 视觉 | 两个独立小零件组保留相对位置；自动推荐总览与两张细节图，实际打开图片；关闭细节与 visual.pick 通过 |
| 机身、连接与删除 | 临时机身长度 1→4→1，外观与编辑器 Collider 同步；探测射线 miss→hit→miss；普通连接保留位置、Euler、四元数及缩放；默认删除只删指定件 |
| 机翼、控制面与对称 | NACA/弦长/翼展、StandardFlap；镜像对称创建、联动、开关、link/unlink；assembly 删除范围正确且保留另一侧 |
| 变量与输出 | 全局变量增改删重排；临时干扰弹发射器输出绑定、修改 activator/priority、解绑；clamp 编译检查 |
| 引用生命周期与事务 | 同批删除再新增复用 ID 有提示；新 temporaryId 可用；旧数字/旧临时引用拒绝；先合法再非法的批次整体恢复；不支持的 assembly 根明确拒绝 |
| 恢复 | 带历史头守卫的 undo、checkpoint rollback；最终独立完整 XML 比较通过 |

验收游戏 PID 31908，DLL 0.3.1 / MVID 085d3750-1a87-4596-8af2-ff2f52b69685，载具 Super Wasp test。最终状态 revision 47：**351 个零件、357 条连接、9 个全局 Setter**，无临时测试件或变量。

独立比较基线 revision 1 与最终快照：equivalent=true、differenceCount=0，九个零件存在每轴 0.0001° 容差内的原生 Euler 重建差异；其他 XML 内容按约定严格比较，原生生成目标集合按去重集合比较。最终指纹为 aab31b07039e1cd5f46ecdf6883cf7cea030afcea96c0fdfcae7778275ad2404，不能用与初始指纹不等单独判定恢复失败。

未覆盖：非空用户选择及其删除后状态、径向对称、多实例、其他控制面样式、全部参数边界、飞行中表达式输出。所测场景通过不代表这些项目已验收。完整历史记录见 [0.3.1](docs/Verification-0.3.1.md)。

## 0.3.2 已完成

- 依据确认的 FB-020/021/022 和 FB-014，新增显式结构化读取、统一输出来源及视觉组索引字段、严格变量重排校验，并解释失败恢复后的 revision；默认 legacy 接口保留兼容。详见 [修订说明](docs/Agent-Feedback-0.3.2.md)。
- DLL 编译通过，MVID 2695c300-e8f7-43f1-8cb2-dcce6167fcdf；SHA-256 B08EEE05A5BE833B7737E5E7DF255E7CF2E212527982D2296180133A914ED720。
- **170 项功能检查通过**：读取模型 23、引用生命周期 14、形状 30、快照 12、assembly 15、视觉 45、CLI 31。新增读取模型检查使用真实飞机 XML 验证 357 条连接与 9 个 Setter 的投影，拒绝错误类型和非完整排列。
- **104 项旧响应契约兼容检查 + 10 项结构化契约正反例通过**。结构化案例是离线构造，输出绑定取自 0.3.1 实测记录；不冒充 0.3.2 实机返回。
- 独立完整快照比较器另经 7 个正反例检查，验证真实属性/ID/变量差异不会被 Euler 容差掩盖。
- skill-creator quick_validate 通过；源目录、已安装的 CLI/知识库/skill 和 DLL 共 **15 个文件哈希一致**。全局 sp2build 八项检查通过，包括版本、发现、schema、帮助与当前游戏状态读取。
- DSH 再次复核新版 CLI/schema/skill 四类问题，全部通过，无新增问题。旧 DLL 请求 variables list --view structured 明确返回 unsupported_bridge_feature；legacy 仍可读取。台账已区分 schema 已核验与新 DLL 行为待验。
- 用户允许自行重启；实际桌面已锁屏，未退出游戏或绕过锁屏。已映射的旧 DLL 保留为 .previous，新 DLL 安装至游戏 BepInEx/plugins/SP2BuildAssistant.dll。**磁盘更新不改变已加载程序集**，未实现热更新。

## 解锁后待完成的实机验收

1. 正常退出并重启游戏，返回目标飞机设计器，读回 0.3.2 版本/MVID；重新建立会话基线及检查点，旧会话 ID 和检查点不可复用。
2. 结构化连接、Setter 与原始 XML 逐项比对；两种输出来源查询字段、内容和计数一致；默认 legacy 兼容。
3. 临时变量合法重排及小数、数字字符串、重复、缺失、越界负例；失败整批恢复，并验证 rollbackResult 前后 revision 与实际状态相符。
4. 视觉 manifest 的 groupIndex/index、detailStatus 与推荐图索引一致；保留相对空间关系。
5. 完成测试后恢复新基线，再以独立完整 XML 比较器复核。

## 证据位置

- tests/artifacts/live-0.3.1-20261002/：baseline/final、最终比较、DSH 最终报告、机身实际 Collider/射线/连接姿态复核，以及比较器正反例。
- DSH 工作区 D:/codeSpace/sp2_craft_edit/acceptance-0.3.1/：八场景原始请求、返回与 REPORT.md；tool-feedback.md 为其统一反馈台账。
- tests/artifacts/unit-0.3.2.log、contracts-0.3.2/report.json、contracts-0.3.2/structured-offline.json：功能与契约检查。
- tests/artifacts/deployment-0.3.2.json：文件哈希、全局命令与仍加载 0.3.1 的运行时证据。
- tests/artifacts/live-0.3.2-20261002/dsh-cli-request.json、dsh-cli-final.json；DSH 工作区 acceptance-0.3.2-cli/REPORT.md：第二轮只读复核。

发布包排除测试数据、运行日志、实例 token、DSH 认证信息和游戏程序集。调用说明见 [CLI 手册](docs/CLI-Usage.md)；各版本实机证据分别记录，历史通过不替代新版验收。
