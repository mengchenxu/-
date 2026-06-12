"""诊断 WeChat 窗口检测 & 发送"""
import ctypes, time

print("=== WeChat 窗口检测 ===")
classes = ('Qt51514QWindowIcon', 'WeChatMainWndForPC', 'CefTopWindow', 'Qt*', '*WeChat*')
found_any = False
for cls in classes:
    hwnd = ctypes.windll.user32.FindWindowW(cls, None)
    if hwnd:
        # 获取窗口标题
        title = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetWindowTextW(hwnd, title, 256)
        print(f"  ✅ 找到: ClassName='{cls}' Title='{title.value}' hwnd={hwnd}")
        found_any = True
    else:
        print(f"  ❌ 未找到: ClassName='{cls}'")

if not found_any:
    print("\n⚠ 一个微信窗口都没找到！")
    print("  请确保微信正在运行并已登录")
else:
    print("\n=== 测试键盘输入（会在微信输入框粘贴测试文字）===")
    print("  请确保微信窗口可见，3秒后测试...")
    time.sleep(3)

    # 聚焦微信
    for cls in ('Qt51514QWindowIcon', 'WeChatMainWndForPC', 'CefTopWindow'):
        hwnd = ctypes.windll.user32.FindWindowW(cls, None)
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 1)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            print(f"  已聚焦微信窗口: {cls}")
            break

    # 测试粘贴
    import pyperclip
    pyperclip.copy("🐹 测试消息 - 鼠鼠诊断")
    time.sleep(0.2)

    VK_CONTROL = 0x11
    VK_V = 0x56
    ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
    ctypes.windll.user32.keybd_event(VK_V, 0, 0, 0)
    ctypes.windll.user32.keybd_event(VK_V, 0, 2, 0)
    ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 2, 0)

    print("  已发送 Ctrl+V，请检查微信输入框是否有文字")
    print("  （不会自动按 Enter，只粘贴不发送）")

print("\n=== 诊断完成 ===")
