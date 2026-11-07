# 0.5.0 局部精修调用指南

[English](../Precision-Workflow.md) · 简体中文

本指南用于机头、玻璃、吊舱、挂架、起落架等局部精修。以实际部件回读、测量和固定视角复拍共同判断结果。

## 一轮有效微调

1. 确定目标件、参照件与不能改变的区域。把目标写成可比较的尺寸、截面或间隙；参考图里看不出的尺寸应标为未知。
2. 查有效属性和依赖，建立检查点，记录初始测量与固定视图。
3. 只改一组相关参数，等待命令完成，再读取实际结果。
4. 打开原生图片，比较同一取景下的外观；测量真实网格，检查完整状态差异。
5. 保留确有改善的结果；较差的候选回滚。达到约定容差、连续无改善或原生零件无法表达目标时，给出结果与限制。

机头通常先调截面，再处理接缝，最后调整窗体。吊舱先定引擎与罩的组合及尺度，再定位挂架。起落架先确认腿、轮、舱门和活塞的依赖及可达姿态，再处理收放间隙。

## 查询与范围

以下命令使用已安装的全局入口。ID均需从当前飞机查询；`76`只用于展示调用格式。

```powershell
sp2build version --json
sp2build designer status --json
sp2build designer selection --json
sp2build craft snapshot --include-xml --output before.json
sp2build parts get --id 76 --json
sp2build properties get --id 76 --limit 1000 --json
sp2build commands schema --operation properties.set
```

`properties get`的字段在`data.parts[].fields[]`：以大小写敏感的`propertyId`标识，不用UI标签替代。检查`valueAvailable/value`、`editability`、`writeOperation`、`condition/currentCondition`、单位、边界与资源选项。未知值不能当作0；XML省略的值也不能当作没有该属性。

要查询尚未装到飞机上的零件，先检索原生目录，再用`properties describe --template-id TEMPLATE_ID`。复合模板会返回多个子件，每个子件的`total/offset`独立分页。字段目录不代表全部字段都能安全写入。

| 目标 | 优先接口 | 注意事项 |
| --- | --- | --- |
| 机身截面、裁切、倒角、翼型和控制面 | `shape get/schema`、`shape.update`、`wing.control.add` | 曲面控制截面的宽高不等于插值后表面实际宽高，应用截面测量复核 |
| 窗体、文字、贴花、整流罩和机构 | `properties get`、`properties.set` | 按有效条件和资源枚举写入；不猜XML或Animator关键帧结构 |
| 材料及指定槽位 | `appearance get`、`appearance.set` | `clone`局部克隆；`shared`会改到当前飞机中所有共用者 |
| 一组部件的定位 | `groups resolve`、`transform.apply` | 腿及其原生随动轮、机翼及其控制面等依赖应一并选中 |
| 挂点对齐 | `transform.align` | 只负责空间对齐，不建立连接；普通`connection.connect`不自动吸附 |
| 贴花投射体位姿 | `decal pose get`、`decal.pose.set` | 原点在前投射平面，局部+Z覆盖0到depth，表面需处于有效体积内 |

## 检查点、小改与恢复

用当前`craftSessionId/revision`创建检查点，保留其ID。所有写入均使用新的`requestId`；每次修改或恢复后重新读取身份，不重复使用旧revision。

```powershell
sp2build craft checkpoint create --input checkpoint.json --json
sp2build batch preview --input patch.json --request-id PREVIEW_REQUEST_ID --json
sp2build batch apply --input patch.json --json
sp2build craft diff --checkpoint-id CHECKPOINT_ID --json
sp2build craft rollback --input rollback.json --json
```

`patch.json`结构示例：

```json
{
  "craftSessionId": "CURRENT_SESSION",
  "expectedRevision": 12,
  "requestId": "UNIQUE_REQUEST_ID",
  "operations": [{
    "kind": "properties.set",
    "partId": 76,
    "symmetric": false,
    "patch": {"ProceduralWindow[0].height": 0.64}
  }]
}
```

检查点输入包含上述三项身份/请求字段，可加`name`。回滚输入包含当前身份、新请求ID及`checkpointId`。预检查不会实际生成模型，也不会锁住revision；实际写入后应读`effectiveChanges`和`validation`。错误时检查`rollbackResult.restored`及`stateUncertain`，不能因返回失败就假设没有改动。

起落架样式编辑保留已有动画，但新几何未必适合旧姿态。样式变更后重新查询条件字段；新挂点所需配置放在后续operation。同步遵守部件对称组和modifier开关，`symmetric:true`不会强行覆盖已禁用的同步开关。

## 固定图片与测量

```powershell
sp2build designer capture --input views.json --output-dir inspection --json
sp2build geometry section --input section.json --json
sp2build geometry seam --input seam.json --json
sp2build geometry measure --input clearance.json --json
```

先查各命令schema组成请求。原生截图返回`repeatableViews/repeatableResolution`，后续复拍沿用它们。每次自动适配取景可能改变缩放比例，不能直接比较像素长度。Agent必须真正打开返回的图片，才能判断玻璃、文字、材质、遮挡及模型是否刷新。

`geometry measure`返回两组表面的最近距离和见证点；0可能表示接触或相交，不提供穿透深度。接缝应使用`geometry seam`限定平面和局部区域，读采样的最大/RMS误差；最近一点距离小，不能证明整个接缝闭合。截面是三角网格与平面的交线段，不是理想CAD曲线。

始终读`complete/exclusions/staleAtDelivery`。不完整或已过时的采样不能作为合格证据；离散收放端点无碰撞也不能证明整个动画轨迹安全。原生参数无法表达的形状，应拆分建模或明确告知限制。

## 不占用桌面的操作

经用户授权后，可通过`designer crafts/control`进入设计器、加载原生保存的飞机、选中零件、返回菜单或退出，见[原生设计器导航](CLI-Usage.md#原生设计器导航)。加载和离开会使当前未保存编辑及检查点失效，需当前身份与明确的`discardCurrent:true`。只有加载到设计器后才能编辑。

这些接口不模拟鼠标点击、不激活窗口。启动尚未运行的游戏仍需本地进程启动器；DLL不能在不存在的进程中自行执行。正式插件不屏蔽玩家输入，玩家同时编辑时应遵守revision冲突结果重新规划。
