# Issue 17b: Pipeline 集成 + 骰子游戏模式

## Parent

PRD: #17 (`docs/superpowers/specs/2026-06-26-game-session-PRD.md`)

## What to build

Pipeline 集成 GameSessionManager，实现游戏模式下的命令路由和退出逻辑。

### 端到端行为

1. @bot 发 `/骰子` → 进入骰子游戏模式，掷骰子
2. 游戏模式中，非 @ 消息被游戏处理器拦截（不调 LLM）
3. "再来一次" → 重掷骰子
4. "不玩了/退出" → 退出游戏模式，猫娘公告
5. 5 分钟无输入 → 自动退出，猫娘公告
6. 退出后恢复正常 @ 触发模式
7. @bot 消息在游戏模式中正常处理（可 @bot 选其他游戏覆盖当前）

### 关键规则

- GameSessionManager 存在 Pipeline 内存中
- 游戏模式路由在 Parse 之后、Enrich 之前
- 退出公告通过 send() 发送，不调 LLM
- 超时检查在每次 handle() 入口处执行

## Acceptance criteria

- [ ] @bot + /骰子 → 进入游戏模式 + 掷骰子
- [ ] 游戏模式中"再来一次" → 重掷（不 @bot）
- [ ] 游戏模式中"不玩了" → 退出 + 猫娘公告
- [ ] 5 分钟超时 → 自动退出
- [ ] 退出后非 @ 消息走正常管道
- [ ] Mock 测试覆盖游戏模式全链路

## Blocked by

- #17a GameSession 数据模型 + 管理器
