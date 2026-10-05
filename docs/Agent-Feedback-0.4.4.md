# S03 反馈修订：CLI / skill / DLL 0.4.4

日期：2026-10-02。DSH 已停在 Aircraft 的 8 件完整连接状态；S00–S02 通过，S03 待补丁运行时复验。用户负责保存当前飞机、重启并重新进入同一飞机设计器。安装新文件不等于正在运行的游戏已加载它。

后续实测更新：用户已保存重启，确认加载 0.4.4，buildId=2ec78fcf-ce37-4f77-95e4-1e6f295ef667。DSH 在新检查点保护下删除单侧翼，协调端通过 computer-use 激活当前游戏窗口，触发 `DesignerScript.OnApplicationFocus(true) -> SaveDesignerCraft` 原生保存居中。有效面从约 x=0 移到 x=-2.8833065，原生缓存仍在约 x=0，`nativeCacheStale=true`；连续查询不改变缓存或身份。随后第一次创建沿有效面正确放置，显式连接后 8 件全部连通；同步启停均有独立 shape 回读，回滚后 revision12 指纹与新会话 revision1 完全一致，原 8 件位置/旋转/组恢复。协调端新运行时证据 **39/39** 通过并实际查看最终三视图。S03 已通过；以下“复验要求”均有对应记录于 DSH `S03/retest-0.4.4/`。

新警告关联 #8，删除 flipped 翼时警告消失；原生 CoM 缺陷没有消失。XML caveat 生效，用户保存后的尺寸元数据刷新已验证。三心摘要明细的追加反馈由 CLI / skill 0.4.5 补充说明，DLL 保持 0.4.4。

## 核实与处理

| 反馈 | 独立核实 | 0.4.4 处理 |
| --- | --- | --- |
| FB-027 保存居中后首个镜像落点错误 | 确认插件缺陷。`Designer.Save` 的 `RepositionAircraftOnGround` 平移整机而未刷新 Symmetry；旧插件查询/创建使用该缓存，批次末尾才刷新。旧面 x=0，实际机身面 x=-2.883307，首次新翼错误落在 x=+2.233307。 | 查询在克隆配置上按当前主控制器位置和 MirrorPlaneOffset 推导有效面；报告旧缓存是否过期。每个受 revision 保护的写操作前刷新原生缓存；创建和对称几何校验也使用有效配置。 |
| FB-028 镜像翼局部质心 Y 变成 0 | 确认原生游戏缺陷，独立于 FB-027。`WingBuilder.cs` 的 flipped 分支使用 `CentreOfMass.y -= CentreOfMass.y`；`JWingData.OnWingMeshRebuilt` 将其直接作为 Part.CenterOfMass。#7 局部 Y=.1585702，#8 为 0，两个世界质心相差约 .158571 m。 | 对游戏 0.7.8.103 的已连接 flipped JWing 增加 `native_flipped_wing_com_y_zeroed` 警告及相关零件 ID。保留游戏实际质量和重心，不更改原生飞行物理，也不伪造“修正后的”三心。原生缺陷仍存在。 |
| FB-029 snapshot XML 整机宽度仍为单翼宽度 | 确认保存时元数据滞后：Designer.Save 才更新 Size/BoundsMinimum/BoundsOffset；rev24 XML 宽 7.066614 m，当前网格宽 12.8334 m。XML 正确反映原字段，并非视觉几何返回错误。 | includeXml 时增加 `xmlMetadataCaveat`；schema/skill 说明请从 parts.geometry 或同 revision visual manifest 获取当前尺寸。只读查询不重写原生 XML 元数据。 |

`symmetry.get.configuration.mirrorPlaneDistance` 遵循 `dot(normal,position)+distance=0`；normal=[1,0,0] 时平面 X 是负 distance。`basis/originPartId/aircraftMirrorPlaneOffset/planeEquation/nativeCacheStale/nativeCachedFrame` 提供依据与缓存诊断；查询只操作配置副本，不触发原生缓存事件。全机包围盒中心不代表对称面。`symmetry.create` 不承诺自动连接副本到宿主。

## S03 已有证据与边界

DSH 完整记录在 `D:/codeSpace/sp2_craft_edit/staged-build/S03/`：final-rev24 的 33 个完整信封、bad-mirror 的错误创建/恢复证据、batches 的同步开关测试、visual 的四视图。协调端实际打开 overview，确认双侧后掠/渐缩/上反一致；检查原始返回与源码，不以报告文字或 success 代替验收。

正确的第二次镜像在旧 DLL 0.4.0 上发生，是上一次操作刷新缓存后的结果，**不能证明缺陷已修复**。同步启用时单侧 chord 修改传播两侧；关闭时仅影响目标侧，之后恢复原弦长并重新启用。删除加 unlink 的失败批次回滚恢复成功且指纹相同，证明该实际失败路径的事务性；不保证所有未来原生恢复都必然成功。

三心仍是原生设计器布局信息；没有验证飞行稳定性、配平或原生 UI 三心标记完全一致。XML 元数据下次保存是否刷新与 0.4.4 实际对称行为均在用户重启后的复验中检查。

## 复验要求

1. 确认加载 0.4.4，并重新读取会话、零件身份、配置、几何及三心；旧 session / checkpoint / revision 全部作废。
2. 通过可恢复的当前飞机操作重现保存居中造成缓存落后的条件。必须实际观察 nativeCacheStale，核对有效平面与主控制器；只验证启动时缓存新鲜是不充分的。保存重定位可能晚于命令完成，应使用一致 revision。
3. 在检查点保护下验证第一次创建即沿有效面放置，明确检查连接、同步开关、几何与碰撞；恢复到原 8 件阶段结果。不得用第二次正确掩盖第一次失败。
4. 检查三心原生缺陷警告及 snapshot 元数据提示；不把提示新增当作物理缺陷修复。
5. S03 通过后才进入 S04 平尾/升降舵。失败则先核实，再收集同阶段独立反馈并合并下一补丁。
