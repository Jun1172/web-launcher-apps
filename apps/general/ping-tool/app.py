"""ping-tool —— 网络连通性测试"""
import json, os, subprocess, platform
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

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

def do_ping(host):
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    cmd = ['ping', param, '4', host]
    try:
        # Windows 下 ping 输出为 GBK，Linux/Mac 为 UTF-8
        encoding = 'gbk' if platform.system().lower() == 'windows' else 'utf-8'
        res = subprocess.run(cmd, capture_output=True, text=True, encoding=encoding, errors='ignore')
        return res.stdout
    except Exception as e:
        return str(e)

HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body{margin:0;height:100vh;display:flex;justify-content:center;align-items:center;background:#eff6ff;font-family:system-ui}
.box{width:500px;background:#fff;border-radius:16px;box-shadow:0 10px 30px rgba(0,0,0,.1);padding:20px}
h3{margin:0 0 15px;color:#1e3a8a}
input{padding:10px;border:1px solid #bfdbfe;border-radius:8px;width:calc(100% - 90px);box-sizing:border-box}
button{padding:10px;background:#3b82f6;color:#fff;border:none;border-radius:8px;cursor:pointer;font-weight:bold}
pre{background:#f8fafc;padding:15px;border-radius:8px;font-size:12px;max-height:300px;overflow:auto;white-space:pre-wrap}
</style>
</head>
<body>
<div class="box">
  <h3>📡 Ping 工具</h3>
  <input id="host" value="127.0.0.1" placeholder="输入 IP 或域名">
  <button onclick="ping()">Ping</button>
  <pre id="out">等待执行...</pre>
</div>
<script>
async function ping(){
  out.textContent='执行中...';
  const res=await fetch('/api/ping?host='+encodeURIComponent(host.value));
  out.textContent=await res.text();
}
</script>
</body>
</html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/ping':
            qs = parse_qs(parsed.query)
            host = qs.get('host', ['127.0.0.1'])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(do_ping(host).encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
    def log_message(self, *a): pass

if __name__ == "__main__":
    print(f"[Ping Tool] 启动成功，监听端口: {PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()