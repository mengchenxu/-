"""
Bot 核心 — 消息路由、命令系统、多群会话隔离、用户记忆集成。
"""
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, Set

from src.weflow_client import WeFlowMessage
from src.config_loader import AppConfig

logger = logging.getLogger(__name__)


# 单条对话记录（增强版 — 带发送者信息）
@dataclass
class ChatMessage:
    role: str              # "user" | "assistant" | "system"
    content: str
    sender_name: str = ""  # 谁说的（user 消息时有值，显示名）
    sender_wxid: str = ""  # 发送者 wxid
    timestamp: float = 0.0 # 消息时间


# 每个群的会话上下文
@dataclass
class GroupSession:
    group_id: str
    history: deque = field(default_factory=lambda: deque(maxlen=20))  # deque[ChatMessage]
    last_reply_at: float = 0.0          # 上次回复时间戳（用于冷却）
    active_users: Set[str] = field(default_factory=set)  # 本群活跃用户 wxid 集合
    group_context: str = ""             # 群级别上下文摘要
    message_count: int = 0              # 本群已处理消息数（用于触发摘要）


class BotCore:
    """
    Bot 核心逻辑：
    1. 消息过滤 — 只处理群聊中 @bot 的消息
    2. 命令解析 — /help /reset /status /whois /memory
    3. 多群会话隔离 — 每个群独立维护对话历史
    4. 用户追踪 — 记录群内活跃用户
    """

    def __init__(self, config: AppConfig, weflow_client, user_memory=None):
        self.config = config
        self.client = weflow_client
        self.bot_name = config.bot.name
        self.cooldown = config.bot.reply_cooldown_seconds
        self.user_memory = user_memory  # UserMemoryStore，由 main.py 注入
        # 群会话: {group_id: GroupSession}
        self._sessions: Dict[str, GroupSession] = {}

    # ----------------------------------------------------------------
    # 入口：处理一条消息
    # ----------------------------------------------------------------
    def handle(self, msg: WeFlowMessage) -> Optional[Tuple[str, str]]:
        """
        处理消息。返回 (reply_text, roomid) 或 None。
        None 表示需要 LLM 处理（调用方负责）。
        """

        # ---- 1. 仅群聊 ----
        if not msg.is_group:
            return None

        roomid = msg.roomid

        # ---- 2. 群过滤（白名单/黑名单） ----
        if not self._group_allowed(roomid):
            return None

        # ---- 3. @bot 检测 ----
        content = msg.content.strip()
        is_at_bot = self._is_at_bot(msg)

        # ---- 4. 记录用户活动 ----
        speaker_wxid = msg.sender_name  # WeFlow 中 sender_name 即 wxid
        speaker_display = msg.display_name

        # 记录到用户记忆
        if self.user_memory:
            self.user_memory.record_message(speaker_wxid, speaker_display)

        # 记录到群活跃用户
        session = self._get_session(roomid)
        session.active_users.add(speaker_wxid)
        session.message_count += 1

        # ---- 5. 命令优先 ----
        if is_at_bot and content.startswith("/"):
            return self._handle_command(content, roomid, msg)

        # ---- 6. 非 @ 不回复 ----
        if not is_at_bot:
            return None

        # ---- 7. 冷却检查 ----
        elapsed = time.time() - session.last_reply_at
        if elapsed < self.cooldown:
            logger.debug("群 %s 回复冷却中 (%.1fs < %ds)", roomid, elapsed, self.cooldown)
            return None

        # ---- 8. 添加用户消息到历史（带发送者信息） ----
        clean = self._clean_at_text(msg)
        chat_msg = ChatMessage(
            role="user",
            content=clean,
            sender_name=speaker_display,
            sender_wxid=speaker_wxid,
            timestamp=time.time(),
        )
        session.history.append(chat_msg)
        session.last_reply_at = time.time()

        # 返回 None 表示需要 LLM 处理（调用方负责）
        return None

    def get_history(self, roomid: str) -> list:
        """获取某个群的对话历史，供 LLM 使用。"""
        session = self._get_session(roomid)
        return list(session.history)

    def add_reply(self, roomid: str, reply: str) -> None:
        """LLM 回复后，将回复加入该群的对话历史。"""
        session = self._get_session(roomid)
        session.history.append(ChatMessage(
            role="assistant",
            content=reply,
            timestamp=time.time(),
        ))

    def get_session(self, roomid: str) -> GroupSession:
        """获取群会话（供外部使用）。"""
        return self._get_session(roomid)

    # ----------------------------------------------------------------
    # 内部方法
    # ----------------------------------------------------------------
    def _is_at_bot(self, msg: WeFlowMessage) -> bool:
        """判断消息是否 @了机器人（精确匹配 @昵称）。"""
        if f"@{self.bot_name}" in msg.content:
            return True
        return False

    def _clean_at_text(self, msg: WeFlowMessage) -> str:
        """去掉 @bot 部分，返回干净的用户问题。"""
        text = msg.content.strip()
        import re
        text = re.sub(r"@[^\s]+\s*", "", text).strip()
        return text

    def _group_allowed(self, roomid: str) -> bool:
        """群白名单/黑名单过滤。"""
        wl = self.config.groups.whitelist
        bl = self.config.groups.blacklist
        if wl and roomid not in wl:
            return False
        if bl and roomid in bl:
            return False
        return True

    def _get_session(self, roomid: str) -> GroupSession:
        if roomid not in self._sessions:
            max_history = self.config.session.max_history_rounds * 2
            self._sessions[roomid] = GroupSession(
                group_id=roomid,
                history=deque(maxlen=max_history),
            )
        return self._sessions[roomid]

    # ----------------------------------------------------------------
    # 命令处理
    # ----------------------------------------------------------------
    def _handle_command(self, content: str, roomid: str, msg: WeFlowMessage = None) -> Optional[Tuple[str, str]]:
        """处理 /xxx 命令。返回 (reply, roomid) 或 None。"""
        parts = content.split()
        cmd = parts[0].lower()

        if cmd == "/help":
            return (self._help_text(), roomid)

        if cmd == "/reset":
            self._sessions.pop(roomid, None)
            return ("✅ 对话已重置，我忘记了之前聊过什么。", roomid)

        if cmd == "/status":
            session = self._get_session(roomid)
            rounds = len(session.history) // 2
            users = len(session.active_users)
            mem_info = ""
            if self.user_memory:
                mem_info = f"，记忆了 {self.user_memory.user_count} 个用户"
            return (f"📊 当前会话: {rounds} 轮对话，{users} 个活跃成员{mem_info}，冷却 {self.cooldown}s", roomid)

        if cmd == "/whois":
            # /whois @某人 — 查看某用户的信息
            if msg and len(parts) > 1:
                target_name = parts[1].lstrip("@")
                if self.user_memory:
                    profile = self.user_memory.find_by_name(target_name)
                    if profile:
                        summary = profile.get_context_summary()
                        if summary:
                            return (f"📋 @{target_name}: {summary}", roomid)
                        else:
                            return (f"📋 @{target_name}: 暂无已知信息", roomid)
                    else:
                        return (f"❓ 没找到 @{target_name} 的信息", roomid)
                return ("⚠ 用户记忆功能未启用", roomid)
            return ("用法: /whois @某人", roomid)

        if cmd == "/memory":
            # 显示群上下文摘要
            session = self._get_session(roomid)
            ctx = session.group_context
            if ctx:
                return (f"🧠 群聊记忆:\n{ctx}", roomid)
            return ("🧠 暂无群聊记忆，多聊聊我就会慢慢了解你们～", roomid)

        if cmd == "/remember":
            # /remember @某人 事实: 值 — 手动教 bot 记住
            if self.user_memory and msg and len(parts) >= 3:
                # 格式: /remember @name key: value
                rest = " ".join(parts[1:])
                if rest.startswith("@"):
                    name_end = rest.index(" ")
                    target_name = rest[1:name_end]
                    fact_part = rest[name_end+1:].strip()
                    if ":" in fact_part:
                        key, value = fact_part.split(":", 1)
                        profile = self.user_memory.find_by_name(target_name)
                        if profile:
                            self.user_memory.update_fact(profile.wxid, key.strip(), value.strip())
                            return (f"✅ 记住了 @{target_name}: {key.strip()} = {value.strip()}", roomid)
                        return (f"❓ 没找到 @{target_name}", roomid)
            return ("用法: /remember @某人 事实: 值", roomid)

        return (f"未知命令: {cmd}，发送 /help 查看可用命令", roomid)

    def _help_text(self) -> str:
        return (
            f"🤖 {self.bot_name} 使用说明:\n"
            f"  @我 + 任意问题 — 和我聊天（我会记住你们）\n"
            f"  /help     — 显示此帮助\n"
            f"  /reset    — 重置对话记忆\n"
            f"  /status   — 查看当前状态\n"
            f"  /whois @某人 — 查看某用户的信息\n"
            f"  /memory   — 查看群聊记忆\n"
            f"  /remember @某人 事实:值 — 教我记得某事\n"
        )
