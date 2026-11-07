# 0.3 外观与空间视觉检查

[English](../Visual-Usage.md) · 简体中文

日期：2026-10-02。最低 DLL / CLI 版本：**0.3.0**。统一入口为全局 `sp2build`，只读取当前设计器中已打开的飞机。

可以通过 `overlays:{centers:true}` 叠加全机三心；完整调用和三心口径见 [三心使用手册](Centers-Usage.md)。也可直接使用 `sp2build craft centers --images` 获取同快照报告与三视图。

本版从游戏实际渲染网格复制顶点、三角面和变换，生成 PNG 三视图、斜视图及空间 JSON。多个目标放在同一个坐标系和比例下绘制，保留实际间距和朝向；不会分别居中再拼成假的装配关系。绘制使用分组配色和简化光照，适合辨认形状、位置和对应零件，**不还原游戏涂装、贴花、透明材质或 shader 效果**。

0.3.1 默认使用 `details:auto`，当某组在所有联合视图中都太小或不可见时，为它生成一张独立细节图，并与 overview 一起推荐。`perGroup` 仍生成各组全部视角，`none` 关闭细节生成。`imageRecommendations` 说明推荐原因；`detailStatus` 报告 `generated/not_needed/disabled/budget_exceeded/no_geometry`。根据最佳联合图块的可见长度（96px）、相对长度（15%）及可见像素数（1024）判断，阈值不代表保证所有视觉模型都可辨识。

即使两次捕获指定同一 frame，自动取景仍会因几何包围盒变化而改变比例。跨次比较必须分别读取各视图 `pixelsPerMetre` 或 `frameToPixelRows` 换算到米。返回和 manifest 中的 `scalePolicy=fit_scope_each_capture`、`comparisonGuidance` 明示这一点；本版未新增固定比例拍摄模式。判断挂载贴合时，把附近挂架/机翼也纳入联合范围，单独放大的零件图不能证明安装关系。

## 1 最快调用

先让玩家在设计器中选中零件，再执行：

```powershell
sp2build designer status
sp2build designer selection
sp2build visual capture --craft-session-id SESSION --output-dir .\inspection --timeout 90
```

将 `SESSION` 替换为 status 返回的 `identity.craftSessionId`。默认取得当前选中的单个零件，生成 front、right、top、isometric 四张图及总览。未选中时返回 `selection_empty`。请求不改变玩家相机、选中项、材质、显隐或撤销历史。

返回 JSON 中的 `recommendedImages` 是可打开的本地 PNG 绝对路径。Agent **必须通过自身平台的读图/附件工具把图片交给视觉模型**；执行命令或读 manifest 不等于看过图片。纯文本模型只能使用附带空间数据。

复杂请求写入 UTF-8 JSON 文件，再执行：

```powershell
sp2build visual resolve --input scope.json
sp2build visual capture --input capture.json --output-dir .\inspection --timeout 90
sp2build commands schema --command visual.capture
```

`visual resolve` 接受范围相关字段；相机、分辨率等只放在 capture 请求。所有示例 ID、SESSION 和 revision 均需替换为当前查询结果。

## 2 多目标联合三视图

`capture.json`：

```json
{
  "craftSessionId": "SESSION",
  "expectedRevision": 12,
  "groups": [
    {"name":"left-wing","selector":{"kind":"parts","partIds":[18]}},
    {"name":"right-wing","selector":{"kind":"parts","partIds":[19]}}
  ],
  "views": ["front","right","top","isometric"],
  "resolution": {"width":640,"height":640},
  "frame": {"kind":"world"},
  "details": "perGroup"
}
```

联合视图使用共同中心和共同像素/米比例，颜色对应 groups 顺序，图上 G1/G2 表示分组，P18/P19 表示原生零件 ID。`details:perGroup` 另外输出各组放大图；这些细节图有各自中心和比例，不能用不同细节图之间的像素距离推算现实间距。每张图最多放置 32 个零件标签；未画标签不代表零件不存在，应结合原图、ID 图和 manifest 查看。

空间关系见 `manifest.groups[].bounds` 和 `manifest.relations[].deltaMetres`。后者是所捕获网格包围盒中心之间的向量，单位米，**不是挂点间距、表面净空或承力归属**。

## 3 选择零件、组件或分支

