# 更新提示与更新方法（0.7.8）

`sp2model`只查询公开GitHub Release元数据、记录本地缓存和发出通知，不下载或执行更新包，不替换安装，不重启游戏，不读写craft。

```powershell
sp2model updates check
sp2model updates status
sp2model updates guide
sp2model updates check --force true
sp2model updates check --channel prerelease
```

`check`显式联网，默认正式版通道；`force`只越过成功缓存，不能越过服务端限流或失败退避。`status`和`guide`默认只读本地信息，不发现游戏、不联网、不创建目录。没有公开Release、404、断网或未检查都不等于“已是最新版”。正式版、SDK的aN后缀及已安装/已加载版本分别解释，不凭字符串大小比较。

如确实需要读取运行插件版本，显式选择实例：

```powershell
sp2model updates status --live --instance ID
sp2model updates guide --live --instance ID
```

`--live`只增加一次`capabilities`查询，不读取craft；未选择实例时的普通命令不因更新检查连接游戏。已有客户端的通知可复用已认证的发现描述符，其source与显式capabilities观测不同。安装器生成`installation.json`，仅当当前DLL的SHA256仍匹配该回执时，才认定已安装插件版本已核实。旧安装没有回执时明确unknown，不猜目录或把SDK版本当DLL版本。

Python公开接口：

```python
from sp2model import Runtime
runtime = Runtime()                     # 不连接游戏
result = runtime.updates.check()         # 显式HTTPS GET
status = runtime.updates.status()        # 本地缓存与组件证据
guide = runtime.updates.guide()          # 完整更新步骤
# runtime = Runtime(instance="明确实例ID")
# status = runtime.updates.status(live=True)
```

三个命令同样支持`Runtime.call("updates.check", {...})`等形式。通过`sp2model commands list`和`commands schema --command updates.check`发现输入契约。此版本没有安装、下载、应用更新命令。

## 自动检查与通知

正规安装的建造入口在使用已选原生客户端时启动独立、隐藏、无控制台的元数据worker；原工具调用不等待网络。检查默认每天一次，短调用首次可能只启动检查，后续调用读取缓存并提示。worker只用标准库，不发现游戏、不获取任何账号/实例token、不操作玩家profile；一次检查有总超时、响应大小和分页上限。没有安装回执的源码/旧安装不会默默启动worker，可用显式`updates check`。

命令host、`run/inspect/resume`脚本host及语义model host的成功和失败信封均可附加`notices`。通知保留原结果、请求ID、identity及错误语义，失败不能诱发原操作重放。提示带版本、Release链接、fresh/checkedAt与`guideCommand`；远端标题、Release正文和任意安装指令不进入提示。缓存过期或本次查询失败时，保留上次候选但明确未核实。

Agent收到通知后应先告诉玩家当前版本、目标版本及是否为过期缓存，再执行`sp2model updates guide`取得实际更新方法并解释给玩家。`tool_restart_required`表示已安装文件较新、运行插件仍旧；保存并等待玩家和其他Agent完成工作后再讨论正常退出重启。通知发出不证明Agent已转告，更不代表玩家已授权安装。

## 本地配置

安装根由`SP2MODEL_HOME`确定；未设置时使用`~/.sp2build`。可在该根的`updates.json`显式配置：

```json
{"repository":"EEEureka/sp2-build-assistant","channel":"stable","automatic":true,"intervalSeconds":86400,"timeoutSeconds":3}
```

仓库只能是GitHub的`owner/repo`，不接受任意服务器URL或认证信息。通道为`stable`或`prerelease`；周期3600至604800秒，超时0.5至10秒。`automatic:false`关闭后台调度，显式check仍可用。状态/说明命令不写配置。缓存按仓库/通道分开，使用原子文件及独占短租约避免并发刷新；错误与限流保留退避时间。

仅查询Release，不把普通tag当发布；按数值版本选择已扫描范围内最高兼容标签，不按返回顺序或创建时间猜。未知格式标签不作为版本依据；分页达到上限时不能认证已检查全部版本。只使用公开API，不从浏览器、环境或游戏提取GitHub凭证；私有仓库的404保持不可区分。

## 更新步骤与安装边界

`updates guide`输出当前安装根、经哈希核实的插件路径、备份位置、Release链接和可核实的包/哈希。先保存craft并等待其他Agent完成，退出目标游戏；备份旧DLL、SDK入口、skill及回执；按目标Release完整包自带安装器更新对应安装，再启动并通过`doctor --live --instance ID`核对实际加载。DLL没有热更新。发生问题时在游戏退出后从本次备份恢复成套文件/入口，不删除玩家项目或存档。

游戏目录下的本地工具和旧全局工具分开；更新一个安装不会授权迁移另一个，也不能猜测PATH指向。多个候选包或缺少哈希时不自动选包、不宣称已验签。当前guide不会执行步骤；跨游戏版本适用性以目标Release说明和安装器验证为准。
