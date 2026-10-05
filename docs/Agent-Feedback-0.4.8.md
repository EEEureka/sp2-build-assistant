# S06 输入控制字段修复（0.4.8）

日期：2026-10-02。本版更新 CLI、skill 和 DLL。后续用户已重启加载 0.4.8，并授权 Codex 直接验收：S06 输入绑定、合法/非法表达式、反向映射、对称配置和整批恢复通过，FB-039 已解决。完整证据见 [直接建造验收与 0.4.9](Agent-Feedback-0.4.9.md)。以下保留首次部署时的诊断与验收计划。

## 确认的问题

S06 添加左右主翼外段控制面 #15、#16 后，使用正确的 `InputController.State` 路径将 input 改为 Aileron，被 0.4.6 拒绝为 `unsupported_property: No native metadata for attribute input`。失败批次恢复到相同 revision/fingerprint；独立几何测试和 20→18→20 对称同步通过，最终 16 件 / 15 连接，两个新控制面仍是 Pitch。S06 因此尚未通过。

FB-039 成立：原生 InputControllerData.GenerateStateXml / RestoreFromState 支持 input、activationGroup、invert、min、max、zeroOnDeactivate，但 BuildOverloadMetadata 只声明 invertType。通用写入器仅依据该元数据，导致游戏 UI 可配置的输入字段被错误阻挡。实际复现来自 StandardFlap 模板 tpl-923fb3378019afb3；没有实测其他风格的默认输入，不能推广为所有控制面都默认 Pitch。元数据缺少上述字段，并非整个 InputController.State 元数据为空。

## 修改与调用

为原生 InputController.State 增加严格字段白名单，沿用 `part.update` 和现有事务恢复。无需新增独立的输入编辑命令。支持单个或带 `[0]`、`[1]` 下标的控制器节点；未知字段仍拒绝。目录返回 `parts[].toolEditableExtensions`，包括当前飞机未使用的模板；status 返回 `data.inputControllerEditing`，明确这些字段来自插件对原生序列化代码的补充，而非伪装成游戏元数据。

```json
{"kind":"part.update","partId":15,"changes":[
  {"path":"InputController.State","attribute":"input","value":"Aileron"},
  {"path":"InputController.State","attribute":"invert","value":false}
]}
```

将 operation 放入带 requestId、craftSessionId、expectedRevision 的 batch，通过 `sp2build batch apply --input 文件.json` 调用。也可在同一批次 wing.control.add 后，使用其 temporaryId 配置输入。wing.control.add 的形状 patch 不新增 input 字段。

| 字段 | 验证与含义 |
| --- | --- |
| input | 非空字符串，原生轴 ID 或输入表达式；以游戏 GetAxisGetter 在部件上下文中解析，保留 Aileron / WingFlipped 的专用语义 |
| activationGroup | 整数字符串 0–8（0 常开）或布尔表达式；拒绝越界数字及小数写法 |
| invert、zeroOnDeactivate | JSON 布尔或规范 true/false 字符串 |
| min、max | 有限 float 范围值；允许 min > max 的反向映射，不自动重排 |
| invertType | Axis 或 Output |

input / activationGroup 仅在本次被修改时编译，不求值遥测，也不对其他零件的旧输入追加全局校验。非法输入进入现有失败恢复路径。null/删除字段拒绝，要求显式值。native Aileron 按所属翼 flipped 决定 Roll 符号，不能因为镜像就再给一侧加 invert；普通 Roll 无此逻辑。设计器输入配置验证不等于飞行操纵效能验证。

## 证据与验收边界

- S06 现有证据独立复核 60/60：16 件完整连通、原件变换/材料/对称组保留、两侧面板挂点/形状/碰撞射线、同步参数往返、三心重算、失败恢复和实际读图。报告 `tests/artifacts/staged-build/S06-review/independent-review.json` 明确阶段仍待输入修复。
- 构建通过；243 项离线回归（新增输入字段验证 28 项）、105 项通用契约、32 项形状契约通过；skill 校验通过。这些结果尚未验证新 DLL 在游戏中的输入表达式解析与回读。
- 本轮末尾飞机保留 session 482adc5f4cbd444fba54ab6aa383e4e8 / rev19，fingerprint 4f5b6be73a8a6ae03018dd8b7e6d9e5a41286b3cb2a6367604a0542f82c900f5。重启保存可能原生居中；下一轮须重新读取身份、检查点和几何，不能沿用旧会话检查点。

加载 0.4.8 后先建立新检查点，再测试 Aileron、带 Aileron 的合法表达式、布尔激活表达式、映射/反转字段、非法表达式和非法值的整批恢复，以及未放置模板的字段发现。最终将左右 #15/#16 配为 Aileron 并回读，检查几何和对称关系保留；S06 通过后进入 S07 内侧襟翼。未试飞，不输出稳定性或控制效能结论。
