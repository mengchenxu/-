"""
风格观察器 — 监听所有群消息，维护缓冲区 + 实时统计，供定期风格分析使用。
"""
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RoomStats:
    """单个群的实时统计"""
    word_counter: Counter = field(default_factory=Counter)
    emoji_counter: Counter = field(default_factory=Counter)
    total_length: int = 0
    message_count: int = 0


class StyleObserver:
    """
    监听所有群消息，维护每个群的：
    - 消息缓冲区（供 LLM 定期分析风格）
    - 实时统计（词频、表情频率、平均句长）
    """

    def __init__(self, max_buffer: int = 30):
        self.max_buffer = max_buffer
        self._buffers: dict[str, list[dict]] = defaultdict(list)
        self._stats: dict[str, RoomStats] = defaultdict(RoomStats)

    def observe(self, room_id: str, wxid: str, display_name: str, content: str):
        """记录一条群消息到缓冲区和统计。"""
        if not content.strip():
            return

        # 统计
        stats = self._stats[room_id]
        stats.message_count += 1
        stats.total_length += len(content)

        # 简单分词（按非中文字符/空格分割，并提取单个汉字序列）
        words = re.findall(r'[一-鿿]{2,}', content)
        for w in words:
            stats.word_counter[w.lower()] += 1

        # 提取表情
        emojis = re.findall(r'[\U0001F300-\U0001FAFF☀-➿✀-➿︀-️‍]', content)
        for e in emojis:
            stats.emoji_counter[e] += 1

        # 缓冲区
        self._buffers[room_id].append({
            "wxid": wxid,
            "name": display_name,
            "content": content,
        })

    def should_analyze(self, room_id: str) -> bool:
        """缓冲区满时返回 True。"""
        return len(self._buffers.get(room_id, [])) >= self.max_buffer

    def get_buffer(self, room_id: str) -> list[dict]:
        """返回缓冲区消息列表，取完后清空。"""
        msgs = list(self._buffers.get(room_id, []))
        self._buffers[room_id] = []
        return msgs

    def get_stats(self, room_id: str) -> dict:
        """返回当前统计快照。"""
        stats = self._stats.get(room_id)
        if not stats or stats.message_count == 0:
            return {"top_words": [], "top_emojis": [], "avg_len": 0}

        return {
            "top_words": [w for w, _ in stats.word_counter.most_common(15)],
            "top_emojis": [e for e, _ in stats.emoji_counter.most_common(5)],
            "avg_len": round(stats.total_length / stats.message_count, 1),
        }

    def reset_buffer(self, room_id: str):
        self._buffers[room_id] = []

    def reset_all(self, room_id: str):
        """重置某个群的缓冲区和统计。"""
        self._buffers.pop(room_id, None)
        self._stats.pop(room_id, None)
