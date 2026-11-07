# Funky Trees 按需知识

工具 0.7.7 的离线知识对应游戏 **0.7.9.104 / Steam build 25840865 / XML26**。查询只读派生资料，不需要游戏进程，不编译或执行表达式。来源版本、Game.dll 哈希、资料哈希、覆盖和 unknown 会随结果返回。详细接口与分页见 `knowledge.status` 和工具发现。

```python
from sp2model import Runtime

runtime = Runtime()
runtime.call("knowledge.search", {"collection": "functions", "query": "PID"})
runtime.call("knowledge.get", {"collection": "functions", "id": "PID"})
runtime.call("knowledge.get", {"collection": "rules", "id": "B05"})
runtime.call("knowledge.search", {"collection": "inputs", "query": "InputController"})
runtime.call("knowledge.get", {"collection": "outputs", "id": "HeliMainRotorScript.RotorRPM"})
runtime.call("knowledge.export", {"collection": "variables", "limit": 100})
```

先查目标输入入口的 `expectedType`、`scope` 与规则，再查函数或变量详情。输入 UI 的 `AllowFunkyInput` 标记不保证字段真能执行 FT：`DetacherData._direction` 是枚举，`PosedGripData._aircraftControl` 是原生控制绑定名。输出记录的 `outputId` 是属性名，不能用显示名代替；必须通过目标变量绑定才能供普通 FT 读取。`B05` 包含“主旋翼输出 → RotorRPM → Setter → 另一控制器”的完整配置与手动旁路例子，以及118个内置part实例的默认输入/输出绑定。

`partTypes` 来自已核对的Script/Data类型关联和部件字段映射。72条输入与53条输出可关联当前部件目录；其余为通用载具入口、旧类型或没有确认映射的声明，继续保留并标记 `partTypeMappingStatus`。例如旧 `CarEngineScript` 不能仅凭名称映射到当前 `JCarEngine`。默认控制器关联不是当前载具实例值，也不表示该部件每个入口都使用所有控制器。

| 集合 | 本版覆盖 | 适用说明 |
| --- | ---: | --- |
| functions | 35 | 31普通函数、4状态函数；精确名称 `PID` 大小写敏感 |
| constants | 4 | 当前真实值，不纠正游戏实现 |
| variables | 55 | 53载具context项（含默认用户变量RotorRPM）及2部件局部项 |
| rules | 21 | 原始S/T/L/B/I标识；语法、类型、生命周期、绑定与调度 |
| inputs | 88 | 22 UI候选与66调用/声明位置；含非FT与无部件context入口 |
| outputs | 60 | 全部源码声明，逐项含绑定、Activator、优先级和时序 |
| examples | 16 | 正例、负例与区别常见语言的例子；均未编译/求值 |
| mfd | 75 | 7类代理显式公开成员；可编译性未验证 |
| unknowns | 8 | 原生数学边界、调度、状态恢复、命名、MFD、单位、资产域和运行验证 |

几个容易用错的当前行为：`false` 转float为 **-1**；float转bool要求 **大于0**；常量 `e` 当前为 **0**；相等是单个 `=`；`* /` 高于 `%`，而 `& |` 同级左结合。状态函数每次实际调用才推进，短路可跳过调用；每个调用token有独立状态，重新编译会重新建立状态。普通 `Time` 从载具初始化起算，MFD `craft.Time` 从关卡加载起算。历史官方帮助的五类差异保留在对应详情及发布资料的 `officialHelpComparison`。

`A_NATIVE_CONTEXT` 表示冻结审计中的只读context元数据对照，`B_SOURCE` 表示源码证据，`C_*` 表示静态推导或外部函数体不可用，`UNKNOWN` 表示未闭合。它们均不等于运行验收。每个源码引用仅含以Game为根的相对路径、行号、文件SHA256和等级。发布包不含反编译函数体、原生私有快照、玩家子装配或存档。

先生成同版本 `knowledge/v077/parts.json`，再生成FT知识。显式提供审计文件；生成器只读输入，输入SHA变化会拒绝沿用旧策展说明；`--parts` 可指定部件资料位置：

```powershell
python tools/build_funky_knowledge_077.py --inventory <审计目录>/funky-trees-index.json
python tools/build_funky_knowledge_077.py --inventory <审计目录>/funky-trees-index.json --check
```

当前未知项继续保留。函数表、示例或MFD成员可被检索，不代表控制闭环、飞行操控、多人同步或状态跨存档恢复已经通过验证。

