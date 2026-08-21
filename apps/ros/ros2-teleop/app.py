"""ros2-teleop —— Web 机器人遥控"""
import json, os, subprocess, threading, platform, atexit
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

current_vel = {"linear_x": 0.0, "linear_y": 0.0, "angular_z": 0.0}
last_error = ""   # 最近的错误信息，供前端诊断

# 用 ros2 topic pub 子进程发布速度命令
# (避免 rclpy 在 web server 进程中 init/spin 导致 ExternalShutdownException 和 SHM 端口冲突)
pub_proc = None
pub_lock = threading.Lock()

def _kill_pub():
    global pub_proc
    if pub_proc is not None:
        try:
            pub_proc.terminate()
            try: pub_proc.wait(timeout=1)
            except Exception:
                try: pub_proc.kill()
                except Exception: pass
        except Exception:
            pass
        pub_proc = None

def update_vel(linear_x, linear_y, angular_z):
    """子进程发布：非零速度启动 ros2 topic pub -r 10；停止时 --once 发一次零速度。"""
    global current_vel, pub_proc, last_error
    current_vel = {"linear_x": linear_x, "linear_y": linear_y, "angular_z": angular_z}
    is_win = platform.system() == "Windows"
    with pub_lock:
        _kill_pub()
        # 速度全为 0：发一次停止消息即可，无需持续进程
        if linear_x == 0.0 and linear_y == 0.0 and angular_z == 0.0:
            cmd = ('ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist '
                   '"{linear: {x: 0.0, y: 0.0, z: 0.0}, '
                   'angular: {x: 0.0, y: 0.0, z: 0.0}}"')
            try:
                subprocess.run(
                    cmd, shell=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=2,
                    creationflags=subprocess.CREATE_NO_WINDOW if is_win else 0
                )
            except Exception as e:
                last_error = f"stop failed: {e}"
            return
        # 非零速度：启动持续发布进程
        cmd = (f'ros2 topic pub -r 10 /cmd_vel geometry_msgs/msg/Twist '
               f'"{{linear: {{x: {linear_x}, y: {linear_y}, z: 0.0}}, '
               f'angular: {{x: 0.0, y: 0.0, z: {angular_z}}}}}"')
        try:
            pub_proc = subprocess.Popen(
                cmd, shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if is_win else 0
            )
        except Exception as e:
            last_error = f"Popen failed: {e}"
            pub_proc = None

# 后台线程检测子进程是否意外退出，捕获 stderr
def _watch_pub():
    import time as _t
    global last_error
    while True:
        if pub_proc is not None:
            rc = pub_proc.poll()
            if rc is not None:
                try:
                    err = pub_proc.stderr.read().decode("utf-8", errors="ignore").strip()
                    if err:
                        last_error = f"ros2 topic pub exited({rc}): {err[:300]}"
                except Exception:
                    pass
        _t.sleep(1)
threading.Thread(target=_watch_pub, daemon=True).start()
atexit.register(_kill_pub)

HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body{margin:0;background:#eff6ff;font-family:system-ui;display:flex;justify-content:center;align-items:center;height:100vh}
.container{background:#fff;border-radius:16px;padding:30px;box-shadow:0 10px 30px rgba(0,0,0,0.1);text-align:center}
h2{color:#1e40af;margin-bottom:20px}
.joystick{width:200px;height:200px;margin:20px auto;position:relative;background:#f0f9ff;border-radius:50%;border:3px solid #3b82f6}
.center-btn{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:60px;height:60px;background:#3b82f6;border-radius:50%;border:none;color:#fff;font-size:24px;cursor:pointer}
.direction-btn{position:absolute;width:50px;height:50px;background:#60a5fa;border:none;border-radius:8px;color:#fff;font-size:20px;cursor:pointer;transition:all 0.1s}
.direction-btn:active{background:#2563eb;transform:scale(0.95)}
.up{top:10px;left:50%;transform:translateX(-50%)}
.down{bottom:10px;left:50%;transform:translateX(-50%)}
.left{left:10px;top:50%;transform:translateY(-50%)}
.right{right:10px;top:50%;transform:translateY(-50%)}
.speed-control{margin:20px 0}
.speed-control label{display:block;margin-bottom:8px;color:#1e40af;font-weight:bold}
input[type=range]{width:100%}
.status{margin-top:20px;padding:15px;background:#f0f9ff;border-radius:8px;font-family:monospace;font-size:14px}
.key-hint{margin-top:15px;color:#6b7280;font-size:13px}
.tip{background:#fffbeb;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:13px;line-height:1.7;color:#78350f}
.tip code{background:#fef3c7;padding:2px 6px;border-radius:4px;font-family:monospace;color:#92400e}
.tip a{color:#2563eb;text-decoration:none}
.tip a:hover{text-decoration:underline}
#diag{margin-top:12px;padding:8px 12px;background:#f0f9ff;border-radius:6px;font-size:12px;color:#155e75;min-height:18px}
</style>
</head>
<body>
<div class="container">
  <h2>🎮 机器人遥控</h2>
  <div class="tip"><strong>💡 使用提示：</strong>需要机器人订阅 <code>/cmd_vel</code> 话题。可启动 turtlesim 测试：执行 <code>ros2 run turtlesim turtlesim_node</code>，然后用本页面控制乌龟移动。</div>
  <div class="joystick">
    <button class="direction-btn up" data-key="w">↑</button>
    <button class="direction-btn down" data-key="s">↓</button>
    <button class="direction-btn left" data-key="a">←</button>
    <button class="direction-btn right" data-key="d">→</button>
    <button class="center-btn" data-key=" ">■</button>
  </div>
  <div class="speed-control">
    <label>速度: <span id="speed-val">0.5</span> m/s</label>
    <input type="range" id="speed" min="0.1" max="1.0" step="0.1" value="0.5">
  </div>
  <div class="status">
    线速度: <span id="linear">0.0</span> m/s<br>
    角速度: <span id="angular">0.0</span> rad/s
  </div>
  <div id="diag"></div>
  <div class="key-hint">键盘控制: W/A/S/D 移动，空格停止</div>
</div>
<script>
var speed=0.5;
var pressed={};

document.getElementById('speed').oninput=function(){
  speed=parseFloat(this.value);
  document.getElementById('speed-val').textContent=speed.toFixed(1);
};

function sendVel(linear_x,angular_z){
  document.getElementById('linear').textContent=linear_x.toFixed(2);
  document.getElementById('angular').textContent=angular_z.toFixed(2);
  fetch('/api/vel?lx='+linear_x+'&ly=0&az='+angular_z);
}

function applyKey(key){
  if(key==='w') sendVel(speed,0);
  else if(key==='s') sendVel(-speed,0);
  else if(key==='a') sendVel(0,speed);
  else if(key==='d') sendVel(0,-speed);
  else if(key===' ') sendVel(0,0);
}

var btns=document.querySelectorAll('.direction-btn');
for(var i=0;i<btns.length;i++){
  var b=btns[i];
  b.onmousedown=function(){
    var key=this.dataset.key;
    if(pressed[key])return;
    pressed[key]=true;
    applyKey(key);
  };
  b.onmouseup=function(){pressed={};sendVel(0,0);};
  b.onmouseleave=function(){if(Object.keys(pressed).length){pressed={};sendVel(0,0);}};
  b.ontouchstart=function(e){e.preventDefault();this.onmousedown();};
  b.ontouchend=function(e){e.preventDefault();this.onmouseup();};
}

document.querySelector('.center-btn').onclick=function(){pressed={};sendVel(0,0);};

document.onkeydown=function(e){
  if(e.repeat)return;
  var key=e.key.toLowerCase();
  if(key==='w'||key==='s'||key==='a'||key==='d'||key===' '){
    e.preventDefault();
    if(pressed[key])return;
    pressed[key]=true;
    applyKey(key);
  }
};

document.onkeyup=function(e){
  var key=e.key.toLowerCase();
  if(key==='w'||key==='s'||key==='a'||key==='d'){
    delete pressed[key];
    var count=0;
    for(var k in pressed)count++;
    if(count===0) sendVel(0,0);
  }
};

window.onblur=function(){pressed={};sendVel(0,0);};

function loadDiag(){
  fetch('/api/teleop_status').then(function(r){return r.json()}).then(function(d){
    var el=document.getElementById('diag');
    if(d.error){
      el.innerHTML='<span style="color:#ef4444">✗ '+d.error+'</span>';
    }else{
      el.innerHTML='<span style="color:#10b981">✓ 子进程发布运行中</span>';
    }
  }).catch(function(){});
}
loadDiag();
setInterval(loadDiag,2000);
</script>
</body>
</html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/teleop_status':
            status = {
                "vel": current_vel,
                "error": last_error,
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(status, ensure_ascii=False).encode("utf-8"))
        elif parsed.path == '/api/vel':
            qs = parse_qs(parsed.query)
            lx = float(qs.get('lx', [0])[0])
            ly = float(qs.get('ly', [0])[0])
            az = float(qs.get('az', [0])[0])
            threading.Thread(target=update_vel, args=(lx, ly, az), daemon=True).start()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{}')
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
    def log_message(self, *a): pass

if __name__ == "__main__":
    print(f"[ROS2 Teleop] 启动成功，监听端口: {PORT}")
    print("提示: 需要 ROS2 环境并发布 /cmd_vel 话题")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
