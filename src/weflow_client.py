"""
WeFlow 接入层 — 通过 WeFlow SSE 接收微信消息，UIA 自动化发送消息。
替换原来的 wcf_client.py，支持微信 4.x。
"""
import json
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Dict, Any

import requests

from src.config_loader import AppConfig

logger = logging.getLogger(__name__)


@dataclass
class WeFlowMessage:
    """从 WeFlow SSE 解析出的消息对象。"""
    rawid: str            # 消息唯一 ID（去重用）
    content: str          # 消息文本内容
    session_id: str       # 群 ID（xxx@chatroom）或私聊对方 wxid
    session_type: str     # "group" 或空（私聊）
    group_name: str       # 群名称
    sender_name: str      # 发送者名称
    talker_id: str        # 发送者 wxid
    timestamp: int        # 消息时间戳
    raw: dict = field(default_factory=dict)  # 原始数据

    @property
    def is_group(self) -> bool:
        return self.session_type == "group"

    @property
    def roomid(self) -> str:
        return self.session_id


class WeFlowClient:
    """
    替代原 WcfClient：
    - 收消息：连接 WeFlow SSE (/api/v1/push/messages)
    - 发消息：UIA 自动化（或 WeFlow API）
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.base_url = "http://127.0.0.1:5031"
        self.access_token = getattr(config, 'weflow_token', '') or ""

        self._running = False
        self._callback: Optional[Callable[[WeFlowMessage], None]] = None
        self._msg_queue: queue.Queue = queue.Queue()
        self._seen_rawids: set = set()

        # UIA 发送器延迟初始化（只在需要时导入）
        self._uia_sender = None

    # ------------------------------------------------------------
    # 消息接收 — SSE
    # ------------------------------------------------------------
    def start_receiving(self) -> None:
        """连接 WeFlow SSE，在后台线程中接收消息。"""
        self._running = True
        threading.Thread(target=self._sse_loop, daemon=True, name="weflow-sse").start()
        logger.info("WeFlow SSE 接收线程已启动")

    def _sse_loop(self) -> None:
        """SSE 长连接循环，自动重连。"""
        url = f"{self.base_url}/api/v1/push/messages"
        if self.access_token:
            url += f"?access_token={self.access_token}"

        start_ts = int(time.time() * 1000)

        while self._running:
            try:
                logger.info("连接 WeFlow SSE: %s", url)
                resp = requests.get(url, stream=True, timeout=300)
                logger.info("SSE 连接成功，状态码: %d", resp.status_code)

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
        """解析单行 SSE 数据。"""
        try:
            data_str = line[5:].strip()  # 去掉 "data:"
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
            # 限制去重集合大小
            if len(self._seen_rawids) > 50000:
                self._seen_rawids = set(list(self._seen_rawids)[-10000:])

            if self._callback:
                self._callback(msg)

        except json.JSONDecodeError:
            pass
        except Exception:
            logger.exception("SSE 消息解析异常")

    def _parse_message(self, data: dict) -> Optional[WeFlowMessage]:
        """将 WeFlow API 返回的 JSON 转为 WeFlowMessage。"""
        content = data.get("content", "") or ""
        session_type = data.get("sessionType", "") or ""

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

    def on_message(self, callback: Callable[[WeFlowMessage], None]) -> None:
        """注册消息回调。"""
        self._callback = callback

    # ------------------------------------------------------------
    # 消息发送 — UIA 自动化
    # ------------------------------------------------------------
    def send_text(self, text: str, receiver: str, at_sender: str = "") -> bool:
        """
        发送文本消息到群聊。
        - receiver: 群 ID（xxx@chatroom）或联系人名称
        - at_sender: 要 @ 的人
        """
        if self._uia_sender is None:
            self._init_uia_sender()

        try:
            # UIA 发送：先切到目标群，再发消息
            if self._uia_sender:
                self._uia_sender.send_text(receiver, text)
                logger.info("UIA 发送成功: to=%s, text=%s", receiver, text[:50])
                return True
        except Exception:
            logger.exception("UIA 发送失败，尝试 WeFlow API")

        # 后备：WeFlow API 发送
        return self._send_via_weflow_api(text, receiver)

    def _send_via_weflow_api(self, text: str, receiver: str) -> bool:
        """通过 WeFlow API 发送消息。"""
        try:
            url = f"{self.base_url}/api/v1/message"
            headers = {"Content-Type": "application/json"}
            if self.access_token:
                headers["Authorization"] = f"Bearer {self.access_token}"
            payload = {
                "sessionId": receiver,
                "content": text,
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code == 200:
                logger.info("WeFlow API 发送成功: to=%s", receiver)
                return True
            else:
                logger.warning("WeFlow API 发送失败: %d %s", resp.status_code, resp.text)
        except Exception:
            logger.exception("WeFlow API 发送异常")
        return False

    # ------------------------------------------------------------
    # UIA 发送器
    # ------------------------------------------------------------
    def _init_uia_sender(self) -> None:
        """初始化 UIA 自动化发送器。"""
        try:
            from src.uia_sender import UiaSender
            self._uia_sender = UiaSender()
            logger.info("UIA 发送器初始化成功")
        except Exception:
            logger.exception("UIA 发送器初始化失败")
            self._uia_sender = None

    # ------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------
    def stop(self) -> None:
        """停止 SSE 连接并清理。"""
        self._running = False
        logger.info("WeFlow 客户端已停止")
