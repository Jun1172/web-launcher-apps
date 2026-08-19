"""tcp-debug —— TCP 网络调试工具（前后端分离 + 异常捕获修复版）"""
import socket, threading, json, time, os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

PORT = int(os.environ.get("LAUNCHER_APP_PORT", 0))

# 全局状态
state = {
    "mode": None,           # 'server' 或 'client'
    "server_sock": None,
    "client_sock": None,
    "clients": [],          # Server 模式下的客户端连接列表
    "logs": [],
    "lock": threading.Lock(),
    "running": True
}

def add_log(direction, msg):
    with state["lock"]:
        state["logs"].append({"t": time.strftime("%H:%M:%S"), "dir": direction, "msg": msg})
        if len(state["logs"]) > 200: state["logs"].pop(0)

def server_accept_worker():
    """Server 模式：监听并接受新连接"""
    while state["running"] and state["server_sock"]:
        try:
            conn, addr = state["server_sock"].accept()
            state["clients"].append(conn)
            add_log("SYS", f"✅ Client connected: {addr[0]}:{addr[1]}")
            threading.Thread(target=client_recv_worker, args=(conn, addr), daemon=True).start()
        except Exception:
            break

def client_recv_worker(conn, addr):
    """Server 模式：处理单个客户端的数据接收"""
    while state["running"] and conn in state["clients"]:
        try:
            data = conn.recv(4096)
            if not data: break
            add_log("RX", f"[{addr[0]}:{addr[1]}] Hex: {data.hex()} | Text: {data.decode('utf-8', errors='replace')}")
        except Exception:
            break
    if conn in state["clients"]:
        state["clients"].remove(conn)
        try: conn.close()
        except: pass
        add_log("SYS", f"❌ Client disconnected: {addr[0]}:{addr[1]}")

def client_recv_main_worker():
    """Client 模式：主接收线程"""
    while state["running"] and state["client_sock"]:
        try:
            data = state["client_sock"].recv(4096)
            if not data: break
            add_log("RX", f"[Server] Hex: {data.hex()} | Text: {data.decode('utf-8', errors='replace')}")
        except Exception:
            break
    add_log("SYS", "❌ Disconnected from server")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/status":
            with state["lock"]:
                logs_copy = list(state["logs"])
            status = "Idle"
            if state["mode"] == "server": status = f"Server (Listening, {len(state['clients'])} clients)"
            elif state["mode"] == "client": status = "Client (Connected)"
            self._json({"status": status, "logs": logs_copy})
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length).decode('utf-8'))
        except Exception:
            self._json({"ok": False, "err": "Invalid request"})
            return

        if path == "/api/connect":
            self._disconnect_all()
            state["mode"] = body.get("mode")
            try:
                if state["mode"] == "server":
                    state["server_sock"] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    state["server_sock"].setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    state["server_sock"].bind(("0.0.0.0", body.get("port", 8080)))
                    state["server_sock"].listen(5)
                    threading.Thread(target=server_accept_worker, daemon=True).start()
                else:
                    state["client_sock"] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    state["client_sock"].connect((body.get("ip", "127.0.0.1"), body.get("port", 8080)))
                    threading.Thread(target=client_recv_main_worker, daemon=True).start()
                self._json({"ok": True})
            except Exception as e:
                self._json({"ok": False, "err": str(e)})
                
        elif path == "/api/disconnect":
            self._disconnect_all()
            self._json({"ok": True})
            
        elif path == "/api/send":
            try:
                data = bytes.fromhex(body["hex"]) if body.get("isHex") else body["txt"].encode('utf-8')
                if state["mode"] == "server":
                    for c in state["clients"]:
                        try: c.sendall(data)
                        except: pass
                elif state["mode"] == "client" and state["client_sock"]:
                    state["client_sock"].sendall(data)
                add_log("TX", f"-> Hex: {data.hex()} | Text: {body.get('txt', '')}")
                self._json({"ok": True})
            except Exception as e:
                self._json({"ok": False, "err": str(e)})
                
        elif path == "/api/clear":
            with state["lock"]: state["logs"].clear()
            self._json({"ok": True})

    def _disconnect_all(self):
        state["mode"] = None
        if state["server_sock"]:
            try: state["server_sock"].close()
            except: pass
            for c in state["clients"]:
                try: c.close()
                except: pass
            state["clients"].clear()
            state["server_sock"] = None
        if state["client_sock"]:
            try: state["client_sock"].close()
            except: pass
            state["client_sock"] = None

    def _json(self, obj):
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            pass  # 优雅忽略客户端断开错误

    def log_message(self, *a): pass

