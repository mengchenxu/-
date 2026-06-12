"""
上下文构建器 — 为 LLM 构建带用户归属和记忆的对话上下文。
"""
import logging

from src.user_memory import UserMemoryStore
from src.bot_core import GroupSession
from src.weflow_client import WeFlowMessage

logger = logging.getLogger(__name__)


def build_llm_context(
    msg: WeFlowMessage,
    session: GroupSession,
    user_memory: UserMemoryStore,
    bot_nicknames: list,
) -> str:
    """
    构建注入到 LLM user message 中的上下文。

    返回一段结构化文本，包含：
    1. 当前发言者是谁 + 已知信息
    2. 如果 @了其他人，附上被 @者的信息
    3. 群内其他已知成员摘要（精简）
    """
    parts = []

    # ---- 1. 当前发言者 ----
    speaker_name = msg.display_name or msg.sender_name
    speaker_wxid = msg.sender_name  # WeFlow 中 sender_name 就是 wxid
    speaker_ctx = user_memory.get_user_context(speaker_wxid)
    if speaker_ctx:
        parts.append(f"当前发言者 — {speaker_ctx}")
    else:
        parts.append(f"当前发言者 — {speaker_name}")

    # ---- 2. 被 @ 的人（非 bot 的其他人） ----
    mentioned_others = [m for m in msg.mentions if m not in bot_nicknames]
    if mentioned_others:
        mentioned_info = []
        for name in mentioned_others:
            profile = user_memory.find_by_name(name)
            if profile and profile.wxid != speaker_wxid:
                ctx = profile.get_context_summary()
                if ctx:
                    mentioned_info.append(f"  @{name} — {ctx}")
                else:
                    mentioned_info.append(f"  @{name}")
            else:
                mentioned_info.append(f"  @{name}")
        if mentioned_info:
            parts.append("消息中 @了:\n" + "\n".join(mentioned_info))

    # ---- 3. 群内活跃成员摘要（精简，只显示有信息的） ----
    if session.active_users:
        # 过滤掉当前发言者（已经在上方展示了）
        other_users = session.active_users - {speaker_wxid}
        if other_users:
            others_ctx = user_memory.get_users_context(list(other_users))
            if others_ctx:
                parts.append(others_ctx)

    # ---- 4. 群级别上下文摘要 ----
    if session.group_context:
        parts.append(f"群聊背景: {session.group_context}")

    # ---- 组装 ----
    if parts:
        return "[上下文]\n" + "\n\n".join(parts) + "\n\n[消息内容]\n" + msg.content
    else:
        return msg.content


def extract_facts_from_reply(reply: str, speaker_wxid: str, user_memory: UserMemoryStore) -> str:
    """
    从 LLM 回复中提取 /remember 指令并更新用户记忆。
    支持的指令格式：
      /remember @某人 事实: 值
      /remember 事实: 值  （默认记住当前说话者）

    这些指令会在发送前从回复中剥离。
    """
    import re

    # 匹配 /remember @name key: value 或 /remember key: value
    pattern = r'/remember\s+(?:@(\S+)\s+)?(.+?)\s*:\s*(.+)'
    facts: list[tuple[str, str, str]] = []

    def _process(m: re.Match) -> str:
        at_name = (m.group(1) or "").strip()
        key = m.group(2).strip()
        value = m.group(3).strip()
        if key and value:
            facts.append((at_name, key, value))
        return ""  # 从回复中移除

    clean_reply = re.sub(pattern, _process, reply)

    # 应用提取到的事实
    for at_name, key, value in facts:
        if at_name:
            target = user_memory.find_by_name(at_name)
            if target:
                user_memory.update_fact(target.wxid, key, value)
                logger.info("LLM 记住了 @%s: %s = %s", at_name, key, value)
            else:
                logger.debug("未找到用户 @%s，跳过记忆", at_name)
        else:
            user_memory.update_fact(speaker_wxid, key, value)
            logger.info("LLM 记住了当前用户: %s = %s", key, value)

    # 清理多余空行
    clean_reply = re.sub(r'\n{3,}', '\n\n', clean_reply).strip()
    return clean_reply
