# Issue 8: Store 数据模型升级 + 旧代码清理

## What to build

Store 数据模型补字段，删旧 `group_memory.py` 和 `user_memory.py`，旧 JSON 迁移。

### 端到端行为

1. Person 新增 `relations`（与其他人的关系）和 `speaking_style`（说话风格描述）
2. GroupMemory 新增 `participants`（涉及的群友名字）
3. Store JSON save/load 覆盖新字段
4. 如 `data/group_memories.json` 或 `data/users.json` 存在 → 迁移进 store.json → 旧文件加 `.bak`
5. 删 `src/group_memory.py`、`src/user_memory.py`、`src/context_builder.py`（旧架构，未接入管道）

## Acceptance criteria

- [ ] Person 有 `relations` 和 `speaking_style` 字段
- [ ] GroupMemory 有 `participants` 字段
- [ ] Store save/load 覆盖新字段（通过 roundtrip 测试验证）
- [ ] 旧 JSON 迁移：数据正确进入 Store，旧文件改名 `.bak`
- [ ] 旧代码文件已删除，无 import 引用残留
- [ ] 所有已有测试继续通过

## Blocked by

None — can start immediately

## Parent

PRD: `docs/superpowers/specs/2026-06-25-bot-memory-upgrade-v2-PRD.md`