| selector.kind | 其他字段 | 范围定义 |
| --- | --- | --- |
| `parts` | `partIds:[18,19]` | 精确 ID 集合，不自动带对称件或连接件 |
| `selected` | 无 | 执行时玩家当前选中的单件 |
| `craft` | 无 | 当前整机，含断开的零件 |
| `assembly` | `rootPartId:229` | 原生程序化导弹及其归属部件，或机翼及其归属控制面 |
| `branch` | `rootPartId`、`stopConnectionKeys:["edge-..."]` | 将明确指定的连接视为边界，解析根所在连通范围，不真正断开连接 |
| `neighborhood` | `rootPartId`、`hops:0..10` | 限定跳数的连接图邻域，仅代表拓扑 |

多组必须互不重叠；交集返回 `scope_overlap`，避免重复画相同表面。未知自定义子组件没有可依赖的原生所有权，使用明确 ID 或带边界的 branch。视觉 assembly 是观察范围，不承诺该集合可以安全级联删除。

例如同时观察两枚完整原生导弹：

```json
{
  "craftSessionId":"SESSION",
  "groups":[
    {"name":"left-missile","selector":{"kind":"assembly","rootPartId":228}},
    {"name":"right-missile","selector":{"kind":"assembly","rootPartId":229}}
  ],
  "details":"perGroup"
}
```

自定义子树先用 `visual resolve` 查询一个已知 ID，返回的 `connections` 是当前全机连接清单，包含两端 ID、挂点 ID 和稳定连接 key。选择确切边界后提交 branch。若边界仍被其他图路径绕过，或切边与目标范围无关，返回 `scope_ambiguous`，不静默扩展为整机。连接图不是物理悬挂关系，不能用 BFS 判断零件实际装在哪片机翼下。

## 4 视角和坐标

| 字段 | 默认值 | 允许值 / 含义 |
| --- | --- | --- |
| `craftSessionId` | 必填 | 当前打开会话，拒绝另一架飞机的会话 |
| `expectedRevision` | 省略 | 可选；提供时必须等于当前 revision |
| `groups` | 当前选中零件 | 1..8 组，名称唯一且最多 80 字符 |
| `maxParts` | 2048 | 总范围上限 1..2048，超出报错，不静默截断 |
| `views` | front/right/top/isometric | 1..8 个不重复的视图，可另用 back/left/bottom 或自定义视角 |
| `resolution` | 640×640 | 每个维度 128..1024；指单视图分辨率 |
| `frame` | `{"kind":"world"}` | Unity 世界坐标，单位米；也可用 `{"kind":"part","partId":19}` |
| `details` | `none` | `perGroup` 额外输出各组视图 |
| `includeHidden` | false | true 尝试读取可取得的隐藏零件网格，不改变设计器显隐 |

零件坐标系使用该零件的位置和旋转，不带其缩放。front 沿所选坐标系 -Z 看、right 沿 -X 看、top 沿 -Y 看且 +Z 朝图上方。正交斜视图同样保留比例。自定义相机方向是**观察方向**，与 up 不得平行：

```json
{"name":"oblique","direction":[-1,-1,-2],"up":[0,1,0]}
```

name 使用小写字母开头、后续小写字母/数字/连字符、总长不超过 32；不能以 g 开头（预留给分组文件），也不能使用 overview 或 Windows 设备名，如 con、nul、com1。`frameToWorldRows`、`partToFrameRows`、`partToWorldRows` 和 `frameToPixelRows` 都是行数组，乘列向量。图像坐标原点左上，零基；像素采样点为整数索引加 0.5。

## 5 返回文件与内容样例

成功输出的结构示例，省略重复 files 项：

```json
{
  "success":true,
  "schemaVersion":"1",
  "operationId":"CAPTURE_ID",
  "data":{
    "captureId":"CAPTURE_ID",
    "identity":{"craftSessionId":"SESSION","revision":12},
    "geometryStamp":"SHA256_OF_CAPTURED_GEOMETRY",
    "complete":true,
    "staleAtDelivery":false,
    "artifactBase":"v1/visual/CAPTURE_ID/",
    "files":[{"name":"overview.png","bytes":12345,"sha256":"..."}],
    "outputDirectory":"C:\\Work\\inspection\\CAPTURE_ID",
    "manifestPath":"C:\\Work\\inspection\\CAPTURE_ID\\manifest.json",
    "recommendedImages":["C:\\Work\\inspection\\CAPTURE_ID\\overview.png"],
    "exclusions":[],
    "warnings":["Analysis uses actual mesh triangles..."]
  }
}
```

