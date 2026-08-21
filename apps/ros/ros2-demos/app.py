"""ros2-demos —— 配套演示节点集合 (Windows/Linux 跨平台适配)"""
import json, os, sys, subprocess, platform
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

processes = {}
errors = {}

nodes_config = [
    {'id': 'topic_pub', 'name': ' 话题发布者', 'script': 'topic_publisher.py'},
    {'id': 'service_srv', 'name': ' 服务服务器', 'script': 'service_server.py'},
    {'id': 'action_srv', 'name': '🚀 动作服务器', 'script': 'action_server.py'},
    {'id': 'tf_pub', 'name': '📐 TF 发布器', 'script': 'tf_broadcaster.py'},
    {'id': 'param_node', 'name': '️ 参数节点', 'script': 'param_node.py'}
]

def find_ros2_setup_windows():
    """在 Windows 下自动寻找 ROS2 的 setup.bat"""
    # 常见的 Windows ROS2 安装路径
    possible_paths = [
        r"C:\dev\ros2_humble\local_setup.bat",
        r"C:\opt\ros\humble\x64\setup.bat",
        r"C:\dev\ros2_iron\local_setup.bat",
        r"C:\dev\ros2_jazzy\local_setup.bat",
        r"C:\dev\ros2_foxy\local_setup.bat"
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
            
    # 尝试通过环境变量推断
    ament_prefix = os.environ.get("AMENT_PREFIX_PATH", "")
    if ament_prefix:
        setup_path = os.path.join(ament_prefix, "local_setup.bat")
        if os.path.exists(setup_path):
            return setup_path
            
    return None

def build_cmd(script_name):
    """构建跨平台启动命令"""
    demo_dir = Path(__file__).parent / "demo_nodes"
    script_path = str(demo_dir / script_name)
    python_exe = sys.executable
    
    if platform.system() == "Windows":
        setup_bat = find_ros2_setup_windows()
        if setup_bat:
            # Windows 下使用 cmd /c call 来加载环境，确保 PYTHONPATH 被正确设置
            # 注意：call 后面的命令会继承 setup.bat 设置的环境变量
            return f'cmd /c "call \\"{setup_bat}\\" && \\"{python_exe}\\" \\"{script_path}\\""'
        else:
            # 如果找不到 setup.bat，直接运行，依赖当前终端的环境变量
            return f'cmd /c "\\"{python_exe}\\" \\"{script_path}\\""'
    else:
        # Linux/Mac
        ros2_setup = "/opt/ros/humble/setup.bash"
        if not os.path.exists(ros2_setup):
            for distro in ['iron', 'jazzy', 'rolling']:
                p = f"/opt/ros/{distro}/setup.bash"
                if os.path.exists(p):
                    ros2_setup = p
                    break
        return f'bash -c "source {ros2_setup} 2>/dev/null; \\"{python_exe}\\" \\"{script_path}\\""'

def start_demo_node(name, script_name):
    if name in processes:
        if processes[name].poll() is None:
            return f"{name} 已在运行"
        else:
            del processes[name]
            
    try:
        cmd = build_cmd(script_name)
        # 关键：继承当前环境变量
        env = os.environ.copy() 
        
        is_win = platform.system() == "Windows"
        proc = subprocess.Popen(
            cmd, shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            preexec_fn=None if is_win else os.setsid,  # Linux: 新进程组，便于整组杀
            creationflags=subprocess.CREATE_NO_WINDOW if is_win else 0  # Windows: 隐藏黑框
        )
        processes[name] = proc
        errors[name] = ""
        return f"✅ {name} 已启动 (PID: {proc.pid})"
    except Exception as e:
        return f"❌ 启动失败: {e}"

def _kill_tree(proc):
    """跨平台杀掉整个进程树（shell + 真正的 ros2/python 子进程）。"""
    pid = proc.pid
    is_win = platform.system() == "Windows"
    if is_win:
        # taskkill /F /T /PID 杀掉整个进程树
        try:
            subprocess.run(f"taskkill /F /T /PID {pid}", shell=True,
                           capture_output=True, timeout=5)
        except Exception:
            pass
    else:
        # Linux: 杀整个进程组（preexec_fn=os.setsid 创建的新组）
        try:
            import signal
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except Exception:
            try: proc.terminate()
            except Exception: pass
    # 兜底：等不到就 SIGKILL
    try:
        proc.wait(timeout=3)
    except Exception:
        if is_win:
            try:
                subprocess.run(f"taskkill /F /T /PID {pid}", shell=True,
                               capture_output=True, timeout=3)
            except Exception: pass
        else:
            try:
                import signal
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except Exception:
                try: proc.kill()
                except Exception: pass

def stop_demo_node(name):
    if name in processes:
        proc = processes[name]
        _kill_tree(proc)
        if proc.stderr:
            try:
                errors[name] = proc.stderr.read().decode('utf-8', errors='ignore')
            except Exception:
                errors[name] = ""
        del processes[name]
        return f"⏹️ {name} 已停止"
    return f"{name} 未运行"

def get_status():
    status = {}
    for name, proc in processes.items():
        if proc.poll() is None:
            status[name] = "running"
        else:
            status[name] = "crashed"
            if proc.stderr:
                errors[name] = proc.stderr.read().decode('utf-8', errors='ignore')
    return status

HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body{margin:0;background:#ecfdf5;font-family:system-ui}
.container{max-width:800px;margin:20px auto;padding:20px}
h2{color:#065f46}
.card{background:#fff;border-radius:12px;padding:20px;box-shadow:0 4px 6px rgba(0,0,0,0.1);margin-bottom:20px}
.node{display:flex;justify-content:space-between;align-items:center;padding:12px;margin:8px 0;background:#f0fdf4;border-radius:8px;border-left:4px solid #10b981;flex-wrap:wrap}
.node.running{border-left-color:#10b981}
.node.crashed{border-left-color:#ef4444;background:#fef2f2}
.node.stopped{border-left-color:#9ca3af;opacity:0.6}
.status{padding:4px 12px;border-radius:12px;font-size:12px;font-weight:bold}
.status.running{background:#10b981;color:#fff}
.status.crashed{background:#ef4444;color:#fff}
.status.stopped{background:#9ca3af;color:#fff}
button{padding:6px 12px;border:none;border-radius:6px;cursor:pointer;font-size:13px;margin-left:5px}
.btn-start{background:#10b981;color:#fff}
.btn-stop{background:#ef4444;color:#fff}
.btn-log{background:#3b82f6;color:#fff}
.error-log{width:100%;margin-top:10px;padding:10px;background:#1e293b;color:#ef4444;border-radius:6px;font-family:monospace;font-size:12px;white-space:pre-wrap;display:none}
</style>
</head>
<body>
<div class="container">
  <h2> ROS2 演示节点管理器</h2>
  <div class="card">
    <h3>节点列表</h3>
    <div id="nodes">加载中...</div>
  </div>
  <div class="card" style="background:#fffbeb;border-left:4px solid #f59e0b">
    <strong>⚠️ 提示：</strong> 如果节点显示“已崩溃”，请点击“查看错误”。
    最常见原因是 <code>ModuleNotFoundError: No module named 'rclpy'</code>。
    <br>解决方法：请在终端中先执行 <code>source /opt/ros/humble/setup.bash</code>，然后再启动本应用。
  </div>
</div>
<script>
const nodes = [
  {id:'topic_pub', name:' 话题发布者', script:'topic_publisher.py'},
  {id:'service_srv', name:'📞 服务服务器', script:'service_server.py'},
  {id:'action_srv', name:'🚀 动作服务器', script:'action_server.py'},
  {id:'tf_pub', name:'📐 TF 发布器', script:'tf_broadcaster.py'},
  {id:'param_node', name:'⚙️ 参数节点', script:'param_node.py'}
];

async function loadStatus(){
  const res=await fetch('/api/status');
  const status=await res.json();
  const div=document.getElementById('nodes');
  div.innerHTML=nodes.map(n=>{
    const st=status[n.id]||'stopped';
    const stText = st==='running'?'运行中':(st==='crashed'?'已崩溃':'已停止');
    return `<div class="node ${st}">
      <div style="flex:1"><strong>${n.name}</strong><br><small>${n.script}</small></div>
      <div>
        <span class="status ${st}">${stText}</span>
        <button class="btn-log" onclick="showLog('${n.id}')" ${st==='crashed'?'':'style="display:none"'}>查看错误</button>
        <button class="${st==='running'?'btn-stop':'btn-start'}" 
                onclick="${st==='running'?`stopNode('${n.id}')`: `startNode('${n.id}')`}">
          ${st==='running'?'停止':'启动'}
        </button>
      </div>
      <div class="error-log" id="log-${n.id}"></div>
    </div>`;
  }).join('');
}

async function showLog(id){
  const res=await fetch(`/api/log?id=${id}`);
  const text=await res.text();
  const el=document.getElementById(`log-${id}`);
  el.textContent=text||'无错误日志';
  el.style.display=el.style.display==='none'?'block':'none';
}

async function startNode(id){
  const node=nodes.find(n=>n.id===id);
  await fetch(`/api/start?id=${id}&script=${node.script}`);
  loadStatus();
}
async function stopNode(id){
  await fetch(`/api/stop?id=${id}`);
  loadStatus();
}
loadStatus();
setInterval(loadStatus, 2000);
</script>
</body>
</html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        
        if parsed.path == '/api/status':
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(get_status()).encode())
        
        elif parsed.path.startswith('/api/start'):
            qs = parse_qs(parsed.query)
            node_id = qs.get('id', [''])[0]
            script = qs.get('script', [''])[0]
            if node_id and script:
                msg = start_demo_node(node_id, script)
            else:
                msg = "参数错误"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(msg.encode())
        
        elif parsed.path.startswith('/api/stop'):
            qs = parse_qs(parsed.query)
            node_id = qs.get('id', [''])[0]
            msg = stop_demo_node(node_id)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(msg.encode())
        
        elif parsed.path.startswith('/api/log'):
            qs = parse_qs(parsed.query)
            node_id = qs.get('id', [''])[0]
            log = errors.get(node_id, "无错误日志")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(log.encode())
        
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
    
    def log_message(self, *a): pass

if __name__ == "__main__":
    print(f"[ROS2 Demos] 启动成功，监听端口: {PORT}")
    print("提示: Windows 下请确保已安装 ROS2 并配置了环境变量")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()