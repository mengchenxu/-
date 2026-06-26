# PRD: 主动发言 + 游戏意图检测

**日期**: 2026-06-26
**标签**: `ready-for-agent`

---

## Problem Statement

当前 bot（猫娘）只能被动等待 @ 触发，无法在冷场时活跃气氛、不能在定时推话题、也不知道主人想玩游戏。群互动完全靠群友主动，bot 像个工具而不是群成员。

## Solution

分两步：先上线主动发言三层（冷场/定时/热点）+ 游戏意图检测，游戏具体内容后做。

## User Stories

1. 作为群成员，群超过 30 分钟没人说话时，bot 会基于群记忆自动抛话题暖场
2. 作为群成员，每天固定时段 bot 会发早安/午后/晚间问候
3. 作为群成员，bot 会分享热点话题（联网搜索），以猫娘语气转述
4. 作为群成员，我发"好无聊啊有没有什么好玩的"时，bot 能判断我想玩游戏并列出游戏
5. 作为群成员，bot 不会在对话中提到游戏时误判——"昨天打了游戏"不会触发游戏列表
6. 作为群主，主动发言有防刷屏：每日上限、最小间隔、静音时段
7. 作为开发者，主动发言不依赖旧的 `proactive.py` 文件，从零重写适配管道架构

## Implementation Decisions

1. **Seam 范围**: 新增 `src/proactive.py`（ProactiveSpeaker 类），改 Pipeline（集成后台线程 + 游戏意图检测），改 Config（已有 proactive 段可复用）
2. **冷场检测**: Pipeline 记录每个群 `last_msg_at`（已有），ProactiveSpeaker 每分钟检查是否超过 `cold_silence_minutes`（默认 30min）
3. **定时推送**: 从 config 的 `schedule_times` 读取时段，ProactiveSpeaker 在匹配时段时触发
4. **热点分享**: 从 `web_search.py` 搜索热点 → LLM 改写为猫娘风格 → 主动发送
5. **话题生成**: 冷场和定时场景下，LLM 基于 `Group.context` + `top_words` + `top_emojis` 生成话题
6. **游戏意图检测（B+A）**:
   - B：Pipeline 在非 @ 消息中扫关键词（"游戏"/"无聊"/"玩"/"来点"），命中进入 A
   - A：调 LLM 做轻量意图分类（temperature 0.1，2 tokens），判断"想玩" vs "不想玩"
   - 想玩 → 回复游戏列表，带上所有已注册的斜杠命令
7. **防刷屏**:
   - 每日上限: `max_per_day`（默认 10）
   - 最小间隔: `min_interval_minutes`（默认 30min）
   - 静音时段: `quiet_hours`（默认 02:00-06:00）
8. **Config 已有段**（可直接复用）:
   ```
   proactive:
     enabled: true
     cold_silence_minutes: 30
     schedule_times: ["08:30", "12:30", "18:00", "22:00"]
     hot_topic_interval_hours: 4
     max_per_day: 10
     min_interval_minutes: 30
     quiet_hours: ["02:00", "06:00"]
   ```
   新加: `game_keywords: ["游戏", "无聊", "玩", "来点"]` + `game_intent_enabled: true`

## Testing Decisions

- **什么是好测试**: Mock LLM 返回意图分类结果，验证 Pipeline 正确路由到游戏列表/忽略
- **测试文件**: `test_proactive.py`（新建）— ProactiveSpeaker 触发逻辑；`test_pipeline.py`（新建，从 test_store.py 拆分）— 游戏意图路由
- **不测试**: 真实 LLM 意图分类质量、UIA 发送、定时器精度

## Out of Scope

- 游戏具体实现（/骰子 /接龙 等 — 下一期）
- 事件触发（新成员入群欢迎等）
- Web 控制面板

## Further Notes

- ProactiveSpeaker 作为后台线程运行，每分钟检查一次所有群
- 游戏意图检测的 LLM 调用使用极低温度 + 极短 max_tokens = 几乎零成本
- `to-issues` 下一步拆成 2 个 issue
