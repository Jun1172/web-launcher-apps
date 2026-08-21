"""ros2-service-caller —— 服务调用工具"""
import json, os, subprocess
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

def run_cmd(cmd):
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return res.stdout.strip()
    except: return ""

def get_services():
    out = run_cmd("ros2 service list")
    return [s.strip() for s in out.split('\n') if s.strip()]

def get_service_type(name):
    return run_cmd(f"ros2 service type {name}")

def call_service(name, req_type, args):
    cmd = f'ros2 service call {name} {req_type} "{args}"'
    return run_cmd(cmd)

HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body{margin:0;background:#fffbeb;font-family:system-ui}
.container{max-width:800px;margin:20px auto;padding:20px}
h2{color:#92400e}
.card{background:#fff;border-radius:12px;padding:20px;box-shadow:0 4px 6px rgba(0,0,0,0.1);margin-bottom:20px}
label{display:block;margin-bottom:5px;color:#78350f;font-weight:bold}
select,input,textarea{width:100%;padding:8px;border:1px solid #fde68a;border-radius:6px;margin-bottom:15px;box-sizing:border-box;font-family:monospace}
textarea{height:100px}
button{padding:10px 20px;background:#f59e0b;color:#fff;border:none;border-radius:6px;cursor:pointer;font-weight:bold}
button:hover{background:#d97706}
.result{background:#f8fafc;padding:15px;border-radius:6px;font-family:monospace;white-space:pre-wrap;min-height:50px}
.tip{background:#fffbeb;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:13px;line-height:1.7;color:#78350f}
.tip code{background:#fef3c7;padding:2px 6px;border-radius:4px;font-family:monospace;color:#92400e}
.tip a{color:#2563eb;text-decoration:none}
.tip a:hover{text-decoration:underline}
</style>
</head>
<body>
<div class="container">
  <h2>📞 ROS2 服务调用器</h2>
  <div class="tip"><strong>💡 使用提示：</strong>没有服务可调用？请先启动服务：执行 <code>ros2 run demo_nodes_cpp add_two_ints_server</code>，或打开 <a href="http://127.0.0.1:8200/" target="_blank">ROS2 演示节点</a> 启动「服务服务器」。请求参数示例：<code>{a: 5, b: 3}</code>（YAML 格式）。</div>
  <div class="card">
    <label>选择服务</label>
    <select id="service" onchange="loadType()"><option value="">加载中...</option></select>
    
    <label>服务类型</label>
    <input type="text" id="type" readonly>
    
    <label>请求参数 (YAML/JSON)</label>
    <textarea id="args" placeholder="{ } 或 空"></textarea>
    
    <button onclick="call()">调用服务</button>
  </div>
  
  <div class="card">
    <label>响应结果</label>
    <div class="result" id="result">等待调用...</div>
  </div>
</div>
<script>
async function loadServices(){
  const res=await fetch('/api/services');
  const data=await res.json();
  const sel=document.getElementById('service');
  sel.innerHTML='<option value="">选择服务...</option>'+data.map(s=>`<option value="${s}">${s}</option>`).join('');
}
async function loadType(){
  const name=document.getElementById('service').value;
  if(!name){document.getElementById('type').value='';return;}
  const res=await fetch('/api/type?name='+encodeURIComponent(name));
  document.getElementById('type').value=await res.text();
}
async function call(){
  const name=document.getElementById('service').value;
  const type=document.getElementById('type').value;
  const args=document.getElementById('args').value||'{}';
  if(!name||!type)return alert('请选择服务');
  document.getElementById('result').textContent='调用中...';
  const res=await fetch(`/api/call?name=${encodeURIComponent(name)}&type=${encodeURIComponent(type)}&args=${encodeURIComponent(args)}`);
  document.getElementById('result').textContent=await res.text();
}
loadServices();
</script>
</body>
</html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/services':
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(get_services()).encode())
        elif parsed.path.startswith('/api/type'):
            qs = parse_qs(parsed.query)
            name = qs.get('name', [''])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(get_service_type(name).encode())
        elif parsed.path.startswith('/api/call'):
            qs = parse_qs(parsed.query)
            name = qs.get('name', [''])[0]
            stype = qs.get('type', [''])[0]
            args = qs.get('args', ['{}'])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(call_service(name, stype, args).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
    def log_message(self, *a): pass

if __name__ == "__main__":
    print(f"[ROS2 Service Caller] 启动成功，监听端口: {PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()