"""
UIA 消息接收器 v2 — 借鉴 wxauto 思路。
1. 轮询聊天列表，检测红点/未读标记
2. 点进有消息的聊天 → 读取消息列表 → 提取文本
3. 适配微信 4.x Qt 版
"""
import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class UiaMessage:
    content: str
    session_name: str
    session_type: str  # "group" / "private"
    sender_name: str
    timestamp: int = 0

    @property
    def is_group(self) -> bool:
        return self.session_type == "group"

    @property
    def roomid(self) -> str:
        return self.session_name


class UiaReceiver:
    """微信 4.x 消息接收器（轮询版）。"""

    def __init__(self, poll_interval: float = 2.0):
        self.poll_interval = poll_interval
        self._auto = None
        self._window = None
        self._running = False
        self._callback: Optional[Callable[[UiaMessage], None]] = None
        self._seen: set = set()
        self._last_chat = ""

    # ----------------------------------------------------------------
    # 初始化
    # ----------------------------------------------------------------
    def _init_uia(self) -> bool:
        import uiautomation as auto
        self._auto = auto

        root = auto.GetRootControl()
        for w in root.GetChildren():
            cls = w.ClassName
            if cls in ("Chrome_WidgetWin_1", "CabinetWClass"):
                continue
            for kw in ("微信", "WeChat"):
                if kw in w.Name:
                    self._window = w
                    logger.info("找到微信: '%s' (cls=%s)", w.Name, cls)
                    return True

        # 按类名找
        for cls in ("Qt51514QWindowIcon", "CefTopWindow"):
            try:
                w = auto.WindowControl(ClassName=cls, searchDepth=1)
                if w.Exists(1):
                    self._window = w
                    logger.info("找到微信: cls=%s", cls)
                    return True
            except Exception:
                pass
        return False

    # ----------------------------------------------------------------
    # 启动
    # ----------------------------------------------------------------
    def start(self) -> None:
        if not self._init_uia():
            logger.error("未找到微信窗口")
            return
        self._running = True
        threading.Thread(target=self._poll_loop, daemon=True, name="uia-recv").start()
        logger.info("UIA 接收器已启动")

    def on_message(self, callback: Callable[[UiaMessage], None]) -> None:
        self._callback = callback

    def stop(self) -> None:
        self._running = False

    # ----------------------------------------------------------------
    # 轮询
    # ----------------------------------------------------------------
    def _poll_loop(self) -> None:
        while self._running:
            try:
                self._poll_once()
            except Exception:
                logger.exception("轮询异常")
            time.sleep(self.poll_interval)

    def _poll_once(self) -> None:
        """检查聊天列表中的未读标记，点进去读消息。"""
        if not self._window or not self._window.Exists(0.5):
            self._init_uia()
            return

        # 获取有未读/新消息的 session 列表
        sessions = self._get_sessions_with_unread()
        if not sessions:
            return

        for session_name, unread_count in sessions.items():
            if unread_count <= 0:
                continue

            logger.info("检测到新消息: %s (%d条)", session_name, unread_count)

            # 切换到该聊天
            if self._switch_to_chat(session_name):
                time.sleep(0.5)
                # 读取消息
                msgs = self._read_messages()
                for m in msgs:
                    key = f"{session_name}|{m[:80]}"
                    if key in self._seen:
                        continue
                    self._seen.add(key)
                    if len(self._seen) > 2000:
                        self._seen = set(list(self._seen)[-1000:])

                    sender = self._parse_sender(m)
                    content = m
                    if sender:
                        content = m[len(sender):].lstrip(":").lstrip("：").strip()

                    if self._callback:
                        self._callback(UiaMessage(
                            content=content,
                            session_name=session_name,
                            session_type="group" if self._is_group() else "private",
                            sender_name=sender,
                        ))

            # 回聊天列表
            self._go_to_chat_list()
            time.sleep(0.5)

    # ----------------------------------------------------------------
    # UIA 操作
    # ----------------------------------------------------------------
    def _get_sessions_with_unread(self) -> Dict[str, int]:
        """遍历聊天列表，提取有未读标记的会话名和未读数。"""
        result = {}
        try:
            # 遍历所有 ListItem 控件，找到含"条新消息"的
            for ctrl, _ in self._auto.WalkTree(self._window, lambda c: True, maxDepth=10):
                name = ctrl.Name or ""
                if "条新消息" in name:
                    # 格式如 "群名\n联系人名\nX条新消息\n内容预览"
                    parts = name.split("\n")
                    for p in parts:
                        match = re.search(r'(\d+)条新消息', p)
                        if match:
                            count = int(match.group(1))
                            # 取前面的名字
                            idx = parts.index(p)
                            if idx > 0:
                                result[parts[idx - 1].strip()] = count
                            break
        except Exception:
            pass
        return result

    def _switch_to_chat(self, name: str) -> bool:
        """Ctrl+F 搜索 + 跳转到指定聊天。"""
        try:
            import ctypes
            hwnd = ctypes.windll.user32.FindWindowW('Qt51514QWindowIcon', None)
            if not hwnd:
                return False

            # Ctrl+F
            ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0x46, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0x46, 0, 2, 0)
            ctypes.windll.user32.keybd_event(0x11, 0, 2, 0)
            time.sleep(0.3)

            import pyperclip
            pyperclip.copy(name)
            time.sleep(0.1)
            ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0x56, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0x56, 0, 2, 0)
            ctypes.windll.user32.keybd_event(0x11, 0, 2, 0)
            time.sleep(0.3)

            ctypes.windll.user32.keybd_event(0x0D, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0x0D, 0, 2, 0)
            time.sleep(0.8)

            self._last_chat = name
            return True
        except Exception:
            return False

    def _go_to_chat_list(self) -> None:
        """回到聊天列表（按 Esc）。"""
        try:
            import ctypes
            ctypes.windll.user32.keybd_event(0x1B, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0x1B, 0, 2, 0)
        except Exception:
            pass

    def _read_messages(self) -> List[str]:
        """读取当前窗口消息内容。"""
        msgs = []
        try:
            for ctrl, _ in self._auto.WalkTree(self._window, lambda c: True, maxDepth=12):
                ct = ctrl.ControlTypeName
                name = (ctrl.Name or "").strip()
                if ct in ("TextControl", "ListItemControl") and len(name) > 2:
                    if not re.match(r'^\d{1,2}:\d{2}$', name) and "微信" not in name:
                        msgs.append(name)
        except Exception:
            pass
        # 返回最近 20 条
        return msgs[-20:] if len(msgs) > 20 else msgs

    def _is_group(self) -> bool:
        try:
            for ctrl, _ in self._auto.WalkTree(self._window, lambda c: True, maxDepth=10):
                if ("群成员" in (ctrl.Name or "")) or ("成员" in (ctrl.Name or "") and "群" in (ctrl.Name or "")):
                    return True
        except Exception:
            pass
        return False

    def _parse_sender(self, text: str) -> str:
        m = re.match(r'^([^：:]{1,20})[：:]', text)
        return m.group(1) if m else ""
