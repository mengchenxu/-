"""
UIA 发送器 — 通过 Windows UI Automation 控制微信窗口发送消息。
适配微信 4.x (Electron 架构)。
"""
import logging
import threading
import time

import pyperclip

logger = logging.getLogger(__name__)


class UiaSender:
    """通过 uiautomation 控制微信窗口，向指定联系人/群发送文本消息。"""

    def __init__(self):
        import uiautomation as auto
        self.auto = auto
        self._lock = threading.Lock()
        self._window = self._find_window()

    # ------------------------------------------------------------
    # 窗口定位
    # ------------------------------------------------------------
    def _find_window(self):
        """查找微信窗口。"""
        auto = self.auto
        for w in auto.GetRootControl().GetChildren():
            name = w.Name or ""
            if "微信" in name or "WeChat" in name:
                logger.info("找到微信窗口: %s (ClassName=%s)", name, w.ClassName)
                return w
        logger.error("未找到微信窗口，请确认微信已登录")
        return None

    # ------------------------------------------------------------
    # 联系人切换
    # ------------------------------------------------------------
    def _switch_contact(self, contact: str) -> bool:
        """
        通过 Ctrl+F 搜索框切换到目标联系人/群。
        返回是否成功。
        """
        if not self._window:
            return False

        try:
            with self._lock:
                # 激活窗口
                self._activate_window()
                time.sleep(0.1)

                # Ctrl+F 打开搜索
                self._window.SendKeys("{Ctrl}f")
                time.sleep(0.2)

                # Ctrl+A 全选 → 粘贴联系人名 → Enter
                self.auto.SendKeys("{Ctrl}a")
                time.sleep(0.05)

                pyperclip.copy(contact)
                self.auto.SendKeys("{Ctrl}v")
                time.sleep(0.1)

                self.auto.SendKeys("{Enter}")
                time.sleep(0.3)

                return True
        except Exception:
            logger.exception("切换联系人失败: %s", contact)
            return False

    # ------------------------------------------------------------
    # 发送文本
    # ------------------------------------------------------------
    def send_text(self, contact: str, text: str) -> bool:
        """向指定联系人发送文本消息。"""
        if not self._window:
            logger.error("微信窗口不可用")
            return False

        # 切到目标联系人
        if not self._switch_contact(contact):
            return False

        try:
            with self._lock:
                # 方式1: 尝试 ValuePattern 直接设值（Electron 微信 4.x 支持）
                edit = self._find_input_box()
                if edit and self._try_set_value(edit, text):
                    self._click_send()
                    return True

                # 方式2: 剪贴板后备
                logger.debug("ValuePattern 不可用，使用剪贴板方式")
                pyperclip.copy(text)
                self.auto.SendKeys("{Ctrl}v")
                time.sleep(0.1)
                self.auto.SendKeys("{Enter}")
                return True

        except Exception:
            logger.exception("UIA 发送失败")
            return False

    # ------------------------------------------------------------
    # 输入框定位
    # ------------------------------------------------------------
    def _find_input_box(self):
        """遍历窗口 UIA 子树，找到聊天输入框。"""
        window = self._window
        center_y = window.BoundingRectangle.top + window.BoundingRectangle.height() / 2

        candidates = []
        for ctrl, _ in self.auto.WalkTree(window, lambda c: True, maxDepth=6):
            if ctrl.ControlTypeName == "EditControl":
                # 只考虑窗口下半部分的 EditControl（聊天输入框）
                if hasattr(ctrl, 'BoundingRectangle') and ctrl.BoundingRectangle.top >= center_y:
                    w = ctrl.BoundingRectangle.width()
                    if w > 100:
                        candidates.append((w * ctrl.BoundingRectangle.height(), ctrl))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            logger.debug("找到输入框候选: %d 个", len(candidates))
            return candidates[0][1]
        return None

    def _try_set_value(self, edit, text: str) -> bool:
        """尝试通过 ValuePattern.SetValue 设置文本。"""
        try:
            pattern = edit.GetPattern(self.auto.PatternId.ValuePattern)
            if pattern:
                pattern.SetValue("")  # 清空
                pattern.SetValue(text)
                return True
        except Exception:
            pass
        return False

    def _click_send(self) -> None:
        """点击发送按钮或按 Enter。"""
        try:
            self.auto.SendKeys("{Enter}")
        except Exception:
            pass

    # ------------------------------------------------------------
    # 窗口激活
    # ------------------------------------------------------------
    def _activate_window(self) -> None:
        """激活微信窗口（允许后台发送）。"""
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            hwnd = self._window.NativeWindowHandle
            fore_thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), 0)
            cur_thread = kernel32.GetCurrentThreadId()

            user32.AttachThreadInput(cur_thread, fore_thread, True)
            try:
                user32.SetForegroundWindow(hwnd)
                user32.BringWindowToTop(hwnd)
            finally:
                user32.AttachThreadInput(cur_thread, fore_thread, False)
        except Exception:
            logger.debug("窗口激活失败（不影响发送）")
