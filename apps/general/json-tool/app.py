"""json-tool —— JSON 格式化与校验"""
import json, os
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

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
HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body{margin:0;height:100vh;display:flex;justify-content:center;align-items:center;background:#f0fdf4;font-family:system-ui}
.box{width:600px;background:#fff;border-radius:16px;box-shadow:0 10px 30px rgba(0,0,0,.1);padding:20px}
h3{margin:0 0 15px;color:#065f46}
textarea{width:100%;height:200px;border:1px solid #d1fae5;border-radius:8px;padding:10px;font-family:monospace;font-size:14px;box-sizing:border-box}
.btns{margin:15px 0;display:flex;gap:10px}
button{padding:8px 16px;border:none;border-radius:6px;cursor:pointer;font-weight:bold}
.val{background:#f59e0b;color:#fff}
.fmt{background:#10b981;color:#fff}
.cmp{background:#3b82f6;color:#fff}
.status{font-size:14px;font-weight:bold;min-height:20px}
</style>
</head>
<body>
<div class="box">
  <h3>{ } JSON 格式化与校验</h3>
  <textarea id="input" placeholder="在此输入 JSON..."></textarea>
  <div class="btns">
    <button class="val" onclick="validate()">校验</button>
    <button class="fmt" onclick="format()">格式化</button>
    <button class="cmp" onclick="compress()">压缩</button>
  </div>
  <div class="status" id="status"></div>
</div>
<script>
const inputEl = document.getElementById('input');
const statusEl = document.getElementById('status');

function validate() {
  try {
    JSON.parse(inputEl.value);
    statusEl.textContent = '✅ JSON 格式完全正确';
    statusEl.style.color = '#10b981';
  } catch (e) {
    statusEl.textContent = '❌ 格式错误: ' + e.message;
    statusEl.style.color = '#ef4444';
  }
}
function format(){
  try{
    const obj=JSON.parse(inputEl.value);
    inputEl.value=JSON.stringify(obj,null,2);
    statusEl.textContent='✅ 校验通过，已格式化';statusEl.style.color='#10b981';
  }catch(e){statusEl.textContent='❌ '+e.message;statusEl.style.color='#ef4444';}
}
function compress(){
  try{
    const obj=JSON.parse(inputEl.value);
    inputEl.value=JSON.stringify(obj);
    statusEl.textContent='✅ 校验通过，已压缩';statusEl.style.color='#10b981';
  }catch(e){statusEl.textContent='❌ '+e.message;statusEl.style.color='#ef4444';}
}
</script>
</body>
</html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML.encode("utf-8"))
    def log_message(self, *a): pass

if __name__ == "__main__":
    print(f"[JSON Tool] 启动成功，监听端口: {PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()