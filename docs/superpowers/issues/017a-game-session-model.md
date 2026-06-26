# Issue 17a: GameSession 数据模型 + 管理器

## Parent

PRD: #17 (`docs/superpowers/specs/2026-06-26-game-session-PRD.md`)

## What to build

新建 `src/game_session.py`，包含 GameSession dataclass 和 GameSessionManager。纯数据层，不碰 Pipeline。

### 端到端行为

1. GameSession 记录游戏名、开始时间、上次输入时间，支持超时检测
2. GameSessionManager 管理 room_id → GameSession 映射
3. 进入游戏模式（覆盖已有）
4. 退出游戏模式（返回被退出的 session）
5. 超时检查（>5 分钟自动退出）
6. 退出命令检测（"不玩了/退出/算了"）
7. 重掷命令检测（"再来一次/再掷一次"）
8. 生成猫娘风格退出公告

### 关键规则

- 一个群一个活跃游戏
- 内存存储，不持久化
- 无任何 Pipeline/LLM 依赖

## Acceptance criteria

- [ ] GameSession 创建/超时检测/触摸更新
- [ ] GameSessionManager CRUD（进入/退出/查询/超时）
- [ ] 退出/重掷关键词检测
- [ ] 退出公告格式包含游戏名和猫娘口癖
- [ ] 单元测试覆盖

## Blocked by

None — can start immediately
