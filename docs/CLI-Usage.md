# SP2 Build Assistant CLI 调用手册

**最新发布0.5.0**：已加入有效属性/材质、局部刚性组、接缝测量和固定原生视图，见[最终验收报告](Verification-0.5.0.md)。`designer crafts` 与 `designer control`通过游戏原生API加载、选择和切换场景，无需桌面输入。调用方法、守卫和丢弃当前编辑的影响见[原生导航说明](../skills/sp2-build-assistant/references/designer-navigation.md)。精修完整流程见[局部精修指南](Precision-Workflow.md)。

此前发布 **0.4.11**：新增 `sp2build designer capture --input camera.json --output-dir inspection --json`，支持真实设计器材质/背景、当前视角、任意方位及正交/透视，详见 [输入输出与角度定义](Designer-Screenshots.md)。不合成屏幕菜单和独立 gizmo 相机。挂点 `localPosition/worldPosition` 优先来自实时句柄，新增 `positionSource/definitionLocalPosition`。0.4.11 已实测通过截图常用流程和动态挂点返回，见 [验收记录](Verification-0.4.11.md)；旧版插件会被 CLI 明确拒绝新截图请求。

本文说明如何通过 `sp2build` 查询 SimplePlanes 2 当前编辑器中的飞机、检索完整零件库、编辑零件与变量，以及查询任务、撤销和回滚。面向玩家、能执行本地命令的 agent，以及接入此 CLI 的开发者。

文档日期：2026 年 10 月 2 日。当前发布 **CLI / skill / DLL 0.4.11**，目标游戏 **0.7.8.103 / XML 25 / BepInEx 5 / Mono**。复杂形状见 [0.2 扩展](Complex-Parts-and-Designer-0.2.md)，分析网格图见 [视觉手册](Visual-Usage.md)，三心见 [三心手册](Centers-Usage.md)。已加载0.4.10的实机复验通过场景生命周期和有效输入配置，当前42件双涡桨构型；独立 Spoiler 未完成、未试飞。截图与挂点新修订已在0.4.11实测通过，详见 [验证记录](../Verification.md) 和 [本轮报告](Agent-Feedback-0.4.11.md)。更新DLL需要重启游戏，日常编辑无需重开飞机；CLI版本不代表运行中DLL版本。

DLL 0.4.9：`parts get --id ID` 返回 `data.part.inputControllers`，`shape get` 返回 `data.shape.inputControllers`，`catalog schema --id TEMPLATE_ID` 返回 `data.templates[].parts[].inputControllers`，均包含原生有效 `input/activationGroup/invert/invertType/min/max/zeroOnDeactivate`。`index/path/name/description` 区分同一零件的多个控制器，`serializedAttributes` 区分原生 XML 是否显式写出某属性。省略的默认值仍可从这些类型明确的字段直接读取。编辑继续使用 `part.update` 和返回的 path；name/description/invertOnMirror 仅为说明，不是新增可写属性。通过 `commands schema --command parts.get` 查询完整输出契约。

0.4.4 的 `symmetry get` 返回基于当前主控制器位置的有效平面，并增加 `basis/originPartId/aircraftMirrorPlaneOffset/planeEquation/nativeCacheStale/nativeCachedFrame`。平面为 `dot(normal, position)+distance=0`，X 法线时平面位置为 `-distance`。查询不改缓存；批次写入在每个操作前刷新缓存。`symmetry.create` 创建副本与对称组，连接到宿主仍需显式操作。

`craft snapshot` 请求 `includeXml:true` 时增加 `xmlMetadataCaveat`：XML 的 Aircraft `size/boundsMin/boundsOffset` 是游戏保存时更新的元数据，可能落后于当前网格；查询即时尺寸请用 `parts geometry` 或同 revision 的 visual manifest。XML 内容仍忠实保留原值。

示例中的 `SESSION`、`REQUEST_ID`、`OPERATION_ID`、`CHECKPOINT_ID` 是占位符。实际零件 ID、模板 ID、版本号和坐标均需查询当前游戏。历史输出样例保留真实字段结构，缩短身份标识、裁剪长数组；它们不是当前飞机的完整状态，也不代表所有接口已验证成功。注明“结构示例”的输出按当前代码构造。

## 功能总览

0.5.0 当前 CLI 注册 **91 个命令、25 种批次编辑操作**，其中一个是正式DLL明确拒绝的开发验收入口`acceptance.native`；90个产品/本地/任务命令不等于90项独立建造能力。`sp2build commands list`可获取机器可读的完整映射。新增精修流程与调用示例见[局部精修指南](Precision-Workflow.md)，发行状态仍以验收总览为准。

2026-10-02 S00 修订：CLI / skill 已到 **0.4.1**，DLL 保持 **0.4.0**。形状写入 schema 与 family/style 枚举已补齐；designer.status.commands 的 bridge 范围已说明。此次仅 CLI/文档修复，无需重启，详见 [修订记录](Agent-Feedback-0.4.1.md)。

S01 修订 **0.4.2**：明确开启 autoResize 的机身/锥体在连接时可改变形状和位置，手动设尺寸后需显式关闭；写入返回的身份/校验仅代表完成时采样，不锁定后续保存/居中/玩家编辑。仍无需重启，见 [反馈核实](Agent-Feedback-0.4.2.md)。

S02 修订 **0.4.3**：未知参数裸写与带值均给出 Unknown option，合法参数缺值仍给出 requires a value；输入诊断在实例发现前进行。三心没有 `--include-disconnected` 参数，范围以其 schema/报告为准。见 [反馈核实](Agent-Feedback-0.4.3.md)。

