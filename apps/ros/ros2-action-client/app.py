"""ros2-action-client —— 动作执行器"""
import json, os, subprocess, threading, time
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

active_goals = {}

def run_cmd(cmd):
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        return res.stdout.strip()
    except: return ""

def get_actions():
    out = run_cmd("ros2 action list")
    return [a.strip() for a in out.split('\n') if a.strip()]

def get_action_type(name):
    return run_cmd(f"ros2 action type {name}")

def send_goal(name, action_type, args):
    goal_id = f"goal_{int(time.time())}"
    active_goals[goal_id] = {"status": "running", "log": []}
    
    def worker():
        try:
            cmd = f'ros2 action send_goal {name} {action_type} "{args}" --feedback'
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for line in proc.stdout:
                if goal_id in active_goals:
                    active_goals[goal_id]["log"].append(line.strip())
                    if len(active_goals[goal_id]["log"]) > 100:
                        active_goals[goal_id]["log"].pop(0)
            proc.wait()
            if goal_id in active_goals:
                active_goals[goal_id]["status"] = "completed"
        except Exception as e:
            if goal_id in active_goals:
                active_goals[goal_id]["log"].append(f"Error: {e}")
                active_goals[goal_id]["status"] = "error"
    
    threading.Thread(target=worker, daemon=True).start()
    return goal_id

HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body{margin:0;background:#f7fee7;font-family:system-ui}
.container{max-width:800px;margin:20px auto;padding:20px}
h2{color:#3f6212}
.card{background:#fff;border-radius:12px;padding:20px;box-shadow:0 4px 6px rgba(0,0,0,0.1);margin-bottom:20px}
label{display:block;margin-bottom:5px;color:#4d7c0f;font-weight:bold}
select,input,textarea{width:100%;padding:8px;border:1px solid #bef264;border-radius:6px;margin-bottom:15px;box-sizing:border-box;font-family:monospace}
textarea{height:80px}
button{padding:10px 20px;background:#84cc16;color:#fff;border:none;border-radius:6px;cursor:pointer;font-weight:bold}
button:hover{background:#65a30d}
.log{background:#1e293b;color:#e2e8f0;padding:15px;border-radius:6px;font-family:monospace;font-size:13px;max-height:300px;overflow-y:auto;white-space:pre-wrap}
.status{display:inline-block;padding:4px 12px;border-radius:12px;font-size:12px;font-weight:bold;margin-left:10px}
.status-running{background:#fbbf24;color:#78350f}
.status-completed{background:#22c55e;color:#fff}
.status-error{background:#ef4444;color:#fff}
</style>
</head>
<body>
<div class="container">
  <h2>🚀 ROS2 动作执行器</h2>
  <div class="card">
    <label>选择动作</label>
    <select id="action" onchange="loadType()"><option>加载中...</option></select>
    
    <label>动作类型</label>
    <input type="text" id="type" readonly>
    
    <label>目标参数 (YAML/JSON)</label>
    <textarea id="args" placeholder="{ }"></textarea>
    
    <button onclick="send()">发送目标</button>
  </div>
  
  <div class="card">
    <h3>执行日志 <span id="goal-status"></span></h3>
    <div class="log" id="log">等待发送...</div>
  </div>
</div>
<script>
let currentGoal=null;
async function loadActions(){
  const res=await fetch('/api/actions');
  const data=await res.json();
  document.getElementById('action').innerHTML='<option value="">选择动作...</option>'+data.map(a=>`<option value="${a}">${a}</option>`).join('');
}
async function loadType(){
  const name=document.getElementById('action').value;
  if(!name){document.getElementById('type').value='';return;}
  const res=await fetch('/api/type?name='+encodeURIComponent(name));
  document.getElementById('type').value=await res.text();
}
async function send(){
  const name=document.getElementById('action').value;
  const type=document.getElementById('type').value;
  const args=document.getElementById('args').value||'{}';
  if(!name||!type)return alert('请选择动作');
  const res=await fetch(`/api/send?name=${encodeURIComponent(name)}&type=${encodeURIComponent(type)}&args=${encodeURIComponent(args)}`);
  currentGoal=await res.text();
  document.getElementById('log').textContent='发送中...';
}
async function refreshLog(){
  if(!currentGoal)return;
  const res=await fetch('/api/log?id='+currentGoal);
  const data=await res.json();
  document.getElementById('log').textContent=data.log.join('\n')||'等待反馈...';
  const statusEl=document.getElementById('goal-status');
  statusEl.className='status status-'+data.status;
  statusEl.textContent=data.status;
  if(data.status==='completed'||data.status==='error') currentGoal=null;
}
loadActions();
setInterval(refreshLog, 500);
</script>
</body>
</html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/actions':
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(get_actions()).encode())
        elif parsed.path.startswith('/api/type'):
            qs = parse_qs(parsed.query)
            name = qs.get('name', [''])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(get_action_type(name).encode())
        elif parsed.path.startswith('/api/send'):
            qs = parse_qs(parsed.query)
            name = qs.get('name', [''])[0]
            atype = qs.get('type', [''])[0]
            args = qs.get('args', ['{}'])[0]
            gid = send_goal(name, atype, args)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(gid.encode())
        elif parsed.path.startswith('/api/log'):
            qs = parse_qs(parsed.query)
            gid = qs.get('id', [''])[0]
            data = active_goals.get(gid, {"status": "unknown", "log": []})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
    def log_message(self, *a): pass

if __name__ == "__main__":
    print(f"[ROS2 Action Client] 启动成功，监听端口: {PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()