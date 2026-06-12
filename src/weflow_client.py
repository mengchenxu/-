"""
WeFlow 接入层 — SSE 实时收消息 + 消息缓冲 + UIA 发送。
"""
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Dict, Any, Tuple

import requests

logger = logging.getLogger(__name__)


@dataclass
class WeFlowMessage:
    """从 WeFlow SSE 解析出的消息对象。"""
    rawid: str
    content: str
    session_id: str
    session_type: str
    group_name: str
    sender_name: str
    talker_id: str
    timestamp: int
    raw: dict = field(default_factory=dict)

    @property
    def is_group(self) -> bool:
        return self.session_type == "group"

    @property
    def roomid(self) -> str:
        return self.session_id


class MessageBuffer:
    """消息缓冲器：收集 N 秒内的消息，合并后推送给 LLM。"""

    def __init__(self, buffer_seconds: float = 2.0, callback: Optional[Callable] = None):
        self.buffer_seconds = buffer_seconds
        self.callback = callback
        self._buffer: Dict[str, list] = {}  # {session_id: [WeFlowMessage]}
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    def add(self, msg: WeFlowMessage, at_sender: str = "") -> None:
        """添加消息到缓冲。"""
        with self._lock:
            key = msg.session_id
            if key not in self._buffer:
                self._buffer[key] = []
            self._buffer[key].append(msg)

            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.buffer_seconds, self._flush)
            self._timer.start()

    def _flush(self) -> None:
        """清空缓冲，调用回调。"""
        with self._lock:
            if not self._buffer:
                return
            for session_id, msgs in self._buffer.items():
                if msgs and self.callback:
                    # 合并成一条消息推送
                    merged = "\n".join([m.content for m in msgs])
                    self.callback(session_id, merged, msgs[0])
            self._buffer.clear()
            self._timer = None


class WeFlowClient:
    """
    WeFlow + UIA 客户端：
    - SSE 接收 WeFlow 消息推送
    - 消息缓冲合并
    - UIA 自动化发送
    """

    def __init__(self, base_url: str = "http://127.0.0.1:5031", access_token: str = ""):
        self.base_url = base_url
        self.access_token = access_token
        self._running = False
        self._callback: Optional[Callable[[WeFlowMessage], None]] = None
        self._seen_rawids: set = set()
        self._uia_sender = None
        self._buffer: Optional[MessageBuffer] = None
        self.bot_nicknames: list = []
        self.bot_wxid: str = ""

    def set_bot_identity(self, nicknames: list, wxid: str = ""):
        """设置机器人昵称列表和 wxid，用于自回过滤和 @ 检测。"""
        self.bot_nicknames = nicknames
        self.bot_wxid = wxid

    # ----------------------------------------------------------------
    # SSE 接收
    # ----------------------------------------------------------------
    def start_receiving(self) -> None:
        self._running = True
        threading.Thread(target=self._sse_loop, daemon=True, name="weflow-sse").start()
        logger.info("WeFlow SSE 接收线程已启动")

    def _sse_loop(self) -> None:
        url = f"{self.base_url}/api/v1/push/messages"
        if self.access_token:
            url += f"?access_token={self.access_token}"
        start_ts = int(time.time() * 1000)

        while self._running:
            try:
                logger.info("连接 WeFlow SSE: %s", url[:60])
                resp = requests.get(url, stream=True, timeout=300)
                if resp.status_code != 200:
                    logger.warning("SSE 返回 %d，5秒后重试", resp.status_code)
                    time.sleep(5)
                    continue
                logger.info("SSE 连接成功: %d", resp.status_code)

                for line in resp.iter_lines(decode_unicode=True):
                    if not self._running:
                        break
                    if not line or not line.startswith("data:"):
                        continue
                    self._handle_sse_line(line, start_ts)
            except requests.exceptions.ConnectionError:
                if self._running:
                    logger.warning("WeFlow 连接失败，5秒后重连...")
                    time.sleep(5)
            except Exception:
                if self._running:
                    logger.exception("SSE 异常，5秒后重连...")
                    time.sleep(5)

    def _handle_sse_line(self, line: str, start_ts: int) -> None:
        try:
            data_str = line[5:].strip()
            if not data_str:
                return
            data = json.loads(data_str)
            msg = self._parse_message(data)

            if msg is None:
                return
            if msg.timestamp < start_ts:
                return
            if msg.rawid in self._seen_rawids:
                return
            self._seen_rawids.add(msg.rawid)
            if len(self._seen_rawids) > 50000:
                self._seen_rawids = set(list(self._seen_rawids)[-10000:])

            # 自回过滤
            if self._is_self(msg):
                return

            if self._callback:
                self._callback(msg)
        except Exception:
            logger.exception("SSE 解析异常")

    def _parse_message(self, data: dict) -> Optional[WeFlowMessage]:
        content = data.get("content", "") or ""
        session_type = data.get("sessionType", "") or ""

        # 跳过语音
        msg_type = data.get("type") or data.get("msgType")
        if msg_type == 34 or "[语音]" in content:
            return None
        if not content.strip():
            return None

        return WeFlowMessage(
            rawid=data.get("rawid", "") or str(time.time()),
            content=content,
            session_id=data.get("sessionId", "") or "",
            session_type=session_type,
            group_name=data.get("groupName", "") or "",
            sender_name=data.get("senderName", "") or data.get("sourceName", "") or "",
            talker_id=data.get("talkerId", "") or "",
            timestamp=data.get("timestamp", 0) or 0,
            raw=data,
        )

    def _is_self(self, msg: WeFlowMessage) -> bool:
        """判断是否为机器人自己的消息。"""
        sender = msg.sender_name
        if self.bot_wxid and self.bot_wxid in msg.talker_id:
            return True
        for nick in self.bot_nicknames:
            if nick and nick in sender:
                return True
        return False

    def is_at_bot(self, msg: WeFlowMessage) -> bool:
        """检测是否 @ 了机器人（基于内容）。"""
        for nick in self.bot_nicknames:
            if nick and nick in msg.content:
                return True
        return False

    def on_message(self, callback: Callable[[WeFlowMessage], None]) -> None:
        self._callback = callback

    # ----------------------------------------------------------------
    # 发送
    # ----------------------------------------------------------------
    def send_text(self, text: str, receiver: str, at_sender: str = "") -> bool:
        """通过 UIA 发送文本消息。"""
        if self._uia_sender is None:
            try:
                from src.uia_sender import UiaSender
                self._uia_sender = UiaSender()
                logger.info("UIA 发送器初始化成功")
            except Exception:
                logger.exception("UIA 发送器初始化失败")
                return False

        try:
            return self._uia_sender.send_text(receiver, text)
        except Exception:
            logger.exception("UIA 发送失败")
            return False

    def stop(self) -> None:
        self._running = False
        logger.info("WeFlow 客户端已停止")
