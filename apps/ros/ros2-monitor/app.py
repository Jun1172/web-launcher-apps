"""ros2-monitor —— ROS2 系统监控面板"""
import json, os, sys, subprocess, threading, time
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# 引入 ROS 组共享的 ros2 环境探测模块（跨平台、不固化路径）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import shared_ros2 as ros2env

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

# 缓存数据
cache = {
    "nodes": [],
    "topics": [],
    "services": [],
    "last_update": 0
}

def run_ros2_cmd(cmd):
    """执行 ROS2 命令并返回结果"""
    try:
        if cmd.startswith("ros2 "):
            cmd, cwd = ros2env.command(cmd[5:])
        else:
            cwd = None
        result = subprocess.run(
            cmd, shell=True, cwd=cwd, capture_output=True, 
            text=True, encoding="utf-8", errors="replace", timeout=20
        )
        return result.stdout.strip().split('\n') if result.stdout else []
    except:
        return []

def update_cache():
    """后台更新缓存"""
    while True:
        try:
            cache["nodes"] = run_ros2_cmd("ros2 node list")
            cache["topics"] = run_ros2_cmd("ros2 topic list")
            cache["services"] = run_ros2_cmd("ros2 service list")
            cache["last_update"] = time.time()
        except:
            pass
        time.sleep(3)

# 启动后台更新线程
threading.Thread(target=update_cache, daemon=True).start()

HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body{margin:0;background:#ecfdf5;font-family:system-ui}
.container{max-width:1200px;margin:20px auto;padding:20px}
h2{color:#065f46;margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}
.card{background:#fff;border-radius:12px;padding:20px;box-shadow:0 4px 6px rgba(0,0,0,0.1)}
.card h3{margin:0 0 15px;color:#059669;font-size:16px;border-bottom:2px solid #d1fae5;padding-bottom:8px}
.list{max-height:300px;overflow-y:auto}
.item{padding:8px;margin:5px 0;background:#f0fdf4;border-radius:6px;font-size:13px;font-family:monospace}
.count{background:#10b981;color:#fff;padding:2px 8px;border-radius:12px;font-size:12px;margin-left:8px}
.update-time{color:#6b7280;font-size:12px;margin-top:10px}
.tip{background:#fffbeb;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:13px;line-height:1.7;color:#78350f}
.tip code{background:#fef3c7;padding:2px 6px;border-radius:4px;font-family:monospace;color:#92400e}
.tip a{color:#2563eb;text-decoration:none}
.tip a:hover{text-decoration:underline}
</style>
</head>
<body>
<div class="container">
  <h2>📊 ROS2 系统监控</h2>
  <div class="tip"><strong>💡 使用提示：</strong>需要先 source ROS2 环境：执行 <code>source /opt/ros/humble/setup.bash</code>。若列表为空说明当前没有节点运行，可打开 <a href="http://127.0.0.1:8200/" target="_blank">ROS2 演示节点</a> 启动节点。</div>
  <div class="grid">
    <div class="card">
      <h3>🔷 节点 <span class="count" id="node-count">0</span></h3>
      <div class="list" id="nodes"></div>
    </div>
    <div class="card">
      <h3> 话题 <span class="count" id="topic-count">0</span></h3>
      <div class="list" id="topics"></div>
    </div>
    <div class="card">
      <h3> 服务 <span class="count" id="service-count">0</span></h3>
      <div class="list" id="services"></div>
    </div>
  </div>
  <div class="update-time">最后更新: <span id="time">-</span></div>
</div>
<script>
async function refresh(){
  const res=await fetch('/api/status');
  const data=await res.json();
  
  document.getElementById('node-count').textContent=data.nodes.length;
  document.getElementById('nodes').innerHTML=data.nodes.map(n=>`<div class="item">${n}</div>`).join('')||'<div style="color:#9ca3af">无节点</div>';
  
  document.getElementById('topic-count').textContent=data.topics.length;
  document.getElementById('topics').innerHTML=data.topics.map(t=>`<div class="item">${t}</div>`).join('')||'<div style="color:#9ca3af">无话题</div>';
  
  document.getElementById('service-count').textContent=data.services.length;
  document.getElementById('services').innerHTML=data.services.map(s=>`<div class="item">${s}</div>`).join('')||'<div style="color:#9ca3af">无服务</div>';
  
  const now=new Date();
  document.getElementById('time').textContent=now.toLocaleTimeString();
}
refresh();
setInterval(refresh,3000);
</script>
</body>
</html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/status':
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(cache, ensure_ascii=False).encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
    def log_message(self, *a): pass

if __name__ == "__main__":
    print(f"[ROS2 Monitor] 启动成功，监听端口: {PORT}")
    print("提示: 请确保已 source /opt/ros/humble/setup.bash")
    ThreadingHTTPServer((os.environ.get("APP_HOST", "127.0.0.1"), PORT), H).serve_forever()