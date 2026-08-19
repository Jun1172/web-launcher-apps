"""udp-debug —— UDP 网络调试工具（前后端分离）"""
import socket, threading, json, time, os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

PORT = int(os.environ.get("LAUNCHER_APP_PORT", 0))
state = {"sock": None, "thread": None, "logs": [], "lock": threading.Lock()}

def udp_worker():
    while state["sock"]:
        try:
            data, addr = state["sock"].recvfrom(65535)
            log = {"t": time.strftime("%H:%M:%S"), "dir": "RX", "addr": f"{addr[0]}:{addr[1]}", 
                   "hex": data.hex(), "txt": data.decode('utf-8', errors='replace')}
            with state["lock"]:
                state["logs"].append(log)
                if len(state["logs"]) > 100: state["logs"].pop(0)
        except: break

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/logs":
            with state["lock"]:
                logs = list(state["logs"])
            self._json({"logs": logs})
        elif path == "/api/status":
            self._json({"running": state["sock"] is not None, "port": int(state["sock"].getsockname()[1]) if state["sock"] else 0})
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
        except:
            self._json({"ok": False, "err": "Invalid request"})
            return
            
        if path == "/api/start":
            if state["sock"]: state["sock"].close()
            state["sock"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            state["sock"].setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            state["sock"].bind(("0.0.0.0", body.get("port", 9999)))
            state["thread"] = threading.Thread(target=udp_worker, daemon=True)
            state["thread"].start()
            self._json({"ok": True})
        elif path == "/api/stop":
            if state["sock"]: state["sock"].close()
            state["sock"] = None
            self._json({"ok": True})
        elif path == "/api/send":
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                data = bytes.fromhex(body["hex"]) if body.get("isHex") else body["txt"].encode()
                s.sendto(data, (body["ip"], body["port"]))
                log = {"t": time.strftime("%H:%M:%S"), "dir": "TX", "addr": f"{body['ip']}:{body['port']}", 
                       "hex": data.hex(), "txt": body.get("txt","")}
                with state["lock"]:
                    state["logs"].append(log)
                s.close()
                self._json({"ok": True})
            except Exception as e:
                self._json({"ok": False, "err": str(e)})
        elif path == "/api/clear":
            with state["lock"]:
                state["logs"].clear()
            self._json({"ok": True})

    def _json(self, obj):
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            pass  # 忽略客户端断开错误
    def log_message(self, *a): pass

HTML = r"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>UDP 调试</title>
<style>
body{background:#0b1120;color:#f8fafc;font-family:system-ui;padding:20px;display:flex;gap:20px;height:100vh;box-sizing:border-box}
.panel{flex:1;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:20px;display:flex;flex-direction:column}
h2{font-size:16px;margin-bottom:16px;color:#34d399}
.row{display:flex;gap:10px;margin-bottom:12px}
input,button{background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.1);color:#fff;padding:8px 12px;border-radius:8px;font-size:13px}
button{cursor:pointer;background:#34d399;color:#000;border:none;font-weight:600}button:hover{background:#10b981}
.log-area{flex:1;background:rgba(0,0,0,0.3);border-radius:8px;padding:10px;overflow-y:auto;font-family:Consolas,monospace;font-size:12px}
.log-item{margin-bottom:6px;padding:6px;border-radius:4px;background:rgba(255,255,255,0.03)}
.rx{border-left:3px solid #34d399}.tx{border-left:3px solid #fbbf24}
</style></head><body>
<div class="panel">
  <h2>⚙️ 监听配置</h2>
  <div class="row"><input id="lPort" value="9999" placeholder="监听端口" style="flex:1"><button onclick="start()">开始监听</button><button onclick="stop()" style="background:#f87171">停止</button></div>
  <h2>📤 发送数据</h2>
  <div class="row"><input id="sIp" value="127.0.0.1" style="flex:1"><input id="sPort" value="9998" style="width:80px"></div>
  <div class="row"><input id="sTxt" placeholder="文本内容" style="flex:1"><input id="sHex" placeholder="Hex (优先)" style="flex:1"><button onclick="send()">发送</button></div>
</div>
<div class="panel">
  <h2>📋 通信日志 <button onclick="clearLog()" style="float:right;font-size:12px;padding:4px 8px">清空</button></h2>
  <div class="log-area" id="logs"></div>
</div>
<script>
async function api(url, data) {
  const r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data||{})});
  return r.json();
}
async function start() { await api('/api/start', {port: parseInt(document.getElementById('lPort').value)}); poll(); }
async function stop() { await api('/api/stop'); }
async function send() { await api('/api/send', {ip: document.getElementById('sIp').value, port: parseInt(document.getElementById('sPort').value), txt: document.getElementById('sTxt').value, hex: document.getElementById('sHex').value, isHex: !!document.getElementById('sHex').value}); }
async function clearLog() { await api('/api/clear'); }
async function poll() {
  while(true) {
    try {
      const r = await fetch('/api/logs');
      const d = await r.json();
      document.getElementById('logs').innerHTML = d.logs.map(l => 
        `<div class="log-item ${l.dir.toLowerCase()}"><b>[${l.t}] ${l.dir}</b> ${l.addr}<br>HEX: ${l.hex}<br>TXT: ${l.txt}</div>`
      ).join('');
    } catch(e) {}
    await new Promise(r=>setTimeout(r, 1000));
  }
}
poll();
</script></body></html>"""

if __name__ == "__main__":
    print(f"[UDP Debug] http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()