HTML = r"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>TCP 调试</title>
<style>
body{background:#0b1120;color:#f8fafc;font-family:system-ui;padding:20px;display:flex;gap:20px;height:100vh;box-sizing:border-box;
     background-image:radial-gradient(at 0% 0%,rgba(99,102,241,0.25) 0px,transparent 50%),radial-gradient(at 100% 100%,rgba(236,72,153,0.2) 0px,transparent 50%)}
.panel{flex:1;background:rgba(255,255,255,0.06);backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:20px;display:flex;flex-direction:column}
h2{font-size:16px;margin-bottom:16px;color:#fbbf24}
.row{display:flex;gap:10px;margin-bottom:12px}
input,select,button{background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.1);color:#fff;padding:8px 12px;border-radius:8px;font-size:13px}
button{cursor:pointer;background:#fbbf24;color:#000;border:none;font-weight:600}button:hover{background:#f59e0b}
.log-area{flex:1;background:rgba(0,0,0,0.3);border-radius:8px;padding:10px;overflow-y:auto;font-family:Consolas,monospace;font-size:12px}
.log-item{margin-bottom:6px;padding:6px;border-radius:4px;background:rgba(255,255,255,0.03)}
.rx{border-left:3px solid #34d399}.tx{border-left:3px solid #fbbf24}.sys{border-left:3px solid #94a3b8}
</style></head><body>
<div class="panel">
  <h2>🔌 连接配置</h2>
  <div class="row"><select id="mode"><option value="client">TCP Client</option><option value="server">TCP Server</option></select></div>
  <div class="row"><input id="ip" value="127.0.0.1" placeholder="IP (Client)" style="flex:1"><input id="port" value="8080" placeholder="端口" style="width:100px"></div>
  <div class="row"><button onclick="connect()">连接/监听</button><button onclick="disconnect()" style="background:#f87171;color:#fff">断开</button></div>
  <h2>📤 发送数据</h2>
  <div class="row"><input id="txt" placeholder="文本内容" style="flex:1"><input id="hex" placeholder="Hex (优先)" style="flex:1"><button onclick="send()">发送</button></div>
</div>
<div class="panel">
  <h2>📋 日志 <span id="status" style="float:right;font-size:12px;color:#94a3b8">Idle</span> <button onclick="clearLog()" style="float:right;font-size:12px;padding:4px 8px;margin-right:10px">清空</button></h2>
  <div class="log-area" id="logs"></div>
</div>
<script>
async function api(url, data) { const r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data||{})}); return r.json(); }
async function connect() { const m = document.getElementById('mode').value; await api('/api/connect', {mode: m, ip: document.getElementById('ip').value, port: parseInt(document.getElementById('port').value)}); }
async function disconnect() { await api('/api/disconnect'); }
async function send() { await api('/api/send', {txt: document.getElementById('txt').value, hex: document.getElementById('hex').value, isHex: !!document.getElementById('hex').value}); }
async function clearLog() { await api('/api/clear'); }
async function poll() {
  while(true) {
    try {
      const r = await fetch('/api/status');
      const d = await r.json();
      document.getElementById('status').textContent = d.status;
      document.getElementById('logs').innerHTML = d.logs.map(l => `<div class="log-item ${l.dir.toLowerCase()}"><b>[${l.t}] ${l.dir}</b> ${l.msg}</div>`).join('');
    } catch(e) {}
    await new Promise(r=>setTimeout(r, 1000));
  }
}
poll();
</script></body></html>"""

if __name__ == "__main__":
    print(f"[TCP Debug] http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()