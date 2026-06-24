"""Prompt 组装阶段 — 四段式 system + 摘要 + 历史 + 当前消息"""
from typing import Dict, List

from src.enrich import EnrichedCtx


def build_prompt(enriched: EnrichedCtx, system_prompt: str) -> List[Dict[str, str]]:
    """构建 LLM 消息列表。返回 [{"role": "system", "content": ...},
    {"role": "user", "content": ...}]。"""

    messages = [{"role": "system", "content": system_prompt}]

    # 用户消息：四段组装
    sections = []

    sender = enriched.parsed.sender_name or "未知"

    # 1. 群聊摘要
    if enriched.group_summary:
        sections.append(f"[群聊摘要] {enriched.group_summary}")

    # 2. 群聊记录（最多 10 条）
    if enriched.history:
        lines = []
        for m in enriched.history[-10:]:
            name = m.sender_name or "未知"
            role_label = "" if m.role == "assistant" else f"{name}: "
            lines.append(f"{role_label}{m.content[:200]}")
        sections.append("[群聊记录]\n" + "\n".join(lines))

    # 3. 当前消息
    sections.append(f"[当前消息]\n@{sender}: {enriched.parsed.content}")

    user_content = "\n\n".join(sections)
    messages.append({"role": "user", "content": user_content})

    return messages
