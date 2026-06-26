"""游戏会话管理 — 一个群一个活跃游戏，多人随时参与"""
import logging
import time
from dataclasses import dataclass
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

# 手动退出关键词
_EXIT_KEYWORDS = ["不玩了", "退出", "算了"]

# 再来一次关键词
_RERUN_KEYWORDS = ["再来一次", "再掷一次", "再来一发", "重来"]


@dataclass
class GameSession:
    game_name: str           # "/骰子"
    display_name: str        # "骰子"
    started_at: float        # 开始时间戳
    last_input_at: float     # 上次输入时间戳（超时检测用）

    def touch(self):
        self.last_input_at = time.time()

    def is_expired(self, timeout_minutes: int = 5) -> bool:
        return time.time() - self.last_input_at > timeout_minutes * 60


class GameSessionManager:
    """管理所有群的游戏会话。"""

    def __init__(self, timeout_minutes: int = 5):
        self._sessions: Dict[str, GameSession] = {}  # room_id → GameSession
        self._timeout_minutes = timeout_minutes

    @property
    def active_rooms(self) -> List[str]:
        return list(self._sessions.keys())

    def enter(self, room_id: str, game_name: str, display_name: str) -> GameSession:
        """进入游戏模式。覆盖已有的。"""
        session = GameSession(
            game_name=game_name,
            display_name=display_name,
            started_at=time.time(),
            last_input_at=time.time(),
        )
        self._sessions[room_id] = session
        logger.info("Game session started: room=%s game=%s", room_id[:20], game_name)
        return session

    def leave(self, room_id: str) -> Optional[GameSession]:
        """退出游戏模式，返回被退出的 session 或 None。"""
        session = self._sessions.pop(room_id, None)
        if session:
            logger.info("Game session ended: room=%s game=%s", room_id[:20], session.game_name)
        return session

    def get(self, room_id: str) -> Optional[GameSession]:
        """获取当前活跃的 game session。"""
        return self._sessions.get(room_id)

    def is_in_game(self, room_id: str) -> bool:
        return room_id in self._sessions

    def check_timeout(self, room_id: str) -> Optional[GameSession]:
        """超时检查，返回被超时退出的 session 或 None。"""
        session = self._sessions.get(room_id)
        if session and session.is_expired(self._timeout_minutes):
            return self.leave(room_id)
        return None

    def is_exit_command(self, content: str) -> bool:
        """检测消息是否包含退出关键词（"不玩了/退出/算了"）。"""
        return any(kw in content for kw in _EXIT_KEYWORDS)

    def is_rerun_command(self, content: str) -> bool:
        """检测消息是否包含重掷关键词（"再来一次/再掷一次" 等）。"""
        return any(kw in content for kw in _RERUN_KEYWORDS)

    def make_exit_message(self, display_name: str) -> str:
        """生成猫娘风格退出公告。"""
        return f"喵~ 人家退出 {display_name} 啦！有什么要问的记得 @人家哟 💕"
