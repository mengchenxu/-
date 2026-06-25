# Issue 9: 记忆自动提取 + 上下文引用

## What to build

Pipeline 中加入 LLM 自动从群聊中提取记忆的流程，Enrich 阶段注入 relations 和 speaking_style。

### 端到端行为

1. 每 10 条消息触发一次 `_extract_memories()`（低温度 0.3，与回复用的 0.85 区分）
2. LLM 扫最近 15 条消息 → 返回结构化记忆项（content, category, keywords, participants, importance）
3. 记忆写入 Store（group.memories），自动去重
4. 从记忆中提取 Person facts（source=llm_extract, confidence=0.6）
5. Enrich 阶段注入 Person.relations 和 Person.speaking_style 到上下文
6. 静默提取——不在群里发"我学会了xxx"

### 关键规则

- 提取 prompt 放在 `src/prompt.py`，新函数 `build_extraction_prompt()`
- 温度 0.3，max_tokens 512
- 每次最多提取 3 条记忆
- 每次最多更新 2 个 Person facts
- 记忆去重：相同 content 不重复存储
- LLM 返回结构化 JSON，解析失败不崩溃

## Acceptance criteria

- [ ] `build_extraction_prompt()` 函数存在且包含四部分：系统指令 + 判断标准 + 最近消息 + 输出格式
- [ ] Pipeline 每 10 条消息触发一次提取
- [ ] 提取的记忆正确写入 Store（含 participants）
- [ ] 从记忆中提取 Person facts（source=llm_extract, confidence=0.6）
- [ ] Enrich 阶段的 people 包含 relations 和 speaking_style
- [ ] 提取失败不崩溃（JSON 解析失败、API 错误均有保护）
- [ ] Mock LLM 测试覆盖记忆提取全链路

## Blocked by

- #8 Store 数据模型升级 + 旧代码清理

## Parent

PRD: `docs/superpowers/specs/2026-06-25-bot-memory-upgrade-v2-PRD.md`
