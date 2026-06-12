"""
独立消息发送进程 — 无控制台，键盘事件直接进微信。
通过文件通信，避免终端抢焦点。
"""
import ctypes, json, os, sys, time

VK_CONTROL = 0x11
VK_V = 0x56
VK_RETURN = 0x0D

def tap(k): 
    ctypes.windll.user32.keybd_event(k, 0, 0, 0)
    ctypes.windll.user32.keybd_event(k, 0, 2, 0)

def focus_wechat():
    for cls in ('Qt51514QWindowIcon', 'WeChatMainWndForPC', 'CefTopWindow'):
        hwnd = ctypes.windll.user32.FindWindowW(cls, None)
        if hwnd:
            TID = ctypes.windll.user32.GetWindowThreadProcessId(hwnd, None)
            CTID = ctypes.windll.kernel32.GetCurrentThreadId()
            ctypes.windll.user32.AttachThreadInput(CTID, TID, True)
            ctypes.windll.user32.ShowWindow(hwnd, 1)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.BringWindowToTop(hwnd)
            time.sleep(0.4)
            ctypes.windll.user32.AttachThreadInput(CTID, TID, False)
            return True
    return False

def send(contact: str, text: str, at_sender: str = ""):
    if not focus_wechat():
        return False
    import pyperclip
    if at_sender:
        # 用剪贴板输入名字（不逐个打字）
        pyperclip.copy("@" + at_sender + " ")
        time.sleep(0.1)
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
        tap(VK_V)
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 2, 0)
        time.sleep(0.5)
    pyperclip.copy(text)
    time.sleep(0.1)
    ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
    tap(VK_V)
    ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 2, 0)
    time.sleep(0.3)
    tap(VK_RETURN)
    return True

# 监听命令文件
CMD_FILE = "send_queue.json"
last_mtime = 0
while True:
    try:
        if os.path.exists(CMD_FILE):
            mtime = os.path.getmtime(CMD_FILE)
            if mtime != last_mtime:
                last_mtime = mtime
                with open(CMD_FILE, 'r', encoding='utf-8') as f:
                    cmd = json.load(f)
                if "text" in cmd:
                    send(cmd.get("contact",""), cmd["text"], cmd.get("at_sender",""))
                os.remove(CMD_FILE)
    except Exception:
        pass
    time.sleep(0.3)
