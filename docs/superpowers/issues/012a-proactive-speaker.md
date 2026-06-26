# Issue 12a: ProactiveSpeaker — 冷场/定时/热点主动发言

## Parent

PRD: #14 (`docs/superpowers/specs/2026-06-26-proactive-speaker-PRD.md`)

## What to build

新增 ProactiveSpeaker 类作为后台线程，每分钟检查一次所有活跃群，在冷场/定时/热点三种场景下自动发言。

### 端到端行为

1. 冷场检测：群 `last_msg_at` 超过 30 分钟无人说话 → LLM 基于 `Group.context` + `top_words` + `top_emojis` 生成话题 → 发送
2. 定时推送：当前时间匹配 config 中的 `schedule_times` → LLM 生成问候 → 发送
3. 热点分享：距上次热点检查超过 `hot_topic_interval_hours` → `web_search` 搜热点 → LLM 改写成猫娘风格 → 发送
4. 防刷屏：每日上限、最小间隔、静音时段（复用已有 proactive config）

### 关键规则

- 后台线程，不阻塞主 Pipeline
- LLM 生成话题时带群上下文（用已有 `summarize_context` 类似逻辑）
- 发送复用已有 `send.py`（需要构造 DecodedReply）
- 主动发言不计入冷却，但有自己的间隔控制

## Acceptance criteria

- [ ] ProactiveSpeaker 类存在，后台线程每分钟检查
- [ ] 冷场超过阈值时自动发言
- [ ] 定时匹配时自动发言
- [ ] 热点定期分享
- [ ] 防刷屏规则生效（上限/间隔/静音）
- [ ] Mock LLM + Mock 时间测试覆盖触达逻辑

## Blocked by

None — can start immediately
