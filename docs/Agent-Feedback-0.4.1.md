# S00 反馈修订：CLI / skill 0.4.1，DLL 仍为 0.4.0

日期：2026-10-02。DSH 在两件初始飞机上完成 S00 基线、三心与目录测试，协调端独立核查。此修订仅改 CLI 契约和 skill/说明；无需重启游戏。

- FB-023 成立：为 wing.control.add 添加四种合法 style 枚举、按 style 区分的 patch 字段及数值范围；shape.update.patch 增加机身、机翼、各控制面的命名结构；shape.schema.family 明确三个区分大小写的值。快捷调用与批次使用同一份 schema。额外说明机身不能使用机翼的 replaceSections。
- FB-024 描述缺失成立，但反馈中的“全部 guarded 写命令缺失”和改名 readOnlyCommands 的建议不准确：原字段本身包含 batch.apply、craft.undo、craft.rollback。现在输出 schema 与 skill 明确它是 bridge 命令标识清单，不是完整 CLI 清单；快捷写命令转译成 batch.apply。capabilities/designer.status 也不能简单归类为纯 CLI 本地命令。DSH 应保留原反馈并按核实结果修正措辞。
- Spoiler/SplitFlap 的原生实现存在于游戏代码，但目前无可创建的目录模板，工具也未开放 typed 写入。暂不把 BrakeFlap、AirBrake 或上偏副翼当作用户要求的原生扰流板。该能力在 S09 前进一步调研并单独验收，不阻塞 S01 机身建造。

新增 32 项形状输入契约检查（包括实际 S00 原生参数表的字段/范围一致性），原有 46 项 Python 检查及 105 项历史契约验证通过。此次未修改 DLL，不增加已加载游戏的运行时能力；S00 的三心实测只覆盖质量、无翼/无推进源、图像及未编辑比较，尚未覆盖有翼/有推进源的后续场景。

分阶段工作流见 [阶段方案](Staged-Aircraft-Build-Acceptance.md)。DSH 台账及原始证据位于 D:/codeSpace/sp2_craft_edit/staged-build/ 和其根目录 tool-feedback.md。

## S09 前置源码核查补充

存在名为 Spoiler 的类并不等于游戏已提供可完整使用的原生扰流板。当前 `Game/Assets/Scripts/Craft/Wings/ControlSurfaces/Spoiler.cs` 实现了上翼面网格、碰撞体和固定 50 度的运行时偏转；但没有覆写基类的 `TryPlaceOnWing` / `TryChangeRange`（基类会抛 NotImplementedException），也没有覆写 `SaveToXml` 保存其私有 hingePos/length，缺少现成的可创建目录模板。未找到这些行为的补全证据前，不能把它定性为“只缺工具入口”，更不能据此宣布扰流板功能已可用。后续需要分别验证可创建性、形状持久化、放置/调整以及气动作用；必要时作为插件扩展实现，并明确兼容性边界。
