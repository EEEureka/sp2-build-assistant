# 0.4.11 实机验收

2026-10-02，用户重启后由 Codex 直接通过全局 `sp2build` 验收，未调用 DSH。**原生设计器截图的常用流程、相机恢复及 FB-042 实时挂点修复通过。没有修改 DLL 或飞机，无需再次重启。**

## 环境与状态

- CLI / 已加载 DLL：0.4.11；buildId `4c2ed599-e6da-411b-a214-f1311690ef0e`；PID 6756；游戏 0.7.8.103 / XML25。
- Aircraft：42件完整双涡桨构型；场景实例数1、active1、extra0，healthy。
- 当前会话 `310038788ff940fbb990bb94ff25dcd2`，revision1；指纹 `4d62dfe775846f960c8917d2f361fcc6c1cdb050028858f1e3f65e1d12133723`，与重启前一致。
- 全轮只读；所有截图前后飞机完整快照、选中状态和历史完全一致。原生历史只有 Loaded Aircraft，canUndo/canRedo 均 false。真实窗口截图前后均查看，玩家原视角及选中轮廓保留。

## 已验证

| 场景 | 结果与证据 |
| --- | --- |
| 当前玩家视角 | 原生材质、涂装、背景和当前选中轮廓与窗口一致，默认1280×800保持16:10；不包含菜单/鼠标/独立操作柄相机 |
| 七个预设方向 | front/right/top/back/left/bottom/isometric 正交渲染正常；六轴朝向独立数值验证，25张请求图片均实际打开查看 |
| 任意角度与投影 | 方位45°/仰角25°分别透视和正交；方位−35°/仰角−10°/滚转30°；当前视角转正交；相机方向和投影矩阵独立验证 |
| 局部取景 | 7件右侧涡桨总成自动聚焦，周围机翼/机身/起落架保持可见；侧向显式target `[2.6,3.45,1.05]`、distance10m、正交半高2m均精确返回 |
| 相机恢复 | 每次manifest.cameraBefore/After相同；全轮开始、非法输入后、异步测试后的current PNG逐字节相同，SHA256 `70063bc8ace6be9212fcac638def6dfed16e645958ea6d84f71d568c096f01fd` |
| 文件与异步 | 每个文件独立复核SHA256和PNG尺寸；推荐列表包含全部请求视图，overview复制第一张；`--async`受理→`operation wait --output-dir`下载成功 |
| 8类错误输入 | 非法projection、custom缺仰角、current设置distance、重复视图名、不存在部件、超1600万像素、过期session和revision，分别明确拒绝；之后正常截图成功 |
| 动态挂点 | 6个动力零件的14个挂点与独立geometry返回的AttachPoint碰撞体中心一致（误差<10⁻⁶m）；parts.get和connections.points逐字段一致 |

FB-042 原例 #35 AP1 当前世界坐标为 `[2.6,3.468876,1.88289]`，局部约 `[0,0,-0.254325032]`；definitionLocalPosition仍保留旧定义 `[0,0.1141,-0.2663]` 供对照，positionSource=`live_attach_point_transform`。实际与#36螺旋桨连接点距离0.002518m，未移动任何零件。左侧#42及两侧涡轴排气挂点也独立复核通过。**FB-042关闭，已解决(0.4.11)。**

## 未覆盖与边界

一次8视图异步取消尝试中，取消到达时任务已succeeded，最终成功结果可正常取得。没有触发渲染中取消，所以**不把“发送cancel成功”写成取消恢复通过**。强制渲染异常及人为制造不一致场景的截图也未做故障注入；它们仍需专项测试。这些限制不等于本轮观察到故障。

自动取景使用保守包围范围，整机图适合观察布局；精细挂载建议focusPartIds，必要时固定target/distance/FOV或orthographicSize，提高目标在图中的占比。它不会隐藏遮挡物，也不会修改玩家选择；选中轮廓可能保留。独立Spoiler和试飞仍不在本轮完成范围。

测试脚本首次对connections.points误传partId（正确为part），后来对异步受理误用了终态outputSchema（应为asyncOutputSchema）。均依据已存在的CLI契约修正测试，保留原失败记录；这些是测试调用错误，不登记产品缺陷。

## 证据

原始输入/返回、调用索引、下载图片与manifest：[direct-0.4.11](../tests/artifacts/staged-build/direct-0.4.11/)。实时断言62项通过；独立复核 [review.json](../tests/artifacts/staged-build/direct-0.4.11/review.json) **81/81通过**，覆盖25张请求图片、14个挂点和63份返回契约。二者是不同层次的检查，不将数量合并当作独立场景数。

示例：[原生整机斜视](../tests/artifacts/staged-build/direct-0.4.11/images/d63d7d774565480089a8bc109ecab6ac/aircraft-oblique.png)、[涡桨局部透视](../tests/artifacts/staged-build/direct-0.4.11/images/2485f27b946a4ac5851557e8b6db1c16/engine-angle.png)、[涡桨局部正交](../tests/artifacts/staged-build/direct-0.4.11/images/2485f27b946a4ac5851557e8b6db1c16/engine-right.png)。这些路径引用工作区验收产物，发行包不包含当前飞机或验收图片。
