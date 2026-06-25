"""上下文充实阶段 — 名字解析 + 记忆检索 + 别名扫描"""
from dataclasses import dataclass, field
from typing import Dict, List

from src.store import Store, Person
from src.parse import ParsedMsg


def _person_entry(person: Person, fallback_name: str) -> dict:
    """为一个人生成上下文条目，包含关系与风格。"""
    relations_str = ""
    if person.relations:
        parts = [f"{rid}:{label}" for rid, label in person.relations.items()]
        relations_str = ", ".join(parts)[:80]
    return {
        "name": person.mention_name or fallback_name,
        "facts": person.get_fact_strings(),
        "relations": relations_str,
        "style": person.speaking_style,
    }


@dataclass
class EnrichedCtx:
    parsed: ParsedMsg
    people: Dict[str, dict] = field(default_factory=dict)   # {wxid: {name, facts}}
    related_memories: List = field(default_factory=list)
    group_summary: str = ""
    group_topic: str = ""
    history: List = field(default_factory=list)              # ChatMsg 列表
    mentionable_names: List[str] = field(default_factory=list)


def enrich(parsed: ParsedMsg, store: Store, bot_names: List[str] = None) -> EnrichedCtx | None:
    """充实上下文。非@bot 消息返回 None（调用方仍需记录历史）。"""
    if not parsed.is_at_bot:
        return None
    if bot_names is None:
        bot_names = []

    group = store.get_group(parsed.room_id)
    people: Dict[str, dict] = {}

    def _is_bot(name: str) -> bool:
        return any(name == bn for bn in bot_names)

    # 解析显式 @ 的人
    for name in parsed.raw_mentions:
        if _is_bot(name):
            continue
        person, matched = store.resolve_name(name)
        if person and person.wxid != parsed.sender_wxid:
            people[person.wxid] = _person_entry(person, matched or name)

    # 扫描正文中的已知别名（使用 Store 公开方法）
    exclude = set(people.keys()) | {parsed.sender_wxid}
    alias_matches = store.scan_aliases_in_text(parsed.content, exclude_wxids=exclude, bot_names=bot_names)
    for wxid, (person, alias) in alias_matches.items():
        people[wxid] = _person_entry(person, alias)

    # 检索相关记忆
    keywords = list(parsed.raw_mentions) + list(people.keys())
    memories = store.search_memories(parsed.room_id, keywords, limit=3)

    # 可 mention 的名字列表（排除发送者自己）
    mentionable = []
    for wxid, info in people.items():
        name = info["name"]
        if name and name != parsed.sender_name:
            mentionable.append(name)

    return EnrichedCtx(
        parsed=parsed,
        people=people,
        related_memories=memories,
        group_summary=group.context,
        group_topic=group.topic,
        history=store.get_history(parsed.room_id, limit=10),
        mentionable_names=mentionable,
    )
