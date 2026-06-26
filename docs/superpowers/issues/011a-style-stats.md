# Issue 11a: 表情/高频词实时统计 + 风格上下文注入

## What to build

实时统计群聊中的 emoji 和词频，注入到 prompt 上下文。Store 加 `top_emojis`/`top_words`，Enrich/Prompt/Config 加风格段。

### 端到端行为

1. 每条消息进入 Pipeline 时，`Store.track_style()` 实时统计 emoji 和词频
2. 每 10 条消息更新 `Group.top_emojis`（top-5）和 `Group.top_words`（top-10）
3. Enrich 阶段组装 `group_style` 字符串（emoji + 高频词 + 成员风格）
4. Prompt 在 `[群聊摘要]` 后加 `[群内风格]` 段
5. Config 系统指令加风格适应说明

### 关键规则

- emoji 统计用正则，不需要 LLM
- 词频统计 CJK 双字词 + 拉丁词（≥3 字母）
- 计数缓存 `_emoji_counts`/`_word_counts` 不序列化到 JSON
- top-N 每 10 条刷新一次

## Acceptance criteria

- [ ] Group 有 `top_emojis` 和 `top_words` 字段，save/load 覆盖
- [ ] `track_style()` 正确统计 emoji 和词频
- [ ] EnrichedCtx.group_style 包含表情 + 高频词 + 成员风格
- [ ] Prompt 用户消息包含 `[群内风格]` 段
- [ ] Config 系统指令包含"风格适应"说明
- [ ] 测试覆盖

## Blocked by

None — can start immediately

## Parent

PRD: `docs/superpowers/specs/2026-06-25-style-learning-PRD.md`