| 文件 | 用法 |
| --- | --- |
| `overview.png` | 联合视图拼图，优先送给视觉模型 |
| `front.png` 等 | 含标签、坐标轴和标尺的单视图 |
| `front.raw.png` 等 | 相同几何、分组配色、无标注遮挡的原图 |
| `front.ids.png` 等 | 精确的表面 ID 索引图，用于程序反查，不是原生涂装 |
| `g1-front.png`、对应 raw/ids 等 | 请求 perGroup 时的组内放大图 |
| `manifest.json` | 身份、范围、坐标变换、包围盒、分组关系、投影、可见像素、遗漏与文件哈希 |

默认四视图包共 14 个文件。2 组、四视图、perGroup 共 38 个文件。CLI 下载时校验长度和 SHA-256，临时文件写完后再替换；文件放在 output-dir 下独立 captureId 子目录。省略 output-dir 时使用 `~/.sp2build/captures`。

manifest 中 `parts` 保留所有所选 ID，`views[].parts` 描述实际取得网格的零件。`visiblePixels:0` / `occluded_or_subpixel` 意味着遮挡或小于像素，不是飞机里不存在。`partIdPalette` 将 RGB 编码的索引映射到原生 partId，索引 0 为背景。

```powershell
sp2build visual pick --capture-id CAPTURE_ID --view top --x 320 --y 240
```

结构示例：

```json
{"success":true,"data":{"captureId":"CAPTURE_ID","view":"top","x":320,"y":240,"partId":19,"capturedIdentity":{"craftSessionId":"SESSION","revision":12}}}
```

pick 使用标签下方的模型 ID，背景为 null。view 必须是 manifest 的单视图名称，如 `top`、`g1-top`，不能用 `overview`。捕获的 ID 是历史快照，编辑前应重新读取当前身份。

## 6 新鲜度、异步与资源限制

采集先等待原生编辑器几何稳定，在主线程一次复制网格/变换，然后在后台 CPU 绘制。`geometryStamp` 对实际复制的顶点和索引计算哈希；修改形状或变换后重新调用 capture，旧包不会跟随变化。`staleAtDelivery:true` 表示交付时检测到飞机已变化，不能当作当前证据。这个判定基于飞机身份/XML，不保证发现每种临时动画或 shader 状态变化。

```powershell
sp2build visual capture --input capture.json --async
sp2build operation wait --id OPERATION_ID --output-dir .\inspection --timeout 90
sp2build operation result --id OPERATION_ID --output-dir .\inspection
sp2build operation cancel --id OPERATION_ID
```

异步提交只返回 operationId。wait/result 会下载完成后的视觉包；status 只看任务状态。遇到 wait_timeout，保留原 operationId 继续等待，不要立刻新建重复 capture。取消后查询终态；已经完成的任务不保证可以撤销交付。

游戏侧缓存最多保留 15 分钟、3 个包、192 MiB，任一容量约束可提前淘汰，退出游戏后失效。下载到本地的文件持续保留；缓存过期时在线 pick / 再下载返回 `artifact_expired`，应重新 capture。已下载 ID 图仍可按本地 palette 解码。

上限：2048 零件、8 组、8 视图、120 万顶点、50 万三角面、合计 1600 万像素（含总览/放大图）；另有 3.5 亿候选像素工作量及 45 秒绘制预算。超过预算须缩小范围、分辨率、视图数或关闭 details。特别密集的大飞机可能无法一次取得全部视图。

## 7 覆盖范围和限制

读取原生 PartMaterial 渲染器登记表及归属 SkinnedMeshRenderer，排除编辑器手柄、裁剪预览、粒子等非表面内容。实际三角网格采用不透明双面绘制，支持变换及负缩放。**这是一份网格分析图，不是游戏原生画面截图**：透明/镂空 shader、贴花、材质纹理和 shader 顶点位移不会完整复现；仅靠本图不能证明碰撞净空或挂载支撑。

隐藏、不可读、无可捕获网格或包含无效三角面的目标都记录在 `exclusions`。`success:true` 表示取图任务完成；`complete:false` 表示有遗漏，Agent 必须检查并说明遗漏。只有引用 NaN/Infinity 顶点的三角面被过滤，其他有效面继续生成；如果整个范围没有可用网格则报错。

查看颜色、玻璃、贴花或透明表面时，改用[原生截图](Designer-Screenshots.md)。分析图中没有可绘表面或存在无效三角面时，请查看清单中的覆盖和排除项。
