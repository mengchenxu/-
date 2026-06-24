"""上下文充实阶段 — 名字解析 + 记忆检索 + 别名扫描"""
from dataclasses import dataclass, field
from typing import Dict, List

from src.store import Store
from src.parse import ParsedMsg


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
    if bot_names is None:
        bot_names = []
    group = store.get_group(parsed.room_id)
    if not parsed.is_at_bot:
        return None

    people: Dict[str, dict] = {}

    def _is_bot(name: str) -> bool:
        return any(name == bn for bn in bot_names)

    # 解析显式 @ 的人
    for name in parsed.raw_mentions:
        if _is_bot(name):
            continue
        person, matched = store.resolve_name(name)
        if person and person.wxid != parsed.sender_wxid:
            people[person.wxid] = {
                "name": person.mention_name or matched or name,
                "facts": person.get_fact_strings(),
            }

    # 扫描正文中的已知别名
    for wxid, person in store._people.items():
        if wxid in people or wxid == parsed.sender_wxid:
            continue
        if _is_bot(person.mention_name):
            continue
        for alias in person.aliases:
            if alias and len(alias) >= 2 and alias in parsed.content:
                if _is_bot(alias):
                    continue
                people[wxid] = {
                    "name": person.mention_name or alias,
                    "facts": person.get_fact_strings(),
                }
                break

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
