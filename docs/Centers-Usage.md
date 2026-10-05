# 0.4 三心读取、布局图与前后比较

日期：2026-10-02。最低 **CLI / 已加载 DLL 0.4.0**。本版已完成源码实现、离线验证和部署；按用户要求，没有启动游戏验收。以下数值例子均为合成测试数据，不是玩家飞机实测。

## 1 选择调用方式

| 玩家问题 | 建议调用 | 主要读取 |
| --- | --- | --- |
| 三心在哪里、谁在谁前后？ | `sp2build craft centers` | `data.centers`、`data.relations`、`data.frame` |
| 哪些零件影响重心？ | `sp2build craft centers --detail contributors --metric mass --limit 20` | `data.contributors.items` 的质量、相对重心偏移及质量矩 |
| 当前选中件影响多大？ | `sp2build craft centers --detail contributors --focus selected` | 焦点件贡献；全机三心和全机份额分母保持不变 |
| 看三心与飞机外形的位置关系 | `sp2build craft centers --images --timeout 120 --output-dir ./centers-view` | `data.visual.recommendedImages` 的本地 PNG |
| 改翼、移动发动机或调整挂载后如何变化？ | 先 `--output before-centers.json`，之后 `--baseline before-centers.json` | `data.comparison.relativeChanges`，同时检查是否可比较 |
| 查字段和参数 | `sp2build commands schema --command craft.centers` | 输入 schema、具名输出 `$defs` |

只读取当前打开的设计器飞机，不加载保存的飞机文件。`baseline` 是已有工具报告，不是飞机 XML、检查点或导入入口。读取不调用飞行模拟、编辑、撤销、原生 VTOL Refresh 或修改三心开关。

0.4.4 增加游戏 0.7.8.103 的原生问题提示：有已连接的 flipped 程序化翼时，warnings 中返回 `native_flipped_wing_com_y_zeroed` 和相关零件 ID。该版游戏的 WingBuilder 将镜像翼局部质量中心 Y 清零，因此几何镜像不保证世界质心在竖直方向也镜像。工具保留游戏实际使用的重心，不改写质量或飞行物理；不要把新警告理解为此游戏缺陷已被修复。

## 2 参数

全部参数可放在 UTF-8 JSON 中，通过 `--input request.json` 传入；复杂 JSON 建议使用文件。

| 参数 | 默认与取值 | 作用 |
| --- | --- | --- |
| `detail` | `summary` / `contributors` | 始终返回全机摘要；后者增加贡献页 |
| `metric` | `all` / `mass` / `lift` / `thrust` | 只过滤明细 |
| `focus` | `all` / `selected` | 焦点过滤明细并在图中高亮；无选择返回 `focus.status=no_selection` 与空明细 |
| `focusSelector` | `parts` 或 `assembly` 对象 | 替代 focus；精确集合或原生导弹/机翼组件范围，不递归扩展整张连接图 |
| `limit` / `offset` | `20` / `0`，limit 1–200 | 分页；不改变中心、总质量与全机份额 |
| `frame` | `{"kind":"world"}` 或 `{"kind":"part","partId":ID}` | 只变换输出坐标；参考件缩放被忽略，原生升力投影仍是世界 +Y |
| `images` | false，CLI 使用 `--images` | 同一次主线程采集中心和真实网格，然后生成侧/俯/前视图 |
| `resolution` | width/height 均 640，范围 384–1024 | 标注图分辨率；所有视图受现有像素/时间预算限制 |
| `baseline` | 报告文件路径，最大 8 MiB | CLI 校验并加载数据后交给同一个任务比较；支持异步 |
| `craftSessionId` / `expectedRevision` | 可选 | 指定时校验；未指定时也冻结执行开始的身份，采样期间发生修改会拒绝 |

`focus` 与 `focusSelector` 互斥。例如，查询指定挂载组，在参考件坐标系中展示全机三心：

```json
{
  "detail": "contributors",
  "metric": "mass",
  "focusSelector": {"kind": "parts", "partIds": [214, 215]},
  "frame": {"kind": "part", "partId": 1},
  "images": true
}
```

ID 为占位，调用前应查询当前飞机。原生组件焦点改用 `{"kind":"assembly","rootPartId":ID}`；不支持的组件根返回 `assembly_not_supported`。

## 3 返回内容与解释

成功信封为 `{"success":true,"schemaVersion":"1","data":{...}}`。不再需要从快照自行计算三心。

- `identity`、`analysisId`、`capturedFrame`、`geometryStamp`：本次身份与采样信息。带图时报告、manifest 与真实网格使用同一 geometryStamp；渲染期间设计改变会置 `staleAtDelivery=true`。
- `basis`：`native_designer`、当前编辑器载荷、原生世界 +Y 投影、游戏版本。并非任何指定迎角/速度下的飞行工况。
- `frame`：矩阵、参考身份及坐标约定。+X/+Y/+Z 对应 right/up/forward；这只是设计/参考件的轴约定，不能从中断言模型机头朝 +Z。
- `scope`：全部装配件与主连通件数量、实际主连通 ID。质量和翼源跟随原生连接范围；旧 VTOL 另有原生层级范围例外。
- `centers.com/col/cot`：`status=valid/partial/unavailable`、世界/所选坐标的米制位置、方法、权重与覆盖情况。不可用位置为 null。partial 为覆盖部分源的结果，不能当完整原生标记。
- `relations.colFromCom/cotFromCom/cotFromCol`：名字前者减后者，含三轴向量、三维距离和轴方向词。显示对齐阈值 0.001 m，不是安全容差或求解精度。
- `assessment`：静稳定性、配平、推力力矩均为 `not_assessed` 并附原因。
- `warnings`：机器可读 code 与具体解释，包含范围例外、混合权重和覆盖不足。
- `visual`、`comparison`：未请求时为 null。

