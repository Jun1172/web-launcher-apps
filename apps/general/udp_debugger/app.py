"""udp-debug —— UDP 网络调试工具（高健壮性版）"""
import socket, threading, json, time, os
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

def get_port():
    """优先级: 环境变量 > app.json > 0(系统随机)"""
    env_port = os.environ.get("LAUNCHER_APP_PORT")
    if env_port:
        try: return int(env_port)
        except ValueError: pass
    
    app_json_path = Path(__file__).parent / "app.json"
    if app_json_path.exists():
        try:
            config = json.loads(app_json_path.read_text(encoding="utf-8"))
            # 兼容处理：防止 json 中键名带有意外空格
            port = config.get("port") or config.get("port ")
            if port: return int(port)
        except Exception: pass
    return 0

PORT = get_port()
state = {"sock": None, "thread": None, "logs": [], "lock": threading.Lock()}

def udp_worker():
    while state["sock"]:
        try:
            data, addr = state["sock"].recvfrom(65535)
            log = {
                "t": time.strftime("%H:%M:%S"), 
                "dir": "RX", 
                "addr": f"{addr[0]}:{addr[1]}", 
                "hex": data.hex(), 
                "txt": data.decode('utf-8', errors='replace')
            }
            with state["lock"]:
                state["logs"].append(log)
                if len(state["logs"]) > 100: 
                    state["logs"].pop(0)
        except OSError:
            break  # Socket 被正常关闭
        except Exception:
            break

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/logs":
            with state["lock"]:
                logs = list(state["logs"])
            self._json({"logs": logs})
        elif path == "/api/status":
            with state["lock"]:
                is_running = state["sock"] is not None
                port = int(state["sock"].getsockname()[1]) if is_running else 0
            self._json({"running": is_running, "port": port})
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length).decode('utf-8')) if length > 0 else {}
        except Exception as e:
            self._json({"ok": False, "err": f"Invalid request: {str(e)}"})
            return
            
        try:
            if path == "/api/start":
                with state["lock"]:
                    if state["sock"]: 
                        state["sock"].close()
                        state["sock"] = None
                    state["sock"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    state["sock"].setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    
                    req_port = body.get("port")
                    try:
                        listen_port = int(req_port) if req_port is not None else 9999
                    except (ValueError, TypeError):
                        listen_port = 9999
                        
                    state["sock"].bind(("0.0.0.0", listen_port))
                    state["thread"] = threading.Thread(target=udp_worker, daemon=True)
                    state["thread"].start()
                self._json({"ok": True, "port": listen_port})
                
            elif path == "/api/stop":
                with state["lock"]:
                    if state["sock"]: 
                        state["sock"].close()
                        state["sock"] = None
                self._json({"ok": True})
                
            elif path == "/api/send":
                ip = body.get("ip", "127.0.0.1").strip()
                req_port = body.get("port")
                try:
                    target_port = int(req_port)
                except (ValueError, TypeError):
                    raise ValueError("Invalid target port")
                    
                is_hex = body.get("isHex", False)
                if is_hex:
                    hex_str = body.get("hex", "").replace(" ", "").replace("\n", "").replace("\r", "")
                    if not hex_str:
                        raise ValueError("Hex data is empty")
                    data = bytes.fromhex(hex_str)
                else:
                    data = body.get("txt", "").encode('utf-8')
                    
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.sendto(data, (ip, target_port))
                
                log = {
                    "t": time.strftime("%H:%M:%S"), 
                    "dir": "TX", 
                    "addr": f"{ip}:{target_port}", 
                    "hex": data.hex(), 
                    "txt": body.get("txt", "") if not is_hex else f"[HEX: {hex_str}]"
                }
                with state["lock"]:
                    state["logs"].append(log)
                    if len(state["logs"]) > 100: 
                        state["logs"].pop(0)
                s.close()
                self._json({"ok": True})
                
            elif path == "/api/clear":
                with state["lock"]:
                    state["logs"].clear()
                self._json({"ok": True})
            else:
                self._json({"ok": False, "err": "Unknown path"})
        except Exception as e:
            self._json({"ok": False, "err": str(e)})

    def _json(self, obj):
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            pass
            
    def log_message(self, *a): pass

HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>UDP 调试助手</title>
<style>
body{background:#0b1120;color:#f8fafc;font-family:system-ui;padding:20px;display:flex;gap:20px;height:100vh;box-sizing:border-box;margin:0}
.panel{flex:1;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:20px;display:flex;flex-direction:column}
h2{font-size:16px;margin:0 0 16px 0;color:#34d399;display:flex;justify-content:space-between;align-items:center}
.row{display:flex;gap:10px;margin-bottom:12px;align-items:center}
input,button{background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.1);color:#fff;padding:8px 12px;border-radius:8px;font-size:13px;outline:none}
input:focus{border-color:#34d399}
button{cursor:pointer;background:#34d399;color:#000;border:none;font-weight:600;transition:all 0.2s}
button:hover{background:#10b981}
button:disabled{opacity:0.5;cursor:not-allowed}
button.danger{background:#f87171;color:#fff}
button.danger:hover{background:#ef4444}
.log-area{flex:1;background:rgba(0,0,0,0.3);border-radius:8px;padding:10px;overflow-y:auto;font-family:Consolas,monospace;font-size:12px}
.log-item{margin-bottom:6px;padding:8px;border-radius:6px;background:rgba(255,255,255,0.03);word-break:break-all}
.rx{border-left:3px solid #34d399}
.tx{border-left:3px solid #fbbf24}
.status{font-size:12px;color:#94a3b8}
.status.on{color:#34d399}
.checkbox-label{display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;white-space:nowrap}
input[type="checkbox"]{width:16px;height:16px;accent-color:#34d399}
</style>
</head>
<body>
<div class="panel">
  <h2>⚙️ 监听配置 <span id="status" class="status">未运行</span></h2>
  <div class="row">
    <input id="lPort" value="9999" placeholder="监听端口" style="flex:1">
    <button id="btnStart" onclick="start()">开始监听</button>
    <button id="btnStop" class="danger" onclick="stop()" disabled>停止</button>
  </div>
  
  <h2 style="margin-top:20px">📤 发送数据</h2>
  <div class="row">
    <input id="sIp" value="127.0.0.1" placeholder="目标 IP" style="flex:2">
    <input id="sPort" value="9999" placeholder="端口" style="flex:1">
  </div>
  <div class="row">
    <label class="checkbox-label"><input type="checkbox" id="isHex"> 发送 Hex 格式</label>
  </div>
  <div class="row">
    <input id="sTxt" placeholder="文本内容 (Text)" style="flex:1">
  </div>
  <div class="row">
    <input id="sHex" placeholder="Hex 内容 (如: 01 02 0A)" style="flex:1" disabled>
    <button onclick="send()">发送</button>
  </div>
</div>

<div class="panel">
  <h2>📋 通信日志 <button onclick="clearLog()" style="font-size:12px;padding:4px 10px;background:rgba(255,255,255,0.1);color:#fff">清空</button></h2>
  <div class="log-area" id="logs"></div>
</div>

<script>
let isPolling = false;

async function api(url, data) {
  try {
    const r = await fetch(url, {
      method: 'POST', 
      headers: {'Content-Type': 'application/json'}, 
      body: JSON.stringify(data || {})
    });
    const res = await r.json();
    if (!res.ok) {
      alert('操作失败: ' + (res.err || 'Unknown error'));
    }
    return res;
  } catch (e) {
    alert('网络请求失败: ' + e.message);
    return {ok: false};
  }
}

async function updateStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    const statusEl = document.getElementById('status');
    const btnStart = document.getElementById('btnStart');
    const btnStop = document.getElementById('btnStop');
    const lPort = document.getElementById('lPort');
    
    if (d.running) {
      statusEl.textContent = `运行中 (端口: ${d.port})`;
      statusEl.className = 'status on';
      btnStart.disabled = true;
      btnStop.disabled = false;
      lPort.disabled = true;
    } else {
      statusEl.textContent = '未运行';
      statusEl.className = 'status';
      btnStart.disabled = false;
      btnStop.disabled = true;
      lPort.disabled = false;
    }
  } catch(e) {}
}

async function start() {
  const port = parseInt(document.getElementById('lPort').value);
  if (!port || port < 1 || port > 65535) {
    alert('请输入有效的监听端口 (1-65535)');
    return;
  }
  const res = await api('/api/start', {port: port});
  if (res.ok) {
    updateStatus();
    if (!isPolling) {
      isPolling = true;
      poll();
    }
  }
}

async function stop() {
  const res = await api('/api/stop');
  if (res.ok) updateStatus();
}

async function send() {
  const isHex = document.getElementById('isHex').checked;
  const ip = document.getElementById('sIp').value.trim();
  const port = parseInt(document.getElementById('sPort').value);
  
  if (!ip) { alert('请输入目标 IP'); return; }
  if (!port || port < 1 || port > 65535) { alert('请输入有效的目标端口'); return; }
  
  let txt = "", hex = "";
  if (isHex) {
    hex = document.getElementById('sHex').value.trim();
    if (!hex) { alert('请输入 Hex 数据'); return; }
  } else {
    txt = document.getElementById('sTxt').value;
  }

  const res = await api('/api/send', {ip, port, txt, hex, isHex});
  if (res.ok) {
    // 【修改点】：移除了清空输入框的逻辑，保留用户输入以便连续发送
    fetchLogs(); // 发送后立即刷新日志
  }
}

async function clearLog() {
  await api('/api/clear');
  fetchLogs();
}

async function fetchLogs() {
  try {
    const r = await fetch('/api/logs');
    const d = await r.json();
    const logsEl = document.getElementById('logs');
    logsEl.innerHTML = d.logs.map(l => 
      `<div class="log-item ${l.dir.toLowerCase()}">
        <div style="display:flex;justify-content:space-between;color:#94a3b8;font-size:11px;margin-bottom:4px">
          <span><b>[${l.dir}]</b> ${l.addr}</span>
          <span>${l.t}</span>
        </div>
        <div style="color:#e2e8f0">TXT: ${l.txt || '(empty)'}</div>
        <div style="color:#64748b;font-size:11px;margin-top:2px">HEX: ${l.hex}</div>
      </div>`
    ).join('');
    logsEl.scrollTop = logsEl.scrollHeight;
  } catch(e) {}
}

async function poll() {
  while(isPolling) {
    await fetchLogs();
    await new Promise(r => setTimeout(r, 1000));
  }
}

document.getElementById('isHex').addEventListener('change', function() {
  document.getElementById('sTxt').disabled = this.checked;
  document.getElementById('sHex').disabled = !this.checked;
  if (this.checked) document.getElementById('sHex').focus();
  else document.getElementById('sTxt').focus();
});

updateStatus();
fetchLogs();
isPolling = true;
poll();
</script>
</body>
</html>"""

if __name__ == "__main__":
    print(f"[UDP Debug] 启动成功，监听端口: {PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()