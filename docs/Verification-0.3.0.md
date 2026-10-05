# 0.3.0 验证与部署记录

日期：2026-10-02。游戏 0.7.8.103 / XML 25 / Windows Mono / BepInEx 5.4.23.5。

## 部署与版本

- 全局 CLI 和独立 DLL 均为 0.3.0；CLI 仍使用 `sp2build`，无新增 Python 第三方依赖。
- 最终 DLL MVID：`3c86faf6-5b70-4667-8b7f-a32f96b3392f`。
- 最终 DLL SHA-256：`CAABB76DA8797FAF685F2E4B5490B4FB1D6F2E370E039DB61CA29D4437C54C83`。
- 已自主启动游戏并通过 CLI 读回最终 MVID；新功能已实际加载，不只是复制到磁盘。
- 游戏源代码及游戏原程序集仅作只读参考，继续使用独立 BepInEx 插件。
- 主安装 skill 和既有 AppData 缓存副本同步视觉工作流；仍要求调用全局 CLI，并实际用 harness 图片工具读取 PNG。

## 实现范围

新增 `visual.resolve`、`visual.capture`、`visual.pick`。支持选中件、精确 ID、整机、原生导弹/机翼组件、明确边界分支及有界邻域；多组联合正交三视图/斜视图保留共同尺度和真实变换，可另取组内细节图。

从 Unity 原生登记网格复制实际顶点/三角面，在后台 CPU 绘制，附原图、标签图、精确 ID 图、变换/投影矩阵、分组中心偏移、可见像素、哈希及遗漏项。采用不透明双面、分组配色和简化光照，不代表游戏材质画面。

## 离线检查

最终构建通过 **113 项检查**：ShapeCodec 30、SnapshotState 12、AssemblyScope 15、VisualCore/VisualScope 37、Python CLI/下载 19。命令：`tests/run-unit-tests.ps1`。另通过 skill 格式检查。

视觉覆盖：分支边界/环路/未知 ID、选中与整机范围、无静默截断、共同尺度、分组实际偏移、投影像素映射、遮挡、负缩放、无网格件、输入不可变、几何哈希、取消、NaN/Infinity 三角面过滤、拼图实际像素预算、保留文件名/Windows 设备名，以及 PNG CRC/解压/RGBA/精确 ID 往返、下载路径约束与哈希。

## 实机检查

本地原始结果保存在 `tests/artifacts/`，含玩家飞机快照，不放进分发包。以下计数包含读回和断言，并非独立产品功能数量。

| 阶段 | 结果 | 证据目录 |
| --- | --- | --- |
| 首轮只读检查 | 40/41；整机因原生非有限坐标失败，完成其余案例后统一修正 | `visual-accept-7c6ec4e1` |
| 修正后只读检查 | **43/43** | `visual-accept-2cbbc791` |
| 编辑刷新/异步补充 | **12/12** | `visual-refresh-e4539908` |
| 最终构建版本及边界复核 | **6/6** | `visual-release-0b712674` |

只读案例使用 Super Wasp test（352 件），覆盖机身、左右机翼、单/双导弹组件、旋转件、零件坐标系、自定义视角、整机、真实连接边界、空选中、重叠范围、会话/修订冲突和错误输入。图片已通过本地图片工具实际打开；按 ID PNG 解码选像素，再用 visual.pick 读回相同原生 ID。整轮前后 XML、选中和撤销历史完全一致。

第一轮还发现全 Renderer 遍历会纳入编辑器裁剪预览和粒子。已改为原生 PartMaterial 登记表面及归属 skinned mesh，排除 HideDuringScreenshot 编辑器对象。无效坐标仅过滤受影响三角面，每项遗漏及数量进入 manifest，不能静默当成完整结果。

补充案例通过鼠标选中机翼后调用默认范围，验证异步提交到 wait 下载、result 重复下载一致、取消终态和只读不改飞机/选择/历史。随后添加临时 Fuselage，验证长度变化取得新网格/哈希/revision、撤销恢复几何、位移更新世界包围盒、旧包不可变及第 4 包淘汰第 1 包。回滚检查点后 `restorationVerified=true`，352 件飞机及原选中 ID 恢复，再取消测试选择。碰撞采样点有读回，本轮没有把单点当作完整碰撞体重新验收。

脚本初次误用 `part.update.position` 被接口拒绝，正确格式为 changes 内的 position 属性。记录在 `visual-refresh-7a1ffbbc`，飞机仍成功回滚。修正测试输入后 12 项通过，未为错误测试放宽产品契约。

写入/回滚后 XML 仅有原生生成目标集合顺序及微小 Euler 重建差异，见 `visual-final-xml-diff.json`，在既有恢复规则内；不声称写入测试后 XML 字节完全相同。普通非旋转字段仍严格比较。

最后仅修正像素预算和视图名保护，未改网格采集/绘制路径。最终构建加载后，游戏进入默认新建 Aircraft（2 件）；初次沿用旧 Super Wasp ID 的脚本得到 part_not_found（`visual-release-2dc14c93`），随后改为查询当前 ID。6 项复核确认最终 MVID、overview/con 名称拒绝、奇数拼图实际预算拒绝、当前 Fuselage 下载成功且 complete=true，以及飞机/选择/撤销历史不变。没有通过 CLI 打开或修改其他保存飞机。

## 限制与未验收项

- 双机翼、双导弹组件样例 complete=true。整机捕获 **163,909 个三角面**，complete=false：6 个控制面（24/25/26/27/78/79）的 **200 个非有限三角面**被过滤，另有 15 个 TextDecal/TextureDecal/ModifierWindow 零件无可捕获表面，均明确列入 manifest。
- complete 仅表示受支持网格的采集遗漏，不表示材质完整。纹理、涂装、贴花、透明/镂空 shader、shader 顶点变形不完整复现；粒子和编辑器手柄不属于本版表面载体。
- 已验证当前 Codex 从 CLI 到实际读取 PNG 的链路；**未验证 DSH harness 是否把图片传给视觉模型**。skill 要求检查平台能力，不能把只读到路径当成看图成功。
- 第三方 Mod、复杂 skinned 动画、多实例并发、大规模长时运行未全面验收。缓存与取消检查不代表所有并发条件已穷尽。
- 原生材质渲染、GLB、深度/法线图、剖切、透明上下文及透视相机未实现。
- 0.2.2 assembly 删除随包交付，本轮只测试视觉组件范围，**未补做组件删除/对称删除/删除后失败恢复的实机写入案例**；原有 15 项离线检查通过。视觉读取不能替代删除验收。

调用格式见 [视觉手册](Visual-Usage.md)。历史记录：[0.2.2](Verification-0.2.2.md)、[0.2.1](Verification-0.2.1.md)。
