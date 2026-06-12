"""
UIA 发送器 — 直接用微信窗口控件的 SendKeys，不依赖前景窗口。
"""
import logging, threading, time
log = logging.getLogger(__name__)


class UiaSender:
    def __init__(self):
        self._lock = threading.Lock()
        self._ready = False
        self._auto = None
        self._window = None
        self._init()

    def _init(self):
        import uiautomation as auto
        self._auto = auto
        root = auto.GetRootControl()
        for w in root.GetChildren():
            name = w.Name or ""
            if "微信" in name or "WeChat" in name:
                self._window = w
                self._ready = True
                return
        for cls in ("Qt51514QWindowIcon", "CefTopWindow"):
            try:
                w = auto.WindowControl(ClassName=cls, searchDepth=1)
                if w.Exists(1):
                    self._window = w
                    self._ready = True
                    return
            except Exception:
                pass

    def send_text(self, contact: str, text: str, at_sender: str = "") -> bool:
        with self._lock:
            if not self._ready or not self._window:
                self._init()
                if not self._ready:
                    return False
            try:
                import ctypes, pyperclip

                # 强制前台
                hwnd = self._window.NativeWindowHandle
                TID = ctypes.windll.user32.GetWindowThreadProcessId(hwnd, None)
                CTID = ctypes.windll.kernel32.GetCurrentThreadId()
                ctypes.windll.user32.AttachThreadInput(CTID, TID, True)
                try:
                    ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                except Exception:
                    pass
                time.sleep(0.4)

                # 用微信窗口自己的 SendKeys（不依赖全局焦点）
                if at_sender:
                    self._window.SendKeys('@')
                    time.sleep(0.3)
                    self._window.SendKeys(at_sender)
                    time.sleep(0.4)
                    self._window.SendKeys('{Enter}')
                    time.sleep(0.3)
                    self._window.SendKeys(' ')
                    time.sleep(0.1)

                pyperclip.copy(text)
                time.sleep(0.1)
                self._window.SendKeys('{Ctrl}v')
                time.sleep(0.3)
                self._window.SendKeys('{Enter}')

                ctypes.windll.user32.AttachThreadInput(CTID, TID, False)
                log.info("Sent: @%s %s...", at_sender or "no-at", text[:40])
                return True
            except Exception as e:
                log.error("Send failed: %s", e)
                return False
