"""ros2-param-editor —— 参数编辑器"""
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
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        return res.stdout.strip()
    except: return ""

def get_nodes():
    out = run_cmd("ros2 node list")
    return [n.strip() for n in out.split('\n') if n.strip()]

def get_params(node):
    out = run_cmd(f"ros2 param list {node}")
    params = []
    for line in out.split('\n'):
        line = line.strip()
        if line and not line.startswith('/'):
            params.append(line)
    return params

def get_param(node, param):
    return run_cmd(f"ros2 param get {node} {param}")

def set_param(node, param, value):
    return run_cmd(f"ros2 param set {node} {param} {value}")

HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body{margin:0;background:#f8fafc;font-family:system-ui}
.container{max-width:800px;margin:20px auto;padding:20px}
h2{color:#334155}
.card{background:#fff;border-radius:12px;padding:20px;box-shadow:0 4px 6px rgba(0,0,0,0.1);margin-bottom:20px}
label{display:block;margin-bottom:5px;color:#475569;font-weight:bold}
select,input{width:100%;padding:8px;border:1px solid #cbd5e1;border-radius:6px;margin-bottom:15px;box-sizing:border-box}
.param-list{max-height:300px;overflow-y:auto;border:1px solid #e2e8f0;border-radius:6px;padding:10px}
.param-item{padding:8px;cursor:pointer;border-radius:4px;margin-bottom:4px}
.param-item:hover{background:#f1f5f9}
.param-item.active{background:#e0f2fe;color:#0369a1}
button{padding:10px 20px;background:#64748b;color:#fff;border:none;border-radius:6px;cursor:pointer;font-weight:bold}
button:hover{background:#475569}
.val-display{background:#f1f5f9;padding:10px;border-radius:6px;font-family:monospace;margin-bottom:15px}
</style>
</head>
<body>
<div class="container">
  <h2>️ ROS2 参数编辑器</h2>
  <div class="card">
    <label>选择节点</label>
    <select id="node" onchange="loadParams()"><option>加载中...</option></select>
    
    <label>参数列表</label>
    <div class="param-list" id="params">请选择节点</div>
  </div>
  
  <div class="card" id="editor" style="display:none">
    <h3 id="param-name">参数名</h3>
    <label>当前值</label>
    <div class="val-display" id="current-val">-</div>
    <label>新值</label>
    <input type="text" id="new-val" placeholder="输入新值 (如 10, 3.14, 'string', true)">
    <button onclick="setVal()">保存修改</button>
  </div>
</div>
<script>
let currentParam='';
async function loadNodes(){
  const res=await fetch('/api/nodes');
  const data=await res.json();
  document.getElementById('node').innerHTML=data.map(n=>`<option value="${n}">${n}</option>`).join('')||'<option>无节点</option>';
}
async function loadParams(){
  const node=document.getElementById('node').value;
  if(!node)return;
  const res=await fetch('/api/params?node='+encodeURIComponent(node));
  const data=await res.json();
  document.getElementById('params').innerHTML=data.map(p=>`<div class="param-item" onclick="selectParam('${p}')">${p}</div>`).join('')||'无参数';
}
async function selectParam(p){
  currentParam=p;
  document.querySelectorAll('.param-item').forEach(el=>el.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById('param-name').textContent=p;
  document.getElementById('editor').style.display='block';
  const node=document.getElementById('node').value;
  const res=await fetch(`/api/get?node=${encodeURIComponent(node)}&param=${encodeURIComponent(p)}`);
  document.getElementById('current-val').textContent=await res.text();
  document.getElementById('new-val').value='';
}
async function setVal(){
  const node=document.getElementById('node').value;
  const val=document.getElementById('new-val').value;
  if(!val)return alert('请输入新值');
  const res=await fetch(`/api/set?node=${encodeURIComponent(node)}&param=${encodeURIComponent(currentParam)}&value=${encodeURIComponent(val)}`);
  const text=await res.text();
  document.getElementById('current-val').textContent=text;
  alert('设置结果: '+text);
}
loadNodes();
setInterval(loadNodes, 5000);
</script>
</body>
</html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/nodes':
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(get_nodes()).encode())
        elif parsed.path.startswith('/api/params'):
            qs = parse_qs(parsed.query)
            node = qs.get('node', [''])[0]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(get_params(node)).encode())
        elif parsed.path.startswith('/api/get'):
            qs = parse_qs(parsed.query)
            node = qs.get('node', [''])[0]
            param = qs.get('param', [''])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(get_param(node, param).encode())
        elif parsed.path.startswith('/api/set'):
            qs = parse_qs(parsed.query)
            node = qs.get('node', [''])[0]
            param = qs.get('param', [''])[0]
            value = qs.get('value', [''])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(set_param(node, param, value).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
    def log_message(self, *a): pass

if __name__ == "__main__":
    print(f"[ROS2 Param Editor] 启动成功，监听端口: {PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()