"""
UIA 发送器 — 支持真实 @mention 效果。
"""
import logging, threading, time
log = logging.getLogger(__name__)


class UiaSender:
    def __init__(self):
        self._lock = threading.Lock()
        self._ready = False
        self._auto = None
        self._init()

    def _init(self):
        import uiautomation as auto
        self._auto = auto
        root = auto.GetRootControl()
        for w in root.GetChildren():
            if "微信" in w.Name or "WeChat" in w.Name:
                self._ready = True
                return
        for cls in ("Qt51514QWindowIcon", "CefTopWindow", "WeChatMainWndForPC"):
            try:
                w = auto.WindowControl(ClassName=cls, searchDepth=1)
                if w.Exists(1):
                    self._ready = True
                    return
            except Exception:
                pass

    def send_text(self, contact: str, text: str, at_sender: str = "") -> bool:
        """
        发送文本。at_sender 不为空时，通过 @选人实现真实群聊 @效果。
        """
        with self._lock:
            if not self._ready:
                return False
            try:
                import ctypes, pyperclip

                hwnd = ctypes.windll.user32.FindWindowW('Qt51514QWindowIcon', None)
                if not hwnd:
                    hwnd = ctypes.windll.user32.FindWindowW('WeChatMainWndForPC', None)
                if not hwnd:
                    return False

                TID = ctypes.windll.user32.GetWindowThreadProcessId(hwnd, None)
                CTID = ctypes.windll.kernel32.GetCurrentThreadId()
                ctypes.windll.user32.AttachThreadInput(CTID, TID, True)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                time.sleep(0.2)

                if at_sender:
                    # 真实 @mention: 打字 @ + 名 → Enter 选中 → 空格 → 粘贴回复
                    self._auto.SendKeys('@')
                    time.sleep(0.3)
                    self._auto.SendKeys(at_sender)
                    time.sleep(0.4)
                    self._auto.SendKeys('{Enter}')
                    time.sleep(0.3)
                    self._auto.SendKeys(' ')  # @mention 后加空格
                    time.sleep(0.1)

                pyperclip.copy(text)
                time.sleep(0.05)
                self._auto.SendKeys('{Ctrl}v')
                time.sleep(0.3)
                self._auto.SendKeys('{Enter}')

                ctypes.windll.user32.AttachThreadInput(CTID, TID, False)
                log.info("Sent: @%s %s...", at_sender or "no-at", text[:40])
                return True
            except Exception as e:
                log.error("Send failed: %s", e)
                return False