**合成数据字段节选**：

```json
{
  "centers": {
    "com": {"status":"valid", "positionFrameMeters":[13,0,0], "massKg":4},
    "col": {"status":"valid", "positionFrameMeters":[13,0.25,-0.4]},
    "cot": {"status":"valid", "positionFrameMeters":[13,-0.12,-2]}
  },
  "relations": {
    "colFromCom": {
      "deltaFrameMeters":[0,0.25,-0.4],
      "distanceMeters":0.4716990566,
      "axisRelation":["aligned_within_display_tolerance","above","aft"]
    }
  }
}
```

只有确认 +Z 朝机头后，才把 aft 解释为机体“后方”。CoL 是原生投影面积 × LiftScale 的加权位置，不是整机中性点。CoT 的 nativeWeight 混有程序化喷气静推力、螺旋桨直径平方 × 桨叶数、旧引擎 Power；总和不能标为 N，位置间距不是推力作用线力臂。

重心使用当前 `LoadedMass / 0.01` 换算 kg 和零件真实局部 CoM 变换后的坐标。`EmptyMass` 不代表空油质量。现代喷气计算运行在独立 math state 的数据副本，避免改动实时性能缓存。旧机翼和未知 Mod 的未验证读取分支会排除并标记覆盖不足。

## 4 明细与前后比较

`contributors` 返回 `total/returned/offset/limit/truncated/nextOffset/items`。每行有 `part:{id,type,typeName,name}`、来源 `sourceId`、是否纳入、排除原因、世界/参考坐标和权重。

质量行额外有 `massKg/massFraction/offsetFromComMeters/massMomentAboutComKgM`；质量矩是 kg·m，不是 N·m。升力行有 `projectedAreaSquareMeters/liftScale`；推进源有 `propulsionType/weightMeaning/directionStatus`。全机权重份额的分母在焦点过滤、分页前计算；partial 时只针对已覆盖来源。

首版固定排序：mass/lift/thrust 顺序；质量按质量矩范数降序，其他按原生权重降序，sourceId 打破并列。暂不提供切换排序参数。

```powershell
sp2build craft centers --output before-centers.json
# 按玩家要求，通过现有受 session/revision 保护的编辑命令修改飞机
sp2build craft centers --baseline before-centers.json --output after-centers.json
```

`--output` 写出的文件是完整报告，stdout 只是保存收据；baseline 必须指向完整报告文件。比较不加载/恢复飞机，不把报告里的文本执行成指令。

`comparison.status=comparable` 时，`centerChanges` 给三心坐标前值、后值、差值；`relativeChanges` 给三对关系的向量及三维距离变化。整机共同平移只影响绝对坐标，不改变相对关系。期间发生其他编辑时，这些差值不自动归因于某个单件。

跨会话、算法/游戏版本或口径变化、朝向/参考系变化、参考件重建/ID 复用，返回 `not_comparable` 和 reasonCodes；当前报告仍正常返回。参考件靠进程内对象身份校验，不把数字 ID 当永久身份。图片只绘制当前样本，不叠加旧报告的模型或标记。

## 5 图片和已有 visual capture

`data.visual.recommendedImages` 是 CLI 下载后的绝对 PNG 路径；manifestPath 包含同样本数据与投影矩阵。Agent 应实际打开图片再声称已观察外形。

灰色飞机、绿色焦点件；红圆为 CoM、蓝三角为 CoL、黄菱形为 CoT，标签引线区分重合点，标记不移动。每图含坐标轴、米制尺、三对带符号 XYZ 距离。标记置顶只表达空间位置，不是表面命中，raw/ids 图和 `visual pick` 不受标记影响。

三心间距小于推荐阈值时添加联合局部三视图，至少保留 0.5 m 范围；远离飞机的中心扩大总览范围并按预算补飞机外形图。各张图比例可能不同，使用 pixelsPerMetre，不比较原始像素长度。manifest 的 centersDetailStatus 说明生成、无需生成、无可用中心或预算不足。

已有 `visual capture` 可加入：

```json
{
  "craftSessionId":"SESSION",
  "expectedRevision":1,
  "groups":[{"name":"targets","selector":{"kind":"parts","partIds":[214,215]}}],
  "overlays":{"centers":true},
  "views":["right","top","front"]
}
```

返回 `data.centersReport`；即便只画两个零件，三心仍按全机范围计算。group/perGroup 图片原有语义保留；三心覆盖在联合图和专门的中心细节图中。取景范围包括中心，和关闭叠加时可能不同。

无可读网格、超出渲染预算或取消时，图片任务遵循已有视觉错误机制；可改用不带 images 的数值读取。渲染不保证还原原生涂装、透明材质或 shader 效果。

## 6 版本与验收边界

全局 `sp2build version` 是 CLI 版本；下次启动后，`designer status` 的 pluginVersion 才能证明已加载的 DLL 版本。旧 DLL 调用三心会在提交前返回 `unsupported_bridge_feature`。CLI 的安装与磁盘 DLL 替换不等于热更新。

本版离线验证涵盖算法、空/部分数据、分页、对比守卫、投影、标注不污染拾取、下载和 schema。尚待游戏验收：原生三心标记一致性、程序化翼/推进源/VTOL 现场行为、修改后重读、只读前后的 XML/相机/选择/历史一致性，以及 DSH 真实任务体验。原有版本实机通过项不作为这些新功能的验收证据。
