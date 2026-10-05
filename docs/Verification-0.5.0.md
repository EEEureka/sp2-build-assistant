# 0.5.0 最终验收与交付

2026-10-05。0.5.0 已完成本版规定的代表场景验收，正式 DLL、全局 CLI 和 skill 已安装并加载核对。后台游戏通过插件正常退出；玩家原始飞机未用于写入。全过程没有使用 computer use、桌面键鼠或 DSH。

本版支持对局部零件做可测量、可比较、可恢复的精修。它为高还原度建造提供操作能力和方法，但尚未证明 Agent 能独立建出整架 C17 级复刻。

## 本版可用能力

- 查询当前件或完整目录模板的有效属性、原生默认值、单位、资源和当前可写条件。
- 编辑窗体、文字、贴花、整流罩、起落架及选定机构字段；编辑当前飞机的材质槽、纹理、颜色和表面参数。
- 按明确坐标系和枢轴移动、旋转刚性部件组，检查原生随动依赖，配置镜像及挂点对齐。
- 测量真实网格间隙、截面、接缝和对称误差；固定原生相机视图复拍，比较状态差异，撤销或回滚。
- 通过原生 API 加载指定存档、进入设计器、选择部件、返回菜单和退出。编辑仍只作用于设计器中已加载的飞机。

调用统一使用 `sp2build`，详见[局部精修指南](Precision-Workflow.md)、[完整 CLI 手册](CLI-Usage.md)与[skill](../skills/sp2-build-assistant/SKILL.md)。

## 验收证据

以下目录均相对于 `tests/artifacts/precision-0.5.0/`。完整失败及修订过程保留在[实施记录](Execution-0.5.0.md)，未覆盖范围见[验收总览](Acceptance-Status-0.5.0.md)。

| 项目 | 已执行结果 | 证据 |
| --- | --- | --- |
| 必需属性适配 | 94/94 个字段有代表场景正向原生参考及负向用例；非法输入矩阵 471 项通过，17 种腿样式 27 项通过 | [逐字段索引](../knowledge/native-adapter-evidence.json)、dev19–dev21 矩阵 |
| 局部精修 | E1 机头玻璃、E2 挂架/吊舱/贴花、E3 腿轮机构，各 3 个固定起点、各 2 轮收敛；独立几何与状态复核通过 | 总览中的 E1/E2/E3 索引 |
| 旧版性能对照 | 同一 874 件构型、每批 8 件 raw 编辑，两版各 30 次；中位数 11.971→3.874 秒，降低 67.64%，新版每批重建一次 | `relative-performance-native-reset.json` |
| 连续编辑与恢复 | 250 轮，752 项完整编辑/恢复及历史限制检查通过，最终恢复基线；13 张原生图和内存曲线均实际查看 | `dev24-retention-250/` |
| 正式 DLL 基础回归 | 隐藏验收入口拒绝 3 项、缩放恢复 9 项、原生选择/导航 16 项、顺序与失败恢复 18 项通过；3 张原生视图已查看 | `release-hidden-gate/`、`release-scale-recovery/`、`release-native-navigation/`、`release-ordered-recovery/` |
| 正式 DLL 原生对照 | 网格转换 14 组逐项一致；表达式 float/bool/string 及独立上下文 55 项一致 | `release-native-references/` |
| 编译与契约 | 正式构建移除验收写入辅助代码；C# 核心及 74 项 Python 测试通过；长测 1283 份、最终回归 217 份实际产品返回 schema 零错误 | `release-build-isolation/`、`release-unit-tests.txt`、`dev24-retention-schema.json`、`release-regression-schema.json` |
| 安装与文件保护 | 全局入口、DLL 哈希、已加载 buildId、32 个安装文件和 skill 一致；两个最后的后台进程均原生退出，各核查 939 个玩家文件不变 | `release-deployment/`、`dev24-retention-host-a/craft-preservation.json`、`release-host-a/craft-preservation.json` |

## 长期内存结论

修复了两个已通过原生对照定位的来源：临时 MeshGL 未析构，以及设计器重载时重复编译表达式。修复分别限制在已核查的游戏模块；未知模块不会启用这些兼容补丁。表达式保留原生解析器/编译器语义，每次调用独立绑定常量，模板缓存上限 256，不保存部件上下文。

250 轮的历史填满后，默认 Windows 堆已用量没有持续上升（周期 124→249 约 -0.153 MB），模板数固定 84，Mesh 数固定 3684，材质对象可自然回收；完整状态恢复通过。本工作负载的 T18 持续累积回归关闭。

进程私有内存并非平线：满容量后的 125 个样本净增 281.596 MB，其中出现一次 Unity 预留内存扩容；末 30 轮拟合仍为 +0.372 MB/轮。后段表现为分配/释放波动，扩容的精确分配者未归因。另做 30 次只截图对照，默认堆减少 5.656 MB、私有内存最终保留增加 211.608 MB，过程中有明显释放；随后 60 秒空闲私有内存不变。没有强制 GC，也没有把重叠指标相加。此结论限于有限、固定构型的观测，不能证明任意构型、任意时长或全部图形资源没有泄漏。原 dev22/dev23 长测失败完整保留，详见 `dev24-retention-250/memory-gate-review.json`。

## 安装身份与使用

- 游戏：0.7.8.103 / XML 25 / Windows Mono / BepInEx 5。
- CLI / DLL：0.5.0；正式运行返回 `releaseStatus: released`。
- 已实机加载 buildId：`2d0160ab-8628-4aa6-95b5-d58d087e3e46`。
- DLL SHA256：`B3CC470896AFC6D4DCBBAC0C2F8E6F0895AC34AB53D5ED50CFE1EEDEB03591C5`。
- 全局命令：`sp2build`；通用 skill 已同步至 `%USERPROFILE%\.agents\skills\sp2-build-assistant`。
- 完整包：`dist/SP2BuildAssistant-0.5.0.zip`；独立 skill 包：`dist/SP2BuildAssistant-Skill-0.5.0.zip`。包内不包含游戏程序集、测试宿主、测试飞机、实例令牌或验收故障注入构建。

游戏目前已退出。下次正常启动即可加载已部署版本；Agent 应先运行 `sp2build version --json` 和 `sp2build designer status --json`，确认加载身份后再编辑。

## 仍然存在的能力边界

94 是适配字段数，不是所有 4529 个类型/字段对都已认证。动态组合、额外 Mod 类型仍须查询当前条件并实测。动画关键帧通用编辑、完整机构运动路径碰撞证明、从单张照片自动恢复真实尺寸、飞行性能/静稳定性认证均不在本版范围。历史真实鼠标拾取证据继续保留，本轮 API 选择测试不等同于新做鼠标验收。E1–E3 是开发者自验，整机审美与还原度仍需用户判断。
