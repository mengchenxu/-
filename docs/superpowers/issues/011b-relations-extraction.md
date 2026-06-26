# Issue 11b: 人际关系自动提取

## What to build

在记忆提取流程中，LLM 同时提取群友之间的关系（同事/同学/朋友等），写入 `Person.relations`。

### 端到端行为

1. `build_extraction_prompt` 的 JSON schema 中加 `relations` 字段
2. LLM 在提取记忆时可选择性返回关系
3. `_check_extract` 将 relations 双向写入（A → B 和 B → A）

### 关键规则

- relations 是可选的——没有值得记的关系就跳过
- 关系双向写入：A 是 B 的同事 → B 也是 A 的同事
- 只有确定的关系才写入（不推测）

## Acceptance criteria

- [ ] `build_extraction_prompt` 的 user prompt 包含 `relations` 字段说明
- [ ] `_check_extract` 将 relations 写入 `Person.relations`
- [ ] Mock LLM 测试覆盖 relations 提取全链路
- [ ] 关系双向存储

## Blocked by

None — can start immediately（与 11a 独立）

## Parent

PRD: `docs/superpowers/specs/2026-06-25-style-learning-PRD.md`
