"""
Web 控制面板 — 可视化控制机器人。
访问 http://127.0.0.1:8766
"""
import json
import logging
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

logger = logging.getLogger("web-panel")

PAGE_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Akasha 群聊机器人</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,system-ui,sans-serif;background:#fdf2f8;color:#333;min-height:100vh}
.header{background:linear-gradient(135deg,#ec4899,#8b5cf6);color:#fff;padding:20px;text-align:center}
.header h1{font-size:1.5em}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;padding:16px}
.card{background:#fff;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.1)}
.card h3{font-size:.85em;color:#888;margin-bottom:8px}
.status-dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}
.status-dot.on{background:#22c55e}.status-dot.off{background:#ef4444}
.btn{padding:8px 16px;border:none;border-radius:8px;cursor:pointer;font-size:.9em;margin:4px}
.btn-primary{background:#ec4899;color:#fff}
.btn-danger{background:#ef4444;color:#fff}
.btn-warn{background:#f59e0b;color:#fff}
.btn-success{background:#22c55e;color:#fff}
.logs{background:#1e1e2e;color:#a6e3a1;font-family:monospace;font-size:.8em;padding:12px;border-radius:8px;max-height:400px;overflow-y:auto;white-space:pre-wrap}
.config-editor{width:100%;height:300px;font-family:monospace;font-size:.85em;padding:8px;border:1px solid #ddd;border-radius:8px}
.tabs{display:flex;gap:8px;margin-bottom:12px}
.tab{padding:8px 16px;border:none;border-radius:8px 8px 0 0;cursor:pointer;background:#f3f4f6}
.tab.active{background:#ec4899;color:#fff}
</style>
</head>
<body>
<div class="header"><h1>🤖 群聊 AI 机器人</h1><p id="mode-info">加载中...</p></div>
<div class="cards">
<div class="card"><h3>桥接状态</h3><p><span class="status-dot" id="dot-bridge"></span><span id="txt-bridge">-</span></p></div>
<div class="card"><h3>WeFlow</h3><p><span class="status-dot" id="dot-weflow"></span><span id="txt-weflow">-</span></p></div>
<div class="card"><h3>发送模式</h3><strong id="txt-send">-</strong></div>
<div class="card"><h3>群聊模式</h3><strong id="txt-mode">-</strong></div>
</div>
<div style="padding:0 16px">
<button class="btn btn-primary" onclick="api('start')">▶ 启动</button>
<button class="btn btn-danger" onclick="api('stop')">■ 停止</button>
<button class="btn btn-warn" onclick="api('pause')">⏸ 暂停</button>
<button class="btn btn-success" onclick="api('resume')">▶ 恢复</button>
<button class="btn btn-primary" onclick="api('mode')">切换模式</button>
</div>
<div style="padding:16px">
<div class="tabs"><button class="tab active" onclick="showTab('logs')">日志</button><button class="tab" onclick="showTab('config')">配置</button></div>
<div id="tab-logs"><div class="logs" id="logs">等待...</div></div>
<div id="tab-config" style="display:none"><textarea class="config-editor" id="config-editor"></textarea><br><button class="btn btn-primary" onclick="saveConfig()">💾 保存配置</button></div>
</div>
<script>
var modeOrder=["mention","all","batch"];
function api(action){fetch('/'+action,{method:'POST'}).then(r=>r.json()).then(d=>console.log(d))}
function showTab(t){document.querySelectorAll('[id^="tab-"]').forEach(e=>e.style.display='none');
document.querySelectorAll('.tab').forEach(e=>e.classList.remove('active'));
document.getElementById('tab-'+t).style.display='block';event.target.classList.add('active')}
function saveConfig(){var cfg=document.getElementById('config-editor').value;
fetch('/api/config',{method:'POST',body:cfg}).then(r=>r.json()).then(d=>alert(d.ok?'已保存':'失败'))}
setInterval(function(){fetch('/status').then(r=>r.json()).then(d=>{
document.getElementById('txt-bridge').textContent=d.running?'运行中':'已停止';
document.getElementById('dot-bridge').className='status-dot '+(d.running?'on':'off');
document.getElementById('txt-weflow').textContent=d.weflow_connected?'已连接':'未连接';
document.getElementById('dot-weflow').className='status-dot '+(d.weflow_connected?'on':'off');
document.getElementById('txt-send').textContent=d.send_method||'uia';
document.getElementById('txt-mode').textContent=d.group_reply_mode||'mention';
document.getElementById('mode-info').textContent=d.running?'运行中 | 按Ctrl+C退出':'已停止';
document.getElementById('logs').textContent=d.log||'无日志';
})},2000);
fetch('/api/config').then(r=>r.json()).then(d=>document.getElementById('config-editor').value=JSON.stringify(d,null,2))
</script>
</body></html>"""


# 全局状态引用（由 main.py 注入）
_bot_state = None


def set_bot_state(state_module):
    global _bot_state
    _bot_state = state_module


class WebHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/status":
            running = _bot_state and _bot_state.running
            log_lines = []
            try:
                with open("logs/bot.log", encoding="utf-8", errors="replace") as f:
                    log_lines = f.read().splitlines()[-200:]
            except Exception:
                pass
            self._send_json({
                "running": running,
                "paused": False,
                "send_method": "uia",
                "weflow_connected": _bot_state and _bot_state.weflow_connected,
                "group_reply_mode": "mention",
                "log": "\n".join(log_lines),
            })
        elif self.path == "/api/config":
            try:
                with open("config/config.json", "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                cfg = {}
            self._send_json(cfg)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(PAGE_HTML.encode("utf-8"))

    def do_POST(self):
        if self.path == "/start":
            if _bot_state:
                _bot_state.restart()
            self._send_json({"ok": True})
        elif self.path == "/stop":
            if _bot_state:
                _bot_state.stop()
            self._send_json({"ok": True})
        elif self.path == "/pause":
            self._send_json({"ok": True})
        elif self.path == "/resume":
            self._send_json({"ok": True})
        elif self.path == "/mode":
            self._send_json({"ok": True, "mode": "mention"})
        elif self.path == "/api/config":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                cfg = json.loads(body)
                with open("config/config.json", "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                logger.info("配置已保存")
                self._send_json({"ok": True})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
        else:
            self._send_json({"ok": False}, 404)

    def _send_json(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def log_message(self, fmt, *args):
        pass


def start_web(port: int = 8766):
    """后台启动 Web 控制面板。"""
    srv = HTTPServer(("0.0.0.0", port), WebHandler)
    threading.Thread(target=srv.serve_forever, daemon=True, name="web-panel").start()
    logger.info("Web 控制面板: http://127.0.0.1:%d", port)
