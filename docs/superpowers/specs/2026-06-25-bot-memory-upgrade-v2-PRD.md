# PRD: 记忆升级 V2

**日期**: 2026-06-25
**标签**: `ready-for-agent`
**依赖**: 一期重构已完成（六阶段管道运行中）

---

## Problem Statement

当前 bot 的记忆能力有限：`store.json` 中的 Person 和 GroupMemory 数据结构缺少关系追踪和风格字段，最关键的短板是——**LLM 不会主动从群聊中提取值得记住的东西**。`/remember` 指令能用，但没人手动喂它；情景记忆（`search_memories`）的检索能力已经就绪，但没有数据被喂进去。结果就是 bot 记不住几天前的事，也学不会群友之间的关系和说话风格。

## Solution

给 Store 数据模型补上缺失字段，在 Pipeline 中加入"每 N 条消息让 LLM 扫一遍最近对话、自动提取记忆"的流程。不改 Parse / Prompt / LLM / Decode / Send 五个阶段，只动 Store 和 Pipeline 两个 seam。

## User Stories

1. 作为群成员，bot 会在聊天中自动记住群友说过的重要事情（"贯一下周去日本"），不需要我手动 `/remember`
2. 作为群成员，当有人再次提到相关话题时，bot 能自然提及之前的记忆（"上次贯一不是说要去日本吗"）
3. 作为群成员，bot 能记住群友之间的关系（"子南和贯一是同事"），聊天时用到
4. 作为群成员，bot 能识别并记住群友的口头禅和说话风格，回复越来越像自己人
5. 作为群成员，bot 不会把玩笑话当真——只提取明确的事实和决定，梗和段子另存
6. 作为群成员，超过 30 天没人提起的低价值记忆会被自动清理，bot 不会翻旧账
7. 作为群主，bot 提取记忆的过程是静默的——不会在群里发"我学会了xxx"
8. 作为开发者，所有记忆相关的数据都在 `store.json` 中，不产生新的数据文件
9. 作为开发者，记忆提取是一个纯函数调用（消息列表 → Store mutations），可以独立测试

## Implementation Decisions

1. **Seam 范围**: 只改 Store 和 Pipeline，Parse / Prompt / LLM / Decode / Send 不动
2. **数据合并**: 废弃 `data/group_memories.json` 和 `data/users.json`，所有记忆数据统一进 `store.json`。旧 `src/group_memory.py` 和 `src/user_memory.py` 删除
3. **Person 新增字段**: `relations`（Dict[str, str]，记录与其他人的关系）、`speaking_style`（str，LLM 生成的风格描述）、`catchphrases` 已在 Person 中，不动
4. **GroupMemory 新增字段**: `participants`（List[str]，涉及的群友名字），其余字段已齐全
5. **记忆提取触发**: Pipeline 每 10 条消息触发一次 `_extract_memories()`，将最近 15 条消息发给 LLM，让 LLM 返回结构化记忆项，写入 Store
6. **记忆分类**: event（事件）、decision（决定）、fact（事实）、joke（梗/段子）、topic_change（话题转折），LLM 分类
7. **重要度**: 1-5 分，LLM 评判。≥3 的长期保留，≤2 的 30 天后自动清理
8. **事实提取**: 从记忆中自动提取 Person facts（与 `/remember` 共用 `add_fact` 路径，source=`llm_extract`，confidence=0.6）
9. **搜索不变**: `web_search.py` 已集成在 LLM 阶段，不动
10. **存量数据**: 如 `data/group_memories.json` 或 `data/users.json` 仍存在，自动迁移进 Store，旧文件加 `.bak`

## Testing Decisions

- **什么是好测试**: 只测外部行为（输入 → 输出/副作用），不测内部实现。测试读起来像规格说明
- **Seam**: 两个 seam → 两个测试文件。`test_store.py` 已有 28 测试，追加；`test_pipeline.py` 新建
- **测试内容**:
  - Store: `find_person_by_name` 匹配 relations 中的别名；Person 新增字段读写；GroupMemory 的 participants 字段
  - Pipeline: 给一组消息 → LLM 返回结构化记忆 → Store 中出现了对应记忆（mock LLM）
- **不测试**: LLM 实际输出质量（需要真 API）、UIA 发送

## Out of Scope

- 不换 LLM 提供商（仍用 DeepSeek）
- 不改 prompt 结构（四段式不变）
- 不加新的数据文件（全进 store.json）
- 主动发言系统（二期 B）
- 风格学习系统（二期 C）
- Web 控制面板

## Further Notes

- 记忆提取的 LLM prompt 放在 `src/prompt.py` 中，与系统 prompt 区分——新增一个 `build_extraction_prompt()` 函数
- LLM 提取用的是低温度（0.3），与回复用的高温度（0.85）区分
- 记忆去重：相同内容不重复存储，LLM 提取时检查是否与已有记忆相似
- `to-issues` 下一步拆成 2-3 个独立 issue