| 用途 | 当前提供的能力 | 详细说明 |
| --- | --- | --- |
| 精细建模 | 有效字段、条件、局部材质、刚性组、挂点对齐、截面/接缝/间隙与完整差异 | [局部精修指南](Precision-Workflow.md) |
| 原生导航 | 进入设计器、原生载入、选择部件、菜单、退出 | [导航与身份守卫](../skills/sp2-build-assistant/references/designer-navigation.md) |
| 安装与 agent 接入 | 全局 CLI、实例选择、skill 安装与路径查询 | [快速开始](#1-快速开始)、[本地管理](#3-本地管理和接口发现) |
| 了解当前飞机 | 编辑器状态、完整快照、分页零件列表、单件详细属性树 | [飞机查询](#4-编辑器状态和飞机查询) |
| 三心与布局 | 重心/升力中心/推力中心、三对相对位移、贡献分页、基线比较、同快照标注图；不求解静稳定性 | [三心调用手册](Centers-Usage.md) |
| 拓扑与空间 | 连接图、连接点参数、两件相对位置和距离 | [拓扑与空间](#5-连接拓扑和空间关系) |
| 外观视觉检查 | 精确零件/组件/分支范围、真实网格三视图与斜视图、多组空间关系、放大图、像素 ID 反查 | [视觉检查调用、输入输出样例](Visual-Usage.md) |
| 玩家视角截图 | 原生设计器场景、材质/背景、当前或指定方向、正交/透视、局部取景、自动恢复视角 | [设计器截图](Designer-Screenshots.md) |
| 全零件库 | 大类、小类、分类列表、检索、原生介绍、默认属性及元数据、全库导出 | [零件库](#6-全部零件库检索和属性说明) |
| 零件编辑 | 新增、属性修改、删除、连接、断开；单操作或批次调用 | [零件编辑](#7-批次与零件编辑) |
| 变量与输出 | 全局 Setter 增删改排序、零件输出绑定、命名与激活条件修改 | [变量与输出](#8-全局变量和零件输出) |
| Funky Trees | 常量、函数签名、输入与变量查询、部分函数解释、表达式编译检查 | [表达式](#9-funky-trees-查询与表达式检查) |
| 恢复 | 原生历史查询、检查点、撤销、指定检查点回滚、失败自动恢复；0.4.10 已通过连续重建后的 CLI 与原生撤销复验 | [恢复流程](#10-历史-检查点-撤销与回滚) |
| 任务管理 | 异步提交、状态查询、等待结果、请求取消、去重与超时处理 | [任务管理](#11-异步任务-请求去重与超时) |

能力是否已完成实机验证见[验证状态](#13-验证状态和源码依据)；遇到失败时见[错误和限制](#12-常见错误和限制)。

## 1 快速开始

### 1.1 调用入口

离线帮助：`sp2build --help` 显示全局参数；`sp2build parts --help` 列出该组命令；`sp2build visual capture --help` 显示具体参数、默认值及输入方式。复杂嵌套结构和输出字段继续查 `commands schema`。快捷写入如 `connections connect` 要通过 `--input` 提供嵌套 operation，不能直接传 `--part-a`。`--output` 保存 JSON 结果，`--output-dir` 指定捕获图片下载目录，两者独立。

在玩家 Windows 机器的新终端中执行：

```powershell
sp2build version
sp2build instances list
sp2build designer status
sp2build capabilities
sp2build craft snapshot
```

DLL 随游戏通过 BepInEx 加载，CLI 会自动发现当前游戏实例。只有一个实例时无需指定 PID；多个实例时添加 `--instance PID`。

如果旧终端尚未继承 PATH，可用本机已安装的完整入口：

```powershell
& 'C:\Users\30023\.sp2build\bin\sp2build.cmd' version
```

正常工具调用统一使用 `sp2build`。若已运行的 harness 未继承安装后的 PATH，可在执行工具的 PowerShell 中刷新用户 PATH 后重试：

```powershell
$sp2UserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($sp2UserPath) { $env:Path = $sp2UserPath + ';' + $env:Path }
sp2build version --json
sp2build designer status
```

独立启动的 shell 不会保留上次 shell 的 PATH 修改，必要时重复刷新或从已更新 PATH 的终端重启 harness。不要转为执行仓库中的 Python 文件；仍找不到命令时应修复 CLI 安装。默认安装位置为用户主目录，避免打包版 agent 的 LocalAppData 写入被重定向到私有 LocalCache。旧 AppData 安装目录的 PATH 注册不代表其他平台实际能读取到文件。

先检查 `designer status` 中的 `designerReady`，再读飞机。0.5.0提供 `designer crafts/control`，可在已运行的游戏内，经授权调用原生API进入设计器、加载飞机、选择零件和退出；编辑操作始终针对已加载到设计器的飞机。0.4.11及以前需要玩家先打开目标飞机。`version` 返回CLI版本，`designer status` 或 `instances list` 返回实际加载的DLL版本。更新DLL后仍需重启；0.5.0重启后可通过原生导航入口继续操作，无需模拟桌面键鼠。

### 1.2 安装及 agent 导入

本机已经部署。其他机器需 Python 3.10+，以及已安装 BepInEx 5 的对应 Mono 游戏。项目安装命令：

```powershell
& 'D:\codeSpace\sp2\SP2BuildAssistant\install.ps1' -GameDir '你的游戏目录' -InstallSkill
```

安装器提供 `-GameDir`、`-InstallDir`、`-Python`、`-InstallSkill`。默认 CLI 位于 `%USERPROFILE%\.sp2build\app\cli`，启动器位于 `%USERPROFILE%\.sp2build\bin`，skill 安装到 `~/.agents/skills/sp2-build-assistant`。CLI 本身仅依赖 Python 标准库。

```powershell
sp2build skill path
& 'D:\codeSpace\sp2\SP2BuildAssistant\install-skill.ps1'
# 按平台设置实际的 skills 目录
& 'D:\codeSpace\sp2\SP2BuildAssistant\install-skill.ps1' -SkillRoot '你的 agent skills 目录'
```

agent 需要能执行玩家机器上的 CLI。skill 是使用说明与工作流程，不会自动安装 DLL、启动游戏或给纯云端 agent 建立本地连接。本版无需 MCP；Codex 等平台可通过导入 skill 后执行 CLI 来接入。

### 1.3 一次编辑的调用顺序

1. `craft snapshot` 取得当前 `craftSessionId`、`revision` 与零件 ID。
2. 用 `catalog` 查询模板、属性元数据；用 `parts get`、`connections points` 查询真实零件和连接点。
3. 使用当前身份创建检查点，保存返回的检查点 ID。
4. 写入 UTF-8 JSON 文件，包含新 `requestId`、会话、预期版本及操作。
5. `batch preview` 查看结构检查结果，再 `batch apply` 执行；二者使用不同请求 ID，preview 不保证操作能实际成功。
6. 读取操作结果，再查询修改过的零件、连接或变量。后续写入使用最新版本。
7. 失败或超时时按任务查询与恢复流程处理。

## 2 命令格式和通用输出

### 2.1 参数约定

```text
sp2build <命令组> <子命令> [参数]
```

| 参数 | 用途与约束 |
| --- | --- |
| `--json` | 显式声明 JSON 输出；目前不添加此参数也输出 JSON |
| `--input FILE` | 读取 UTF-8 JSON 对象，支持 UTF-8 BOM；复杂操作建议使用文件 |
| `--input -` | 从标准输入读取 UTF-8 JSON；建议程序直接写入字节，避免 shell 编码转换 |
| `--output FILE` | 将完整结果写入 JSON 文件；stdout 改为路径、SHA256 和 `resultSuccess` 回执 |
| `--instance PID` | 选择游戏 PID；也接受 `instances list` 中的 `instanceId` |
| `--timeout SECONDS` | 等待任务的期限，默认 20 秒，范围大于 0 且不超过 600 秒；不是取消期限 |
| `--async` | 提交任务后立即返回任务信息；此时尚不能断言编辑成功 |
| `--request-id ID` | 写入的请求去重标识，也可放在输入文件的 `requestId` 中；命令行参数优先 |
| `--help`、`-h` | 返回通用用法说明；完整参数请查询 `commands schema` |

命令行使用连字符参数，JSON 使用 camelCase。例如 `--part-a 15 --part-b 16` 对应 `partA`、`partB`；`--include-xml` 对应 `includeXml: true`。`--include-xml` 是开关，后面不写 `true/false`；需要 false 时省略该参数或使用 JSON 输入。

查询参数可直接写在命令行；数组与复杂表达式建议写入输入文件。顶层不允许未知输入字段。快捷写入命令需要 `--input` 与其中的 `operation` 对象，不能直接通过 `--part-id` 等参数填写操作。

### 2.2 成功和错误

本地命令成功样例：

```json
{
  "success": true,
  "schemaVersion": "1",
  "data": {"version": "0.1.3", "python": "3.14.2"}
}
```

游戏查询通常多两个顶层字段：

```json
{
  "success": true,
  "schemaVersion": "1",
  "data": {"valid": true, "compiledOnly": true, "evaluated": false},
  "operationId": "OPERATION_ID",
  "instancePid": 10236
}
```

此处裁剪了 `funky validate` 的 `data.identity`。`operationId` 标识一次游戏任务；不要与写入请求的 `requestId` 混淆。

错误样例：

```json
{
  "success": false,
  "schemaVersion": "1",
  "error": {
    "code": "revision_conflict",
    "message": "Aircraft changed. Read a fresh snapshot and replan."
  },
  "operationId": "OPERATION_ID",
  "instancePid": 10236
}
```

本地输入错误或提交被拒绝时，输出可能没有 `operationId`。失败不保证没有产生过修改；批次失败需继续检查 `rollbackResult`。

`--output` 回执的结构示例：

```json
{
  "success": true,
  "schemaVersion": "1",
  "data": {
    "path": "C:\\work\\snapshot.json",
    "sha256": "FILE_SHA256",
    "resultSuccess": true
  }
}
```

回执顶层 `success` 表示结果文件写出成功。若文件内的游戏任务失败，`resultSuccess` 为 false，进程仍返回失败退出码；不能只看回执顶层 `success`。

### 2.3 飞机会话与版本

状态类查询通常返回以下 `identity`：

```json
{
  "craftSessionId": "SESSION",
  "revision": 1,
  "fingerprint": "CRAFT_FINGERPRINT",
  "fingerprintAlgorithm": "xml-sha256-generated-target-sets-v2",
  "gameVersion": "0.7.8.103",
  "xmlVersion": 25,
  "stateUncertain": false
}
```

| 字段 | 意义 |
| --- | --- |
| `craftSessionId` | 当前打开飞机的运行时会话；玩家更换飞机、原生对象替换等情况下可能改变 |
| `revision` | 工具在观察到状态指纹变化时递增的版本；不是固定“一次操作加一” |
| `fingerprint` | 当前状态指纹；对原生生成目标 ID 集合的顺序和重复 ID 作规范化 |
| `stateUncertain` | 前一次恢复未确认可靠；普通写入被阻止 |

所有写入均需 `craftSessionId` 和 `expectedRevision`；`expectedRevision` 填最近状态查询的 `revision`。工具自己的重建会维护逻辑会话，但不要硬编码会话、版本或初始零件 ID。

0.1.3 对原生恢复校验允许每轴最多 0.0001 度的 Euler 重建误差，其他内容仍进行一致性比较。这个容差仅用于恢复验证；版本指纹对旋转字段仍严格比较。因此恢复后指纹可能不同，需看 `rollbackResult.restored` 或 `validation.restorationVerified`，并重新读取当前状态。

## 3 本地管理和接口发现

DLL 0.3.2 起，推荐使用 `connections list --view structured`、`variables list --view structured`、`outputs list --view structured`。前者返回数值化连接行；变量返回带 `index` 的 setter 行；两种输出来源查询共用 `sources[].modifiers[].definitions/bindings`。不传 `--view` 仍返回旧结构，`data.view` 标明模式，schema 的 `data.oneOf` 描述两者。具体示例见 [0.3.2 修订说明](Agent-Feedback-0.3.2.md)。

这些命令不依赖正在运行的游戏。

| 功能 | 调用 | 主要返回内容 |
| --- | --- | --- |
| CLI 版本 | `sp2build version` | `data.version`、`python` |
| 可连接游戏实例 | `sp2build instances list` | `data.instances`，含 PID、实例 ID、DLL 版本、协议版本、回环地址；不输出访问令牌 |
| 所有命令 | `sp2build commands list` | `data.commands`、`operationKinds` |
| 输入 schema | `sp2build commands schema --command batch.apply` | `inputSchema`、命令 `outputSchema`、请求 ID 说明 |
| 操作 schema | `sp2build commands schema --operation part.update` | 该操作 kind 的字段、类型、必填项 |
| skill 路径 | `sp2build skill path` | 当前 CLI 安装目录内配套 skill 路径 |
| 离线零件资料 | `sp2build knowledge catalog --output catalog-offline.json` | `data.dataSource` 与 `knowledge` |
| 离线 Funky Trees 资料 | `sp2build knowledge funky --output funky-offline.json` | `data.dataSource` 与 `knowledge` |

0.3.1 为命令提供输入与输出 schema，包括 `data.part`、`data.listing.items`、挂点字段、单位及坐标系。使用 `--command connections.connect` 查询 CLI 信封，使用 `--operation connection.connect` 查询批次 operation；`entityKind` 明确区分，旧的单数 `--command` 查询兼容保留。`commandDetails` 提供映射。`asyncOutputSchema` 描述异步受理，`savedOutputSchema` 描述 `--output` 的 stdout 回执；文件内容仍遵循 `outputSchema`。`operation.wait/result` 的精确 data 取决于最初提交的命令。动态零件形状和原生元数据还需结合 `shape schema` / `catalog schema`。详见 [0.3.1 修订说明](Agent-Feedback-0.3.1.md)。

`skill path` 不一定等于 agent 已导入的 skills 路径；它指向 CLI 安装包中的源 skill。

离线知识按以下层级读取（结构示例）：

```json
{
  "success": true,
  "schemaVersion": "1",
  "data": {
    "dataSource": "versioned_offline_knowledge",
    "knowledge": {
      "success": true,
      "schemaVersion": "1",
      "data": {"gameVersion": "0.7.8.103", "entries": [], "schemas": []}
    }
  }
}
```

当前离线文件保存的是一次导出结果，正文在 `data.knowledge.data`；内层可能带历史 `operationId` 和 PID，不代表当前运行实例。零件离线文件默认包含 160 个非 Legacy 原生模板。运行时目录可能额外包含 Mod 或已加载的用户子组件，使用 `catalog` 确定当前可用内容。

## 4 编辑器状态和飞机查询

### 4.1 状态和能力

```powershell
sp2build designer status
sp2build capabilities
```

目前两者返回同一能力结构：`pluginVersion`、`gameVersion`、`designerReady`、`identity`、`target`、`commands`、`limitations`。未进入编辑器时，`designerReady` 为 false，`identity` 为 null；读当前飞机的命令会返回 `designer_not_ready`。

此前运行 DLL 0.1.2、已进入编辑器时的历史查询结果裁剪样例：

```json
{
  "success": true,
  "schemaVersion": "1",
  "data": {
    "pluginVersion": "0.1.2",
    "gameVersion": "0.7.8.103",
    "designerReady": true,
    "identity": {"craftSessionId": "SESSION", "revision": 1, "stateUncertain": false},
    "target": "current_open_designer_only"
  },
  "operationId": "OPERATION_ID",
  "instancePid": 10236
}
```

### 4.2 快照及零件

| 功能 | 调用 | 参数和主要返回内容 |
| --- | --- | --- |
| 完整快照 | `sp2build craft snapshot` | `identity`、`name`、`partCount`、`selectedPartId`、所有零件摘要、连接与全局变量 |
| 快照含 XML | `sp2build craft snapshot --include-xml --output snapshot.json` | 同上，另有 `data.xml`，为当前内存飞机的序列化文本 |
| 分页零件列表 | `sp2build parts list --offset 0 --limit 20` | `identity`、`listing`；默认 offset 0、limit 100，limit 范围 1 至 1000 |
| 类型筛选 | `sp2build parts list --type JFuselage-1 --limit 20` | `type` 精确匹配当前零件类型 ID |
| 名称检索 | `sp2build parts list --query Fuselage` | 当前零件名称的不区分大小写子串匹配 |
| 单件详情 | `sp2build parts get --id 15` | `data.part` 含基础属性、完整状态树、输出定义与绑定、连接点 |
| 原生组件范围 | `sp2build parts assembly --id 229` | DLL 0.2.2+；返回成员 ID、子件和外部连接；可选 --symmetric true |

快照历史输出裁剪样例：

```json
{
  "success": true,
  "schemaVersion": "1",
  "data": {
    "identity": {"craftSessionId": "SESSION", "revision": 1, "stateUncertain": false},
    "name": "Super Wasp",
    "partCount": 357,
    "selectedPartId": null,
    "parts": [
      {
        "id": 15,
        "type": "JFuselage-1",
        "name": "Fuselage",
        "position": [0.0000009886347, 4.566297, -0.6511303],
        "rotationEulerDegrees": [0, 0, 0],
        "rotationQuaternion": [0, 0, 0, 1],
        "scale": [1, 1, 1],
        "symmetryId": 0,
        "materialIds": [0, 0, 0, 0, 0],
        "connectedPartIds": [16, 19, 18, 86, 144, 33, 40, 278, 175, 326]
      }
    ],
    "coordinateSystem": "Unity world; metres; Euler degrees; quaternion x,y,z,w"
  },
  "operationId": "OPERATION_ID",
  "instancePid": 10236
}
```

此样例省略了 `connections`、`variables` 和其余零件。`position` 为 Unity 世界坐标，单位米；Euler 角单位度，四元数顺序为 x、y、z、w。没有直接返回完整网格或包围盒的专用接口。

### 4.3 原生状态树

`parts get` 的 `state`、快照的 `connections` 和 `variables` 使用相同 XML 到 JSON 的树结构：

```json
{
  "element": "Part",
  "attributes": {"id": "358", "partType": "Block-1", "position": "22,5,0", "massScale": "1.25"},
  "children": [
    {"element": "AdaptiveBlock.State", "attributes": {"state": "0"}, "children": [], "text": ""}
  ],
  "text": null
}
```

`element` 是原生节点名，`attributes` 中的 XML 属性值均为字符串；这与 `part.position` 等已转换成数值数组的摘要字段不同。`children` 保留子节点顺序，有子节点时 `text` 为 null。节点不存在时可能直接返回 null，而非空节点。

## 5 连接拓扑和空间关系

连接不会通用地吸附位姿，挂载物位置须单独编辑。BFS 回答连通性；“在哪片机翼下方”使用几何、变换及射线，单条命中不证明实际受力归属。组件级删除、完整样例及七操作事务证据见 [0.2.2 反馈核查](Connections-Assemblies-and-Transactions-0.2.2.md)。

```powershell
sp2build connections list
sp2build connections points --part 358
sp2build spatial query --part-a 15 --part-b 16
```

`connections list` 的 `data.connections` 返回全部原生连接。历史输出裁剪样例：

```json
{
  "element": "Connections",
  "attributes": {},
  "children": [
    {
      "element": "Connection",
      "attributes": {"partA": "15", "partB": "16", "attachPointsA": "0", "attachPointsB": "1"},
      "children": [],
      "text": ""
    }
  ],
  "text": null
}
```

一个 Connection 可以有多个连接点；`attachPointsA/B` 为原生序列化字符串，不能假定永远只有一个数字。零件摘要的 `connectedPartIds` 是邻居列表，适合快速建立图；完整连接点关系应读取连接树。

`connections points` 返回 `identity` 与 `points`。一个连接点的历史样例：

```json
{
  "id": 0,
  "localPosition": [0, 0, 0.25],
  "worldPosition": [20, 5, 1.25],
  "normal": [0, 0, 1],
  "available": true,
  "allowManualConnection": true,
  "allowMultiple": false,
  "seekType": "Normal",
  "receiveType": "Normal",
  "jointType": "Fixed"
}
```

`normal` 是零件局部法线，当前没有单独的世界法线字段。可用标志不能替代兼容性校验；实际连接仍由游戏原生方法决定。

`spatial query` 的 `data` 历史样例（省略 identity）：

```json
{
  "deltaWorld": [0, -0.0100002289, -2.07995558],
  "positionBInA": [0, -0.0100002289, -2.07995558],
  "distanceMetres": 2.07997966
}
```

`deltaWorld` 为 B 世界位置减 A 世界位置；`positionBInA` 使用 A 的逆变换计算，考虑其旋转及缩放；距离单位米。

## 6 全部零件库检索和属性说明

### 6.1 检索命令

| 功能 | 调用 | 参数与返回 |
| --- | --- | --- |
| 大类列表 | `sp2build catalog categories` | `gameVersion`、`categories[{id,name,count}]` |
| 小类列表 | `sp2build catalog subcategories --category Structure` | `category`、`subcategories[{id,name,count}]` |
| 分类零件列表 | `sp2build catalog list --category Structure --subcategory Blocks --limit 20` | `gameVersion`、`listing`；支持 category、subcategory、query、offset、limit |
| 零件检索 | `sp2build catalog search --query Block --limit 20` | 对模板摘要文本作不区分大小写的子串检索，含名称、介绍、分类、类型等；无相似度排名 |
| 模板介绍 | `sp2build catalog get --id tpl-6f0a7d0506e484d3` | 一个模板摘要 |
| 模板属性 | `sp2build catalog schema --id tpl-6f0a7d0506e484d3` | `templates` 中包含默认状态、原生属性元数据与输出定义 |
| 按类型找属性 | `sp2build catalog schema --type JFuselage-1` | 返回采用该类型的所有可用模板；同一类型可能有多个预设模板 |
| 导出完整目录 | `sp2build catalog export --output catalog-runtime.json` | `entries`、`schemas`、游戏版本、生成时间 |

`--category`、`--subcategory` 用游戏返回的原生字符串，精确匹配。`catalog schema` 提供 id 或 type；不要同时提供二者：当前 CLI 的 schema 定义要求二选一，而 DLL 实现会在二者都有时优先 id。

目录来源是游戏当前已加载的非 Legacy 模板，包含当前飞机没有使用的零件。原生大类示例为 Structure、Wings、Aircraft Propulsion、Engines、Wheels、Weapons、Interiors、Gizmos；编辑器还可能有 Sub Assemblies 与 Mod 类别。分类和计数不宜硬编码。

结构分类的历史返回正文：

```json
{
  "category": "Structure",
  "subcategories": [
    {"id": "Procedural", "name": "Procedural", "count": 5},
    {"id": "Prototype", "name": "Prototype", "count": 2},
    {"id": "Blocks", "name": "Blocks", "count": 5}
  ]
}
```

模板介绍的历史返回正文：

```json
{
  "id": "tpl-6f0a7d0506e484d3",
  "name": "Block",
  "description": "The basic building block. Snap these together to build the body of your airplane.",
  "category": "Structure",
  "subcategory": "Blocks",
  "creatable": true,
  "source": "builtin",
  "partTypes": ["Block-1"]
}
```

`id` 是**模板 ID**，用于新增；`partTypes` 是底层类型 ID；飞机中每个实例另有整数**零件 ID**。一个模板可以是多件子组件。`source` 可以是 `builtin`、`loaded_subassembly`、`mod`；`creatable` 反映当前关卡的分类或模板限制。

### 6.2 属性 schema 返回内容

`catalog schema` 的历史返回正文裁剪样例：

```json
{
  "gameVersion": "0.7.8.103",
  "dataSource": "isolated_template_data_and_native_overload_metadata",
  "templates": [
    {
      "id": "tpl-6f0a7d0506e484d3",
      "name": "Block",
      "description": "The basic building block. Snap these together to build the body of your airplane.",
      "parts": [
        {
          "partType": "Block-1",
          "templatePartId": 1,
          "defaultState": {"element": "Part", "attributes": {"id": "1", "partType": "Block-1", "position": "0.0, 0.0, 0.0", "rotation": "0.0, 0.0, 0.0"}, "children": [], "text": ""},
          "metadata": [
            {
              "element": "Part",
              "attributes": [
                {"name": "id", "type": "Int", "label": "ID", "description": "Unique integer identifier for this part within the craft. Changing this breaks craft loading if the new ID is invalid or matches another part.", "defaultValue": null, "min": null, "max": null, "enumValues": null, "optional": false, "readOnly": true}
              ],
              "childElements": ["AdaptiveBlock.State"]
            }
          ],
          "outputs": []
        }
      ],
      "coverage": "native_overload_metadata_plus_all_template_attributes"
    }
  ]
}
```

实际结果含其余属性及 `limitations`。元数据字段说明：

| 字段 | 意义 |
| --- | --- |
| `element` | 属性所属 XML 节点，用于确定修改路径 |
| `name` | 原生属性名，用作写入的 attribute |
| `type` | 原生类型，如 String、Bool、Int、Float、Enum、Vector3 |
| `label`、`description` | 原生属性标签与提示说明，可能为空 |
| `defaultValue` | 原生元数据默认值；具体预设值还应看 defaultState |
| `min`、`max` | 原生数值范围；null 表示元数据未提供，不代表无物理约束 |
| `enumValues` | 可用枚举值；未提供时可为 null |
| `optional`、`readOnly` | 是否可省略、是否只读 |
| `childElements` | 元数据描述的子节点名 |

模板 schema 用隔离的模板数据生成，不会把模板添加到当前飞机。它不保证覆盖所有未公开字段、实例相关 UI 限制或 Mod 行为。原始模板属性即使缺少解释，也可能出现在 defaultState；没有对应 metadata 的字段当前不能通过通用属性编辑器修改。

`catalog export` 顶层成功不保证每个模板 schema 都成功，需检查 `schemas` 各项是否有 `error`。最近实机导出为 176 个模板，含 160 个原生模板和 16 个已加载用户子组件，该次导出的 schema 错误数为 0。

## 7 批次与零件编辑

### 7.1 完整输入文件

保存为 `batch.json`，替换身份、版本、请求 ID 和模板 ID：

```json
{
  "requestId": "REQUEST_ID",
  "craftSessionId": "SESSION",
  "expectedRevision": 1,
  "operations": [
    {"kind": "part.add", "templateId": "tpl-6f0a7d0506e484d3", "temporaryId": "blockA", "position": [20, 5, 0], "rotation": [0, 0, 0]},
    {"kind": "part.update", "partId": "blockA", "changes": [
      {"path": "", "attribute": "name", "value": "AgentBlock"},
      {"path": "", "attribute": "massScale", "value": 1.25}
    ]}
  ]
}
```

```powershell
sp2build batch preview --input batch.json --request-id PREVIEW_REQUEST_ID
sp2build batch apply --input batch.json
```

preview 与 apply 可以使用同一个文件，但它们是不同命令，请采用不同请求 ID。上例用 `--request-id` 将 preview 的 ID 覆盖为另一个唯一 ID，apply 使用文件里的固定 ID；`PREVIEW_REQUEST_ID` 也需替换。另一种方式是为 preview 使用不含 requestId 的输入文件。更换命令却复用已提交的同一个 ID 会得到 `request_id_conflict`。

每批 1 至 100 个操作，按数组顺序执行。`temporaryId` 仅在当前批次内用于引用新模板的首个零件；下一批需结合最新读回确认 `temporaryIds` 中存活的真实整数 ID。0.3.1 中已删除的数字 ID 在当前批次始终失效；替代件必须通过新的 temporaryId 引用。`reusedPartIds` 记录复用事件，`invalidatedTemporaryIds` 列出失效临时引用。

### 7.2 零件与连接操作

以下对象放入 `operations` 数组。标为可选的字段可以省略。

| kind | 必填字段 | 可选字段与行为 |
| --- | --- | --- |
| `part.add` | `templateId` | `temporaryId`、`position[3]`、`rotation[3]`；position 为模板首件的目标世界位置，缺省保留模板原点；rotation 为围绕首件施加的 Euler 旋转偏移，缺省为零，不是覆盖模板原姿态 |
| `part.update` | `partId`、`changes` | changes 中每项必填 attribute 和 value，path 缺省为根节点；支持整数 ID 或本批临时 ID |
| `part.delete` | `partId` | `symmetric`、`assembly` 默认 false；assembly 要求 DLL 0.2.2+，仅明确原生归属的导弹组件/机翼控制面；禁止删除当前主驾驶舱 |
| `connection.connect` | `partA`、`partB`、`attachPointA`、`attachPointB` | `symmetric` 默认 false；连接点需可用且兼容，由原生方法建立连接 |
| `connection.disconnect` | `partA`、`partB` | `symmetric` 默认 false；删除两件之间的全部连接，不是只删一个连接点对 |

示例操作对象分别为：

```json
{"kind":"part.update","partId":358,"changes":[{"path":"","attribute":"position","value":[22,5,0]},{"path":"","attribute":"rotation","value":[0,10,0]},{"path":"","attribute":"scale","value":[1,1,1]}]}
```

```json
{"kind":"connection.connect","partA":358,"partB":359,"attachPointA":0,"attachPointB":1,"symmetric":false}
```

```json
{"kind":"connection.disconnect","partA":358,"partB":359,"symmetric":false}
```

```json
{"kind":"part.delete","partId":358,"symmetric":false}
```

新增模板可能生成多件，返回的 `partIds` 列出所有真实 ID；只有第一件对应该操作的 temporaryId。新增后不会自动连接到其他飞机零件，需要显式执行连接操作。模板姿态可能自带旋转，因此请读回最终位置与姿态。

### 7.3 属性路径和编辑限制

| 路径写法 | 含义 |
| --- | --- |
| `""` 或单独的 `"Part"` | 当前 Part 根节点的属性，如 name、massScale、position |
| `"JetEngine.State"` | 相应 modifier 状态节点的属性；以实际返回节点为准 |
| `"JFuselage.State/Sections/Section[0]"` | 路径语法示例，逐层定位零件内的节点；必须确认当前状态树确实存在这些节点 |

重复子节点从 0 开始计数；省略 `[index]` 会取同名第一个节点。路径相对当前 Part，不能在子节点路径前加 `Part/`。当前通用 setter 只编辑既有节点的属性，不支持任意新增、删除 XML 子节点或列表项。

数值必须有限，Int 必须整数，Bool 使用 JSON true/false，枚举使用原生字符串，Vector3 可以用三项数字数组。metadata 的范围、只读及 optional 限制会被检查；optional 属性可通过 `value: null` 移除。

`id`、`partType`、`symmetryId`、`materials` 即使原生 metadata 标为可编辑，也被当前通用工具额外禁止，避免破坏结构引用。symmetryId/symmetryDisabled 应使用 symmetry 专用接口。shape.update 默认传播到已启用原生组；part.update 需要显式 symmetric:true；材料和类型仍不支持专用修改。

### 7.4 preview 与 apply 输出

preview 历史输出正文裁剪样例：

```json
{
  "identity": {"craftSessionId": "SESSION", "revision": 1},
  "validated": "request_structure_only",
  "operationCount": 2,
  "warnings": ["Metadata, native creation, connections and expression validation run at apply. Preview does not reserve the revision."]
}
```

apply 成功的结构示例：

```json
{
  "success": true,
  "schemaVersion": "1",
  "data": {
    "identity": {"craftSessionId": "SESSION", "revision": 2, "fingerprint": "NEW_FINGERPRINT", "stateUncertain": false},
    "operationId": "OPERATION_ID",
    "actualChanges": [
      {"kind": "part.add", "partIds": [358], "templateId": "tpl-6f0a7d0506e484d3"},
      {"kind": "part.update", "partId": 358, "editMode": "current_craft_rebuild"}
    ],
    "temporaryIds": {"blockA": 358},
    "beforeCheckpointId": "before-OPERATION_ID",
    "validation": {"readBack": true, "expressionCompile": true, "partCount": 358, "restorationVerified": null, "restoreEulerToleranceDegrees": 0.0001},
    "rollbackResult": {"required": false},
    "selectionResetByRebuild": true
  },
  "operationId": "OPERATION_ID",
  "instancePid": 10236
}
```

`actualChanges` 是操作摘要，不是所有修改后属性值；`validation.readBack` 不代表逐个参数与期望值完全相等。需要继续查询受影响的 parts、connections 或 variables。`beforeCheckpointId` 可能为 null，表示检查点容量不足等原因未创建自动检查点。

0.2 的复杂编辑、撤销和回滚等待原生几何任务完成，重新绑定物理碰撞网格并重建编辑器缓存，恢复原先的选中 ID（若仍存在）。旧样例中的 selectionResetByRebuild 字段已由 selectedPartId 和 validation.geometryRefreshed 等字段替代。写入期间工具暂时暂停编辑器输入。

### 7.5 单操作快捷命令

这些快捷命令都转成只有一个操作的 `batch.apply`，返回同一结果结构：

| 快捷调用 | 对应 kind |
| --- | --- |
| `sp2build parts add --input one.json` | `part.add` |
| `sp2build parts update --input one.json` | `part.update` |
| `sp2build parts delete --input one.json` | `part.delete` |
| `sp2build connections connect --input one.json` | `connection.connect` |
| `sp2build connections disconnect --input one.json` | `connection.disconnect` |
| `sp2build variables add --input one.json` | `variable.add` |
| `sp2build variables update --input one.json` | `variable.update` |
| `sp2build variables delete --input one.json` | `variable.delete` |
| `sp2build variables reorder --input one.json` | `variable.reorder` |
| `sp2build outputs bind --input one.json` | `output.bind` |
| `sp2build outputs update --input one.json` | `output.update` |
| `sp2build outputs unbind --input one.json` | `output.unbind` |

`parts update` 的 `one.json` 示例：

```json
{
  "requestId": "REQUEST_ID",
  "craftSessionId": "SESSION",
  "expectedRevision": 1,
  "operation": {"partId": 358, "changes": [{"path": "", "attribute": "name", "value": "AgentBlock"}]}
}
```

顶层使用单数 `operation`，不使用 `operations`；kind 会由快捷命令自动填写。应保持同一请求的调用形式不变，便于复现和去重。

## 8 全局变量和零件输出

### 8.1 查询

```powershell
sp2build variables list
sp2build outputs list
sp2build outputs list --part 20
```

`variables list` 返回 `identity`、`setters` 原生节点树和 `sources`（各件输出）。`outputs list` 返回 `identity`、`parts[{partId,modifiers}]`，其中每个 modifier 有 `definitions` 与 `bindings`。零件输出不是飞行遥测值；接口描述其定义和编辑器绑定。

Setter 结构示例：

```json
{
  "element": "Variables",
  "attributes": {},
  "children": [
    {"element": "Setter", "attributes": {"variable": "BuildTest", "function": "clamp(Throttle,0,1)", "priority": "0"}, "children": [], "text": ""}
  ],
  "text": null
}
```

一个零件的原生输出定义历史样例：

```json
{
  "partId": 20,
  "modifiers": [
    {
      "modifier": "JointRotator.State",
      "definitions": [{"id": "BodyAngle", "name": "Current Angle", "defaultVariable": null, "defaultPriority": 0}],
      "bindings": []
    }
  ]
}
```

绑定后的结构示例：

```json
{"outputId":"BodyAngle","variable":"BayAngle","priority":0,"activator":"Activate1"}
```

`modifier` 使用原生状态节点名；`outputId` 使用 definitions 中的 id，不使用 UI 标签 Current Angle。飞控芯片等部件按同一方法查询其原生输出；当前并没有独立的“飞控芯片程序编辑”命令。

### 8.2 编辑操作

| kind | 必填字段 | 可选字段及默认行为 |
| --- | --- | --- |
| `variable.add` | `variable`、`function` | `priority` 默认 0；`activator` 可选；追加到 Setter 列表 |
| `variable.update` | `index` | `variable`、`function`、`priority`、`activator`，只改提供的字段 |
| `variable.delete` | `index` | 删除该 Setter，不表示删除所有同名变量来源 |
| `variable.reorder` | `order` | 当前全部 Setter 索引的完整排列，不能遗漏或重复 |
| `output.bind` | `partId`、`modifier`、`outputId`、`variable` | `priority` 缺省新绑定为 0；`activator` 可选；同一 output 已有绑定时修改该绑定 |
| `output.update` | `partId`、`modifier`、`outputId` | `variable`、`priority`、`activator`；要求该绑定已经存在 |
| `output.unbind` | `partId`、`modifier`、`outputId` | 删除指定输出绑定，保留空 Variables 节点以防原生默认绑定重新创建 |

以下示例分别放入批次 operations，或单操作快捷输入的 operation：

```json
{"kind":"variable.add","variable":"BuildTest","function":"clamp(Throttle,0,1)","priority":0,"activator":"true"}
```

```json
{"kind":"variable.update","index":0,"variable":"BuildTestRenamed","function":"0.75","priority":5}
```

```json
{"kind":"variable.delete","index":0}
```

```json
{"kind":"variable.reorder","order":[1,0,2]}
```

```json
{"kind":"output.bind","partId":20,"modifier":"JointRotator.State","outputId":"BodyAngle","variable":"BayAngle","priority":0}
```

```json
{"kind":"output.update","partId":20,"modifier":"JointRotator.State","outputId":"BodyAngle","variable":"BayAngleRenamed","priority":4,"activator":"Activate1"}
```

```json
{"kind":"output.unbind","partId":20,"modifier":"JointRotator.State","outputId":"BodyAngle"}
```

index 是 `setters.children` 中 Setter 的零基序号；删除或排序后必须重新读取序号。order 示例假设当前恰有三个 Setter，不可直接用于其他数量的飞机。多个 Setter 和多个零件输出可以指向同名变量，具体合成采用游戏原生规则。

新变量名仅允许 ASCII 字母、数字与下划线，不能以数字开头，不能与内置表达式符号冲突。改名只修改选中的 Setter 或输出绑定，**不会自动替换其他表达式中的旧变量引用**；必要时同时更新相关表达式。此版没有引用检索或批量安全重命名命令。

包含 activator 的输出编辑在 0.1.1 及更早实现中存在编辑器初始化问题，后续已修复。0.3.1 已实机验证临时干扰弹发射器的输出绑定、修改 activator/priority 与解绑，并在测试后恢复；这不代表所有部件的飞行输出行为均已验证。使用前应确认实际加载版本，不只检查 CLI version。

## 9 Funky Trees 查询与表达式检查

```powershell
sp2build funky list
sp2build funky describe --name clamp
sp2build funky describe --name pi
sp2build funky validate --expression 'clamp(Throttle,0,1)'
sp2build funky validate --expression 'Activate1' --type bool
```

| 命令 | 参数与返回 |
| --- | --- |
| `funky list` | 当前原生表达式 context 的全部 entries，含常量、普通函数、状态函数、输入或变量 |
| `funky describe` | 必填 name，按原生名字精确匹配；找不到时成功返回空 entries，不是错误 |
| `funky validate` | 必填 expression，type 默认按 float 编译，布尔表达式明确填 `bool`；返回 valid、compiledOnly、evaluated 与 identity，错误表达式返回失败 |

clamp 的历史返回正文：

```json
{
  "gameVersion": "0.7.8.103",
  "source": "native_expression_context",
  "trigUnit": "degrees",
  "evaluated": false,
  "entries": [
    {
      "name": "clamp",
      "kind": "function",
      "returns": "Single",
      "parameters": [{"name":"value","type":"Single"},{"name":"min","type":"Single"},{"name":"max","type":"Single"}],
      "description": "clamp(value,min,max): restrict value to the inclusive range."
    }
  ]
}
```

常量示例为 `{"name":"pi","kind":"constant","value":3.14159274}`。kind 还包括 `stateful_function`、`input_or_variable`；`Single` 是 .NET 的单精度浮点数类型。输入与用户变量未在 kind 上进一步区分，状态函数暂未提供完整参数签名，许多函数的语义说明尚未整理。

未进入编辑器时，list 与 describe 使用默认原生 Context，可查询基础函数和常量，但不保证有飞机输入及用户变量。validate 需要当前飞机。表达式编译成功不代表逻辑合理或飞行效果正确；本版不会执行表达式，也不提供当前飞行输出数值。

## 10 历史 检查点 撤销与回滚

### 10.1 历史和检查点查询

```powershell
sp2build craft history
sp2build craft checkpoint list
sp2build craft checkpoint get --id CHECKPOINT_ID
```

| 命令 | 返回 |
| --- | --- |
| `craft history` | identity、工具成功操作的 operations、原生 nativeSteps、canUndo、canRedo |
| `craft checkpoint list` | identity、当前会话的检查点摘要列表 |
| `craft checkpoint get` | identity、指定 checkpoint 摘要；不输出其完整飞机 XML |

历史中的 `nativeSteps` 使用原生字段 `Description`（首字母大写），并含 index、time、hash。`operations` 只记录工具成功的编辑，不是所有提交或失败任务的审计日志。当前没有导出原生历史游标的专用字段，也没有 CLI redo 命令，虽然 history 能显示 `canRedo`。

### 10.2 创建检查点

`checkpoint.json`：

```json
{"requestId":"REQUEST_ID","craftSessionId":"SESSION","expectedRevision":1,"name":"Before wing edits"}
```

```powershell
sp2build craft checkpoint create --input checkpoint.json
```

历史成功输出正文示例：

```json
{
  "id": "CHECKPOINT_ID",
  "name": "Before wing edits",
  "craftSessionId": "SESSION",
  "revision": 1,
  "fingerprint": "CRAFT_FINGERPRINT",
  "createdAt": "2026-10-01T07:29:23.9206447Z"
}
```

createdAt 为 UTC。检查点仅保存当前会话内存状态，最多 64 个，包含自动创建的 before 检查点；此版没有检查点删除命令或跨重启持久化。

### 10.3 撤销

`undo.json`：

```json
{"requestId":"REQUEST_ID","craftSessionId":"SESSION","expectedRevision":2}
```

```powershell
sp2build craft undo --input undo.json
```

撤销一个原生历史步骤，玩家与 agent 的编辑共同按原生历史顺序处理；不要假定“一次 undo 就撤销上一批全部操作”。可选 `expectedHeadHash` 用于校验原生当前历史头，但它不是飞机 fingerprint，history 当前也未明确标出哪项是当前头，只有确认原生当前头时才应填写。

### 10.4 回滚指定检查点

`rollback.json`：

```json
{"requestId":"REQUEST_ID","craftSessionId":"SESSION","expectedRevision":5,"checkpointId":"CHECKPOINT_ID"}
```

```powershell
sp2build craft rollback --input rollback.json
```

用完整检查点状态重建当前飞机，会恢复该点的零件、连接、变量等整体内容，并影响检查点后玩家和 agent 的编辑。回滚会写入原生历史，完成后读回当前状态。

undo 和 rollback 成功都使用 batch apply 的结果信封，actualChanges 的 kind 分别为 craft.undo 或 craft.rollback；后者还含 checkpointId。恢复成功结果会带 `validation.restorationVerified: true`。0.3.1 已实机验证 undo/rollback，并独立比较恢复后的完整飞机 XML；详见 [验收记录](Verification-0.3.1.md)。

### 10.5 批次失败后的自动恢复

以下为恢复成功时的**结构示例**，不是最近实机失败输出的成功改写：

```json
{
  "success": false,
  "schemaVersion": "1",
  "error": {"code": "execution_failed", "message": "Function clamp takes 3 arguments, 0 were given."},
  "rollbackResult": {
    "attempted": true,
    "restored": true,
    "error": null,
    "restoreEulerToleranceDegrees": 0.0001,
    "fingerprintIdentical": false,
    "beforeFingerprint": "BEFORE_FINGERPRINT",
    "currentFingerprint": "CURRENT_FINGERPRINT"
  },
  "identity": {"craftSessionId": "SESSION", "revision": 6, "stateUncertain": false},
  "operationId": "OPERATION_ID",
  "instancePid": 10236
}
```

`success: false` 表示请求失败，即使 restored 为 true 也不能认为请求已生效。`restored: false` 或 `stateUncertain: true` 时停止依赖当前结果的普通写入，先读状态。0.1.3 实现允许在身份、版本及检查点仍有效时显式 `craft rollback` 恢复；0.1.2 会因 uncertain 阻止该入口，需玩家原生恢复或重新打开目标飞机。不要反复盲目重试造成额外编辑。

## 11 异步任务 请求去重与超时

```powershell
sp2build batch apply --input batch.json --async
sp2build operation status --id OPERATION_ID
sp2build operation wait --id OPERATION_ID --timeout 60
sp2build operation result --id OPERATION_ID
sp2build operation cancel --id OPERATION_ID
```

| 命令 | 行为与输出 |
| --- | --- |
| `operation status` | 查询一次任务状态，`data` 中含 operationId、state、createdAt、result |
| `operation wait` | 等到终态或等待超时；终态时直接返回任务结果信封 |
| `operation result` | 当前与 wait 相同，包括必要时等待；不是永远立即返回 |
| `operation cancel` | 请求取消；返回任务状态，不保证任务已经取消 |

异步提交后可能返回 queued、running 或已经完成的状态。结构示例：

```json
{
  "success": true,
  "schemaVersion": "1",
  "data": {"operationId":"OPERATION_ID","state":"queued","createdAt":"2026-10-01T07:29:23Z","result":null,"instancePid":10236}
}
```

状态集合为 queued、running、succeeded、failed、cancelled、result_expired。status 顶层 success 仅表示查询成功；真正编辑是否成功需看 state 及嵌套 result。wait/result 则返回最终 result，失败任务直接是 success false。

任务在 queued 阶段收到取消请求时可取消，已经 running 的编辑允许完成。已完成任务的取消请求不会撤销编辑；仍应查看结果并选择恢复方法。

超时输出的结构示例：

```json
{
  "success": false,
  "schemaVersion": "1",
  "error": {
    "code": "wait_timeout",
    "message": "Task is still active. Query operation status/wait; do not blindly retry.",
    "operationId": "OPERATION_ID",
    "state": "running",
    "instancePid": 10236
  }
}
```

超时中 operationId 位于 error 内，与正常结果的顶层不同。此时 CLI 结束不等于游戏编辑结束；保持同一 instance 查询原任务。

同一游戏进程内，**相同 requestId 加相同命令和内容**返回同一任务；同 ID 内容不同返回 request_id_conflict。身份与 expectedRevision 也是内容的一部分：若要取回一个已执行请求，保持原文件不变；若明确遇到版本冲突并重新规划，应使用新请求 ID。CLI 传输会排序 JSON 字段，操作数组顺序仍有意义。

0.5.0 dev12 起，完成结果压缩保留，最多 15 分钟（从完成时计）且全实例共用 64 MiB 压缩结果预算；达到时间或容量上限时先清理最早完成的结果。查询也会触发到期清理，完成任务的输入立即释放。单个压缩结果若超过整个预算，则立即返回 result_expired，并标明 single_result_exceeds_capacity。status 的 completionState 保留 succeeded/failed/cancelled 实际终态，resultRetention 解释结果是否可用；极少数结果保存异常为 retention_failed。不要因为结果过期而用新 requestId 重发写入。designer status.runtimeRetention 提供缓存字节数、条数和检查点数等诊断，不代表整个游戏进程内存。

原生 `nativeUndo.count` 统计保留的状态数，包含当前状态；`maximum` 对应游戏的最多可撤销次数。dev16新增 `maximumRetainedStates` 明确最多保留状态数：本机游戏为251份状态、250次撤销。旧开发构建没有此补充字段时，不能仅凭 `count > maximum` 判断泄漏。计数达到上限后，原来较小的状态被较大飞机快照替换，`xmlBytes` 仍可能暂时增加；须区分条数、状态大小与总体内存。

dev23新增 `runtimeRetention.nativeMeshLifetime`：`installed`表示当前游戏模块已启用原生临时网格释放兼容修复；`auditedGameModule`给出经过核对的模块ID，`conversions/releases`为转换和释放累计数。修复只覆盖该模块的设计器网格转换，不修改游戏文件；未知模块不启用并在日志提示。计数相等只证明这条转换路径的释放配对，不能证明整个游戏无泄漏。长期内存验收状态见[验收总览](Acceptance-Status-0.5.0.md)。

旧 DLL 使用从任务创建起计的 15 分钟结果清理。各版本的去重记录均保留至游戏实例退出，每实例最多 20,000 个任务；结果清理不会再次执行同一个 requestId。游戏重启后旧任务可能 operation_not_found；**这不证明它没有执行过**，应读当前状态确认。

## 12 常见错误和限制

### 12.1 退出码

| 退出码 | 意义或错误代码 |
| --- | --- |
| 0 | 调用成功；异步提交或状态查询仍需检查任务终态 |
| 2 | invalid_input、unsupported_command |
| 3 | bridge_not_running、multiple_instances、bridge_unreachable |
| 4 | session_conflict、revision_conflict、request_id_conflict、history_conflict |
| 5 | 其他失败，包括执行错误、属性错误、状态不确定、恢复错误、结果过期等 |
| 8 | wait_timeout |
| 9 | operation_not_found |

在 PowerShell 中检查 `$LASTEXITCODE`，在 Python 中检查 subprocess.returncode；同时解析 JSON error.code。

### 12.2 处理建议

| error.code | 处理 |
| --- | --- |
| bridge_not_running | 确认 BepInEx、DLL 安装及游戏已重启；检查 instances list |
| multiple_instances | 从 instances list 选择 PID，加 --instance |
| designer_not_ready | 由玩家进入目标飞机编辑器 |
| catalog_not_ready | 游戏原生零件库尚未初始化，稍后再查 |
| session_conflict、revision_conflict | 重新读快照，确认目标并重新规划，不复用旧版本 |
| request_id_conflict | 查明原请求；同一 ID 不要用于不同内容或命令 |
| part_not_found、template_not_found | 分别刷新当前零件列表、零件库模板列表 |
| unsupported_property、read_only | 根据 metadata 和工具限制调整请求，不能通过原始 XML 绕过 |
| out_of_range、invalid_enum、invalid_vector | 修正元数据范围、枚举字符串或向量格式 |
| invalid_connection、connection_rejected | 查询连接点，确认可用性和兼容性 |
| invalid_variable_name、built_in_name_conflict | 使用合法变量名，避开内置符号 |
| undo_unavailable、checkpoint_not_found | 检查历史或检查点是否属于当前会话 |
| native_settle_timeout、restore_mismatch | 0.1.3 恢复或原生状态校验失败；检查 rollbackResult 和当前状态 |
| state_uncertain | 停止普通写入；仅在 0.1.3 中可显式回滚到有效检查点，或由玩家处理 |
| result_expired、operation_not_found | 不能据此判断请求未运行，先确认当前飞机状态 |

### 12.3 当前不提供的能力

- 未打开保存飞机的读取、打开、修改或批量处理，以及按路径保存飞机的 CLI 命令。快照输出到用户指定 JSON 文件是导出当前状态，不是游戏保存接口；游戏自己的自动保存行为仍可能发生。
- 所有隐藏或 Legacy 零件类型的任意实例化；新增只使用当前注册的非 Legacy 模板，受关卡限制。
- 飞行、飞行遥测求值、完整物理仿真、飞控芯片程序专用编辑、完整碰撞网格导出或原生材质渲染。0.3.0 已提供实际表面网格的分析图片，见视觉检查手册。
- 材料专用编辑、任意 XML 列表结构编辑；复杂几何与对称功能的具体覆盖见 0.2 扩展说明。
- 变量引用检索、跨表达式自动改名、CLI redo、检查点删除及跨会话持久化恢复。
- 全部未公开属性的完整解释，以及每个 Funky Trees 函数的完整语义和状态函数签名。

## 13 验证状态和源码依据

### 13.1 历史基线（0.1.x）

下表保留 0.1.x 当时的证据和未解决项，不表示这些问题在当前版本仍然存在。当前版本的构建、部署、离线及实机验收状态统一维护在 [Verification.md](../Verification.md)，历史 0.2.1 验收另有保留。

| 功能 | 目前证据 |
| --- | --- |
| CLI 安装及全局入口 | 已验证，当前 CLI version 返回 0.1.3 |
| 编辑器状态、快照、零件详情、连接点、空间查询 | 已在 Super Wasp 实机读回 |
| 原生分类、模板介绍、全库 schema 导出 | 已验证；最近导出 176 个模板，schema 错误数 0 |
| 零件新增、名称/质量/位置修改、连接、断开、删除 | 在 0.1.1 实机通过，0.1.2 也验证过新增及属性读回 |
| 请求去重和版本冲突保护 | 实机验证通过 |
| 全局 Setter 新增、修改、排序、删除 | 0.1.1 实机验证通过 |
| 输出 bind | 实机通过；带 activator 的 output update 曾触发初始化错误，后续代码修复待完整复测 |
| Funky Trees 普通函数说明和表达式检查 | clamp 查询、合法/非法表达式验证通过 |
| 检查点创建和查询 | 实机通过 |
| 原生 undo、指定检查点 rollback、批次失败自动恢复 | 已实现，但先前实机发现浮点与网格更新时序问题；0.1.3 修复的完整实机复测尚未完成，不能承诺可靠恢复 |
| 异步 wait/status/result、取消和结果过期 | 已实现；部分恢复契约有独立测试，完整游戏场景验证未完成 |

功能表描述当前代码提供的接口，不能等同于验收已完成。使用写入接口前仍需读回实际结果并保留已知恢复起点。

### 13.2 可查阅的项目文件

- [CLI 实现](../cli/sp2build.py)：命令名、参数转换、schema、退出码和任务等待。
- [游戏桥接实现](../bridge/BuildRuntime.cs)：查询数据结构、原生编辑、属性检查、恢复流程。
- [任务和本地通信](../bridge/Transport.cs)：请求去重、任务状态、保留期限、实例发现。
- [状态指纹和恢复比较](../bridge/SnapshotState.cs)：原生目标集合规范化及旋转恢复容差。
- [agent skill](../skills/sp2-build-assistant/SKILL.md) 与 [操作参考](../skills/sp2-build-assistant/references/edits.md)。
- [需求文档](../../docs/SP2AgentBuildAssistant-Requirements.md) 与 [可行性调研](../../docs/SP2AgentBuildAssistant-Feasibility.md)：后续需求和边界，不代表全部已实现。
- [本机历史实机记录目录](../tests/artifacts/)：原始结果与飞机快照，仅作当前开发证据，不作为公开发布包内容。

每次游戏或插件升级，应先执行 commands list、commands schema、designer status，核对命令契约与实际加载版本，再使用历史样例。

`runtimeRetention.expressionLifetime`补充表达式编译诊断：`installed`与已审核模块ID、模板数量/上限、命中/编译/回退/淘汰累计数。模板仅复用代码，每个返回函数独立绑定部件和状态数据；未知节点回退原生编译。计数用于定位长期重建开销，不代表所有表达式或所有内存路径已无泄漏。

通用属性的 `verification=representative_adapter_cases_only` 表示该适配器有代表场景原生对照，不表示当前类型和动态组合已经逐一认证。`outside_typed_write_matrix` 不属于这组写入验收。详细94字段索引在 `knowledge/native-adapter-evidence.json`；`editable-coverage.json`保留原目录快照的版本和分母，不冒充最新全目录认证。
