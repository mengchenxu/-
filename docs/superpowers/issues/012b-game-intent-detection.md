# Issue 12b: 游戏意图检测

## Parent

PRD: #14 (`docs/superpowers/specs/2026-06-26-proactive-speaker-PRD.md`)

## What to build

Pipeline 中新增游戏意图检测：非 @ 消息命中关键词 → 调轻量 LLM 做意图分类 → 想玩就回复游戏列表。

### 端到端行为

1. 非 @ 消息经过 Parse 后，Pipeline 扫描是否包含游戏关键词（"游戏"/"无聊"/"玩"/"来点"）
2. 命中关键词 → 调 LLM 做轻量意图分类（temperature 0.1, max_tokens 2），判断"想玩"或"不想玩"
3. "想玩" → 回复游戏列表文本，包含所有已注册的斜杠命令（/骰子 等）
4. "不想玩" → 忽略，正常记录历史
5. 游戏列表文本为硬编码，不调主 LLM

### 关键规则

- 只在非 @ 消息触发（@ 消息走正常 LLM 回复）
- 意图分类 LLM 调用极轻量（几乎零成本）
- 游戏列表存在一个地方统一维护，方便以后扩展
- "昨天打了游戏"这类不会误触发——LLM 意图分类会判"不想玩"

## Acceptance criteria

- [ ] 非 @ 消息含关键词时触发意图检测
- [ ] LLM 意图分类正确路由（想玩 → 游戏列表，不想玩 → 忽略）
- [ ] 游戏列表包含已注册的斜杠命令
- [ ] Mock LLM 测试覆盖意图分类全链路
- [ ] 命中关键词但不命中意图时不触发

## Blocked by

None — can start immediately（与 12a 独立）
