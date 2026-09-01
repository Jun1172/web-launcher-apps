"""tcp-debug —— TCP 网络调试工具（高健壮性版 + UI 修复）"""
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
        if len(state["logs"]) > 200: 
            state["logs"].pop(0)

def server_accept_worker():
    """Server 模式：监听并接受新连接"""
    while state["running"] and state["server_sock"]:
        try:
            conn, addr = state["server_sock"].accept()
            with state["lock"]:
                state["clients"].append(conn)
            add_log("SYS", f"✅ Client connected: {addr[0]}:{addr[1]}")
            threading.Thread(target=client_recv_worker, args=(conn, addr), daemon=True).start()
        except OSError:
            break  # Socket 被正常关闭
        except Exception:
            break

def client_recv_worker(conn, addr):
    """Server 模式：处理单个客户端的数据接收"""
    while state["running"]:
        try:
            data = conn.recv(4096)
            if not data: break
            add_log("RX", f"[{addr[0]}:{addr[1]}] Hex: {data.hex()} | Text: {data.decode('utf-8', errors='replace')}")
        except Exception:
            break
    
    # 清理断开的连接
    with state["lock"]:
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
                mode = state["mode"]
                clients_count = len(state["clients"])
            
            status = "Idle"
            if mode == "server": 
                status = f"Server (Listening, {clients_count} clients)"
            elif mode == "client": 
                status = "Client (Connected)"
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
            body = json.loads(self.rfile.read(length).decode('utf-8')) if length > 0 else {}
        except Exception:
            self._json({"ok": False, "err": "Invalid request"})
            return

        try:
            if path == "/api/connect":
                self._disconnect_all()
                state["mode"] = body.get("mode")
                
                if state["mode"] == "server":
                    state["server_sock"] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    state["server_sock"].setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    
                    req_port = body.get("port")
                    try:
                        listen_port = int(req_port) if req_port is not None else 8080
                    except (ValueError, TypeError):
                        listen_port = 8080
                        
                    state["server_sock"].bind(("0.0.0.0", listen_port))
                    state["server_sock"].listen(5)
                    threading.Thread(target=server_accept_worker, daemon=True).start()
                    
                elif state["mode"] == "client":
                    ip = body.get("ip", "127.0.0.1").strip()
                    req_port = body.get("port")
                    try:
                        target_port = int(req_port)
                    except (ValueError, TypeError):
                        raise ValueError("Invalid target port")
                        
                    state["client_sock"] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    state["client_sock"].connect((ip, target_port))
                    threading.Thread(target=client_recv_main_worker, daemon=True).start()
                    
                self._json({"ok": True})
                
            elif path == "/api/disconnect":
                self._disconnect_all()
                self._json({"ok": True})
                
            elif path == "/api/send":
                is_hex = body.get("isHex", False)
                if is_hex:
                    # 自动清理用户粘贴的 Hex 字符串中的空格和换行
                    hex_str = body.get("hex", "").replace(" ", "").replace("\n", "").replace("\r", "")
                    if not hex_str:
                        raise ValueError("Hex data is empty")
                    data = bytes.fromhex(hex_str)
                else:
                    data = body.get("txt", "").encode('utf-8')
                    
                if state["mode"] == "server":
                    with state["lock"]:
                        clients_snapshot = list(state["clients"])
                    for c in clients_snapshot:
                        try: c.sendall(data)
                        except: pass
                elif state["mode"] == "client" and state["client_sock"]:
                    state["client_sock"].sendall(data)
                else:
                    raise RuntimeError("Not connected")
                    
                add_log("TX", f"-> Hex: {data.hex()} | Text: {body.get('txt', '') if not is_hex else '[HEX]'}")
                self._json({"ok": True})
                
            elif path == "/api/clear":
                with state["lock"]: 
                    state["logs"].clear()
                self._json({"ok": True})
            else:
                self._json({"ok": False, "err": "Unknown path"})
                
        except Exception as e:
            self._json({"ok": False, "err": str(e)})

    def _disconnect_all(self):
        state["mode"] = None
        if state["server_sock"]:
            try: state["server_sock"].close()
            except: pass
            with state["lock"]:
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

HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>TCP 调试助手</title>
<style>
body{background:#0b1120;color:#f8fafc;font-family:system-ui;padding:20px;display:flex;gap:20px;height:100vh;box-sizing:border-box;margin:0;
     background-image:radial-gradient(at 0% 0%,rgba(99,102,241,0.25) 0px,transparent 50%),radial-gradient(at 100% 100%,rgba(236,72,153,0.2) 0px,transparent 50%)}
.panel{flex:1;background:rgba(255,255,255,0.06);backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:20px;display:flex;flex-direction:column}
h2{font-size:16px;margin:0 0 16px 0;color:#fbbf24;display:flex;justify-content:space-between;align-items:center}
.row{display:flex;gap:10px;margin-bottom:12px;align-items:center}
input,button{background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.1);color:#fff;padding:8px 12px;border-radius:8px;font-size:13px;outline:none}
input:focus{border-color:#fbbf24}

/* 【核心修复】强制下拉框及选项使用深色背景和白色文字 */
select {
    background-color: #1e293b; /* 实色深色背景，避免半透明导致的渲染问题 */
    color: #fff;
    border: 1px solid rgba(255,255,255,0.1);
    padding: 8px 30px 8px 12px;
    border-radius: 8px;
    font-size: 13px;
    outline: none;
    cursor: pointer;
    appearance: none; /* 移除浏览器默认样式 */
    -webkit-appearance: none;
    -moz-appearance: none;
    /* 自定义白色下拉箭头 */
    background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e");
    background-repeat: no-repeat;
    background-position: right 10px center;
    background-size: 16px;
}
select:focus {
    border-color: #fbbf24;
}
/* 强制下拉选项也是深色背景+白字 */
select option {
    background-color: #1e293b;
    color: #fff;
}

button{cursor:pointer;background:#fbbf24;color:#000;border:none;font-weight:600;transition:all 0.2s}
button:hover{background:#f59e0b}
button:disabled{opacity:0.5;cursor:not-allowed}
button.danger{background:#f87171;color:#fff}
button.danger:hover{background:#ef4444}
.log-area{flex:1;background:rgba(0,0,0,0.3);border-radius:8px;padding:10px;overflow-y:auto;font-family:Consolas,monospace;font-size:12px}
.log-item{margin-bottom:6px;padding:8px;border-radius:6px;background:rgba(255,255,255,0.03);word-break:break-all}
.rx{border-left:3px solid #34d399}
.tx{border-left:3px solid #fbbf24}
.sys{border-left:3px solid #94a3b8}
.status{font-size:12px;color:#94a3b8}
.status.on{color:#34d399}
.checkbox-label{display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;white-space:nowrap}
input[type="checkbox"]{width:16px;height:16px;accent-color:#fbbf24}
</style>
</head>
<body>
<div class="panel">
  <h2>🔌 连接配置 <span id="status" class="status">Idle</span></h2>
  <div class="row">
    <select id="mode" style="flex:1">
      <option value="client">TCP Client</option>
      <option value="server">TCP Server</option>
    </select>
  </div>
  <div class="row">
    <input id="ip" value="127.0.0.1" placeholder="目标 IP (Client)" style="flex:2">
    <input id="port" value="8080" placeholder="端口" style="flex:1">
  </div>
  <div class="row">
    <button id="btnConnect" onclick="connect()">连接/监听</button>
    <button id="btnDisconnect" class="danger" onclick="disconnect()" disabled>断开</button>
  </div>
  
  <h2 style="margin-top:20px">📤 发送数据</h2>
  <div class="row">
    <label class="checkbox-label"><input type="checkbox" id="isHex"> 发送 Hex 格式</label>
  </div>
  <div class="row">
    <input id="txt" placeholder="文本内容 (Text)" style="flex:1">
  </div>
  <div class="row">
    <input id="hex" placeholder="Hex 内容 (如: 01 02 0A)" style="flex:1" disabled>
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
    const btnConnect = document.getElementById('btnConnect');
    const btnDisconnect = document.getElementById('btnDisconnect');
    const modeSelect = document.getElementById('mode');
    const ipInput = document.getElementById('ip');
    const portInput = document.getElementById('port');
    
    statusEl.textContent = d.status;
    const isIdle = d.status === "Idle";
    
    btnConnect.disabled = !isIdle;
    btnDisconnect.disabled = isIdle;
    modeSelect.disabled = !isIdle;
    ipInput.disabled = !isIdle;
    portInput.disabled = !isIdle;
    
    if (!isIdle) {
      statusEl.className = 'status on';
    } else {
      statusEl.className = 'status';
    }
  } catch(e) {}
}

async function connect() {
  const mode = document.getElementById('mode').value;
  const ip = document.getElementById('ip').value.trim();
  const port = parseInt(document.getElementById('port').value);
  
  if (!port || port < 1 || port > 65535) {
    alert('请输入有效的端口 (1-65535)');
    return;
  }
  if (mode === 'client' && !ip) {
    alert('请输入目标 IP');
    return;
  }
  
  const res = await api('/api/connect', {mode, ip, port});
  if (res.ok) {
    updateStatus();
    if (!isPolling) {
      isPolling = true;
      poll();
    }
  }
}

async function disconnect() {
  const res = await api('/api/disconnect');
  if (res.ok) updateStatus();
}

async function send() {
  const isHex = document.getElementById('isHex').checked;
  let txt = "", hex = "";
  
  if (isHex) {
    hex = document.getElementById('hex').value.trim();
    if (!hex) { alert('请输入 Hex 数据'); return; }
  } else {
    txt = document.getElementById('txt').value;
  }

  const res = await api('/api/send', {txt, hex, isHex});
  if (res.ok) {
    // 【保留输入内容】：不进行清空，方便连续发送
    fetchLogs(); // 发送后立即刷新日志
  }
}

async function clearLog() {
  await api('/api/clear');
  fetchLogs();
}

async function fetchLogs() {
  try {
    const r = await fetch('/api/status'); // 复用 status 接口获取最新日志
    const d = await r.json();
    const logsEl = document.getElementById('logs');
    
    logsEl.innerHTML = d.logs.map(l => 
      `<div class="log-item ${l.dir.toLowerCase()}">
        <div style="display:flex;justify-content:space-between;color:#94a3b8;font-size:11px;margin-bottom:4px">
          <span><b>[${l.dir}]</b></span>
          <span>${l.t}</span>
        </div>
        <div style="color:#e2e8f0">${l.msg}</div>
      </div>`
    ).join('');
    
    // 自动滚动到底部
    logsEl.scrollTop = logsEl.scrollHeight;
  } catch(e) {}
}

async function poll() {
  while(isPolling) {
    await updateStatus();
    await fetchLogs();
    await new Promise(r => setTimeout(r, 1000));
  }
}

// Hex 复选框联动
document.getElementById('isHex').addEventListener('change', function() {
  document.getElementById('txt').disabled = this.checked;
  document.getElementById('hex').disabled = !this.checked;
  if (this.checked) document.getElementById('hex').focus();
  else document.getElementById('txt').focus();
});

// 初始化
updateStatus();
fetchLogs();
isPolling = true;
poll();
</script>
</body>
</html>"""

if __name__ == "__main__":
    print(f"[TCP Debug] 启动成功，监听端口: {PORT}")
    ThreadingHTTPServer((os.environ.get("APP_HOST", "127.0.0.1"), PORT), Handler).serve_forever()