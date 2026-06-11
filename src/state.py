"""
全局共享状态 — 供 main.py 和 web_panel.py 通信。
"""
import threading


class BotState:
    def __init__(self):
        self.running = False
        self.weflow_connected = False
        self._restart_callback = None
        self._stop_callback = None

    def set_callbacks(self, restart_fn, stop_fn):
        self._restart_callback = restart_fn
        self._stop_callback = stop_fn

    def restart(self):
        if self._restart_callback:
            self._restart_callback()

    def stop(self):
        if self._stop_callback:
            self._stop_callback()
