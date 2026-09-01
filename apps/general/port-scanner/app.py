"""port-scanner —— 本机端口与进程扫描"""
import json, os, subprocess, platform
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

def get_port():
    env_port = os.environ.get("LAUNCHER_APP_PORT")
    if env_port:
        try: return int(env_port)
        except ValueError: pass
    app_json_path = Path(__file__).parent / "app.json"
    if app_json_path.exists():
        try:
            config = json.loads(app_json_path.read_text(encoding="utf-8"))
            port = config.get("port") or config.get("port ")
            if port: return int(port)
        except Exception: pass
    return 0

PORT = get_port()

def get_process_name_windows(pid):
    try:
        res = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'], 
                             capture_output=True, text=True, encoding='gbk', errors='ignore')
        if res.stdout:
            return res.stdout.strip().split(',')[0].strip('"')
    except: pass
    return ""

def get_ports():
    ports = []
    try:
        if platform.system() == "Windows":
            out = subprocess.check_output(['netstat', '-ano'], text=True, encoding='gbk', errors='ignore')
            pid_cache = {}
            for line in out.splitlines():
                if 'LISTENING' in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        addr = parts[1]
                        port = addr.rsplit(':', 1)[-1]
                        pid = parts[4]
                        if pid not in pid_cache:
                            pid_cache[pid] = get_process_name_windows(pid)
                        ports.append({"port": port, "addr": addr, "pid": pid, "process": pid_cache[pid]})
        else:
            out = subprocess.check_output(['lsof', '-i', '-P', '-n'], text=True, errors='ignore')
            for line in out.splitlines():
                if 'LISTEN' in line:
                    parts = line.split()
                    if len(parts) >= 9:
                        addr = parts[8]
                        port = addr.rsplit(':', 1)[-1].split()[0]
                        ports.append({"port": port, "addr": addr, "pid": parts[1], "process": parts[0]})
    except Exception: pass
    return ports

HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {
    margin: 0;
    height: 100vh;
    display: flex;
    justify-content: center;
    align-items: center;
    background: #fffbeb;
    font-family: system-ui, -apple-system, sans-serif;
}
.box {
    width: 700px;
    background: #fff;
    border-radius: 16px;
    box-shadow: 0 10px 30px rgba(0,0,0,.1);
    padding: 25px;
}
h3 {
    margin: 0 0 20px;
    color: #92400e;
    font-size: 20px;
}
button {
    padding: 10px 24px;
    background: #f59e0b;
    color: #fff;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-weight: 600;
    margin-bottom: 20px;
    transition: background 0.2s;
}
button:hover {
    background: #d97706;
}
.table-container {
    max-height: 400px;
    overflow-y: auto;
    border-radius: 8px;
    border: 1px solid #fde68a;
}
table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
}
thead {
    background: #fef3c7;
    position: sticky;
    top: 0;
    z-index: 10;
}
th {
    padding: 12px 15px;
    text-align: left;
    color: #92400e;
    font-weight: 600;
    border-bottom: 2px solid #fbbf24;
    white-space: nowrap;
}
td {
    padding: 10px 15px;
    border-bottom: 1px solid #fde68a;
    color: #78350f;
}
tbody tr:hover {
    background: #fffbeb;
}
tbody tr:last-child td {
    border-bottom: none;
}
.loading {
    text-align: center;
    padding: 20px;
    color: #92400e;
}
</style>
</head>
<body>
<div class="box">
  <h3>🔌 本机端口扫描</h3>
  <button onclick="scan()">扫描监听端口</button>
  <div class="table-container">
    <table>
      <thead>
        <tr>
          <th style="width: 80px;">端口</th>
          <th style="width: 180px;">本地地址</th>
          <th style="width: 80px;">PID</th>
          <th>进程/服务</th>
        </tr>
      </thead>
      <tbody id="list"></tbody>
    </table>
  </div>
</div>
<script>
async function scan(){
  list.innerHTML = '<tr><td colspan="4" class="loading">扫描中...</td></tr>';
  try {
    const res = await fetch('/api/ports');
    const data = await res.json();
    if (data.length === 0) {
      list.innerHTML = '<tr><td colspan="4" class="loading">未发现监听端口</td></tr>';
    } else {
      list.innerHTML = data.map(p => 
        '<tr>' +
          '<td><strong>' + p.port + '</strong></td>' +
          '<td>' + p.addr + '</td>' +
          '<td>' + p.pid + '</td>' +
          '<td>' + (p.process || '-') + '</td>' +
        '</tr>'
      ).join('');
    }
  } catch(e) {
    list.innerHTML = '<tr><td colspan="4" class="loading" style="color:#ef4444">扫描失败</td></tr>';
  }
}
scan();
</script>
</body>
</html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/ports':
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(get_ports(), ensure_ascii=False).encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
    def log_message(self, *a): pass

if __name__ == "__main__":
    print(f"[Port Scanner] 启动成功，监听端口: {PORT}")
    ThreadingHTTPServer((os.environ.get("APP_HOST", "127.0.0.1"), PORT), H).serve_forever()