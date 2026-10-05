# 设计器原生视角截图（0.4.11）

`sp2build designer capture` 使用当前设计器的原生场景相机生成 PNG，保留原生模型、涂装、材质、光照和背景。支持当前玩家视角、预设方向和自定义方向，以及透视/正交投影。截图过程中临时设置相机，并在返回前恢复；不修改飞机、不增加撤销记录。

本版已加载 **0.4.11并完成常用流程实机验收**：当前视角、七个预设方向、自定义方位/仰角/滚转、透视/正交、局部取景、异步下载、8类错误输入及相机/飞机/选择/历史保持均通过。25张请求图片已实际打开；运行中取消与强制渲染异常尚未覆盖，详见 [验收记录](Verification-0.4.11.md)。

## 如何选择接口

| 需要观察什么 | 接口 |
| --- | --- |
| 玩家当前相机看到的飞机与场景、原生涂装、场景重影 | `designer capture` |
| 指定部件/子树的隔离图、分析配色、像素对应零件 ID | `visual capture` / `visual pick` |
| 同一快照的三心标注和数值 | `craft centers --images` |
| 菜单、鼠标指针、独立 gizmo 相机/UI 叠层 | Agent 平台的窗口截图能力 |

原生截图不主动过滤旧飞机实例，所以 `sceneIntegrity:inconsistent` 时仍可截图取证。`focusPartIds` 只用于取景，不隐藏其他部件，亦不把全场景伪装为健康。默认只渲染设计器主场景相机，**不合成屏幕 UI、鼠标和独立 gizmo 相机**；这不是桌面屏幕截取。渲染能力受本机游戏原生相机/图形管线影响，首轮上线需检查 PNG 是否正常。

## 基本调用

先查当前会话与已加载版本，再将实际 session/revision 填入 UTF-8 JSON 文件：

```powershell
sp2build designer status --json
sp2build commands schema --command designer.capture --json
sp2build designer capture --input camera.json --output-dir inspection --json
```

当前玩家视角：

```json
{"craftSessionId":"SESSION","expectedRevision":12,"views":["current"]}
```

三张正交图，加一张自定义透视图：

```json
{
  "craftSessionId":"SESSION",
  "expectedRevision":12,
  "views":[
    {"view":"front","projection":"orthographic"},
    {"view":"right","projection":"orthographic"},
    {"view":"top","projection":"orthographic"},
    {"name":"front-quarter","view":"custom","projection":"perspective",
     "azimuthDegrees":45,"elevationDegrees":25,"fieldOfViewDegrees":45}
  ],
  "resolution":{"width":1280,"height":800}
}
```

局部取景可加 `"focusPartIds":[31,32,33,34,35,36,37]`，默认取当前飞机全部零件的真实 renderer bounds；其他场景物体仍然会显示和遮挡目标。部件 ID 仅为示例，必须根据当前载具查询。`view:current` 不自动重新取景，focus 列表不会改变玩家当前相机姿态。

## 方向、单位和投影

| 参数 | 含义 |
| --- | --- |
| `view` | `current/front/back/right/left/top/bottom/isometric/custom` |
| `projection` | `current/perspective/orthographic`，默认继承玩家当前投影 |
| `target` | 命名/自定义视图的观察目标，Unity 世界坐标 `[x,y,z]`，米；默认所选取景部件的包围盒中心 |
| `azimuthDegrees` | custom 必填；0° 从世界 +Z 看向目标，+90° 从 +X 看向目标，范围 −360..360 |
| `elevationDegrees` | custom 必填；正值从目标上方观察，范围 −89.9..89.9；严格俯视用 top |
| `rollDegrees` | 绕相机观察方向旋转，−180..180° |
| `distance` | 相机到 target 的距离，0.05..10000 m；省略则按取景包围盒自动取景 |
| `fieldOfViewDegrees` | 透视相机垂直视场角，5..140°；默认沿用玩家相机 |
| `orthographicSize` | 正交视图的**半高**，0.01..10000 m；仅正交投影可用，省略则自动取景 |

命名视图以 **世界轴** 定义，不自动推断飞机朝向：front 相机在 +Z，right 在 +X，top 在 +Y，top 图的上方为 +Z。`view:current` 不接受 target/distance/角度修改；需要修改姿态时选预设或 custom。当前视角切换到正交且未指定半高时，按当前目标距离及 FOV 保持目标平面上的近似视觉尺度。

跨次比较时，显式固定 target、角度、分辨率，以及 distance/FOV 或 orthographicSize。自动取景会改变图像缩放，不能直接比较像素大小；原生保存居中也可能改变所有世界坐标。

## 返回内容

以下是裁剪后的**结构示例，不是实机截图成功记录**：

```json
{
  "success":true,
  "data":{
    "identity":{"craftSessionId":"SESSION","revision":12},
    "captureId":"CAPTURE_ID",
    "backend":"native_designer_camera",
    "nativeMaterials":true,
    "includesUi":false,
    "includesGizmos":false,
    "cameraRestored":true,
    "sceneIntegrity":{"status":"healthy","aircraftInstanceCount":1},
    "views":[{
      "name":"front","view":"front","file":"front.png","width":1280,"height":800,
      "camera":{"positionWorld":[0,3,20],"targetWorld":[0,3,0],
        "projection":"orthographic","orthographicSize":5,"fieldOfViewDegrees":60},
      "autoDistance":true,"autoOrthographicSize":true
    }],
    "outputDirectory":"C:/Users/PLAYER/.sp2build/captures/CAPTURE_ID",
    "manifestPath":"C:/Users/PLAYER/.sp2build/captures/CAPTURE_ID/manifest.json",
    "recommendedImages":["C:/Users/PLAYER/.sp2build/captures/CAPTURE_ID/front.png"]
  }
}
```

完整 manifest 还包含每张图的相机位置/方向/四元数、投影矩阵、裁剪面、分辨率，截图前后相机参数及文件哈希。Agent 必须使用平台读图能力打开 `recommendedImages`，路径本身不会让文本模型看到图片。

每个请求最多 8 个名称不同的视图。未指定分辨率时保持当前视窗宽高比，最长边不超过1280；显式指定时 width/height 必须同时出现，各128..2048。总像素上限1600万，包含 overview 副本。`overview.png` 复制第一张视图，不是拼接总览；所有请求视图都列入推荐图片。

图片复用现有受令牌保护的本机 artifact 下载机制：进程内共享保留15分钟、3次捕获或192 MiB，CLI 自动下载并校验 SHA256；本地下载持续保留。无 output-dir 时存到 `~/.sp2build/captures`。与旧接口相同，可使用 `--async` 后查询 operation result/wait，不应因等待超时盲目重发。

## 验收清单

已验收：当前视角与真实窗口对照、六轴及等角方向、自定义角度、两种投影、显式距离/半高、局部取景不隐藏背景、PNG下载完整性、截图前后相机/选择/飞机指纹/撤销历史保持、非法参数拒绝。三次current截图在切换其他视图和错误请求后逐字节一致。一次取消到达时任务已完成，故渲染中取消恢复、强制渲染失败恢复和异常场景诊断仍未做实机故障注入；完整证据见 [0.4.11验收](Verification-0.4.11.md)。
