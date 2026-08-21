"""ros2-bag-manager —— 罗素包管理器"""
import json, os, subprocess, glob
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

bag_dir = os.path.expanduser("~/ros2_bags")
os.makedirs(bag_dir, exist_ok=True)

record_proc = None
play_proc = None

def get_bags():
    return [os.path.basename(p) for p in glob.glob(os.path.join(bag_dir, "*")) if os.path.isdir(p)]

def get_topics():
    try:
        result = subprocess.run("ros2 topic list", shell=True, capture_output=True, text=True, timeout=3)
        return [t.strip() for t in result.stdout.strip().split("\n") if t.strip()]
    except:
        return []

def get_bag_info(name):
    path = os.path.join(bag_dir, name)
    try:
        res = subprocess.run(f"ros2 bag info {path}", shell=True, capture_output=True, text=True, timeout=10)
        return res.stdout
    except: return "获取信息失败"

def start_record(topics):
    global record_proc
    stop_record()
    path = os.path.join(bag_dir, "record_bag")
    cmd = f"ros2 bag record -o {path} {' '.join(topics)}"
    record_proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def stop_record():
    global record_proc
    if record_proc:
        record_proc.terminate()
        record_proc = None

def start_play(name):
    global play_proc
    stop_play()
    path = os.path.join(bag_dir, name)
    cmd = f"ros2 bag play {path}"
    play_proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def stop_play():
    global play_proc
    if play_proc:
        play_proc.terminate()
        play_proc = None

HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body{margin:0;background:#fdf2f8;font-family:system-ui}
.container{max-width:800px;margin:20px auto;padding:20px}
h2{color:#9d174d}
.card{background:#fff;border-radius:12px;padding:20px;box-shadow:0 4px 6px rgba(0,0,0,0.1);margin-bottom:20px}
label{display:block;margin-bottom:5px;color:#831843;font-weight:bold}
input,select{width:100%;padding:8px;border:1px solid #fbcfe8;border-radius:6px;margin-bottom:15px;box-sizing:border-box}
button{padding:8px 16px;margin-right:10px;border:none;border-radius:6px;cursor:pointer;font-weight:bold;color:#fff}
.btn-rec{background:#ec4899}.btn-stop{background:#ef4444}.btn-play{background:#8b5cf6}
pre{background:#f8fafc;padding:15px;border-radius:6px;font-size:13px;max-height:200px;overflow:auto}
.status{padding:10px;background:#fce7f3;border-radius:6px;margin-bottom:15px;font-weight:bold}
.topic-list{max-height:150px;overflow-y:auto;border:1px solid #fbcfe8;border-radius:6px;padding:8px;margin-bottom:10px}
.tip{background:#fffbeb;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:13px;line-height:1.7;color:#78350f}
.tip code{background:#fef3c7;padding:2px 6px;border-radius:4px;font-family:monospace;color:#92400e}
.tip a{color:#2563eb;text-decoration:none}
.tip a:hover{text-decoration:underline}
</style>
</head>
<body>
<div class="container">
  <h2>📦 Bag 管理器</h2>
  <div class="tip"><strong>💡 使用提示：</strong>录制前需要先有话题在发布。可打开 <a href="http://127.0.0.1:8200/" target="_blank">ROS2 演示节点</a> 启动话题发布者，或执行 <code>ros2 run demo_nodes_cpp talker</code>。下方「录制话题」会自动检索当前可用话题，勾选要录制的话题即可。</div>
  
  <div class="card">
    <h3>录制</h3>
    <div class="status" id="rec-status">状态: 空闲</div>
    <label>录制话题（勾选要录制的话题）</label>
    <div id="topic-list" class="topic-list">加载中...</div>
    <button onclick="loadTopics()" style="background:#3b82f6;color:#fff;border:none;border-radius:6px;padding:8px 16px;cursor:pointer;font-weight:bold;margin-bottom:15px">刷新话题列表</button>
    <button class="btn-rec" onclick="rec()">开始录制</button>
    <button class="btn-stop" onclick="stopRec()">停止</button>
  </div>

  <div class="card">
    <h3>播放</h3>
    <div class="status" id="play-status">状态: 空闲</div>
    <select id="bags"><option>加载中...</option></select>
    <button class="btn-play" onclick="play()">播放</button>
    <button class="btn-stop" onclick="stopPlay()">停止</button>
  </div>

  <div class="card">
    <h3>Bag 信息</h3>
    <pre id="info">选择 Bag 查看信息</pre>
  </div>
</div>
<script>
async function loadBags(){
  const res=await fetch('/api/bags');
  const data=await res.json();
  const sel=document.getElementById('bags');
  sel.innerHTML=data.length?data.map(b=>`<option value="${b}">${b}</option>`).join(''):'<option>无 Bag 文件</option>';
  if(data.length) showInfo(data[0]);
}
async function showInfo(name){
  const res=await fetch('/api/info?name='+encodeURIComponent(name));
  document.getElementById('info').textContent=await res.text();
}
document.getElementById('bags').onchange=e=>showInfo(e.target.value);

async function loadTopics(){
  const res=await fetch('/api/topics');
  const topics=await res.json();
  const div=document.getElementById('topic-list');
  if(topics.length===0){div.innerHTML='<span style="color:#9ca3af">暂无话题，请先启动话题源</span>'}
  else{div.innerHTML=topics.map(t=>'<label style="display:block;padding:4px;cursor:pointer"><input type="checkbox" value="'+t+'" checked> '+t+'</label>').join('')}
}
async function rec(){
  const checked=document.querySelectorAll('#topic-list input:checked');
  const topics=Array.from(checked).map(c=>c.value);
  if(topics.length===0)return alert('请至少选择一个话题');
  await fetch('/api/record?topics='+encodeURIComponent(topics.join(' ')));
  document.getElementById('rec-status').textContent='状态: 录制中...';
}
async function stopRec(){
  await fetch('/api/stop_record');
  document.getElementById('rec-status').textContent='状态: 已停止';
  loadBags();
}
async function play(){
  const name=document.getElementById('bags').value;
  if(!name)return;
  await fetch('/api/play?name='+encodeURIComponent(name));
  document.getElementById('play-status').textContent='状态: 播放中...';
}
async function stopPlay(){
  await fetch('/api/stop_play');
  document.getElementById('play-status').textContent='状态: 已停止';
}
loadBags();
loadTopics();
setInterval(()=>{
  fetch('/api/status').then(r=>r.json()).then(d=>{
    document.getElementById('rec-status').textContent='状态: '+(d.recording?'录制中...':'空闲');
    document.getElementById('play-status').textContent='状态: '+(d.playing?'播放中...':'空闲');
  });
},1000);
</script>
</body>
</html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/bags':
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(get_bags()).encode())
        elif parsed.path == '/api/topics':
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(get_topics()).encode())
        elif parsed.path.startswith('/api/info'):
            qs = parse_qs(parsed.query)
            name = qs.get('name', [''])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(get_bag_info(name).encode())
        elif parsed.path.startswith('/api/record'):
            qs = parse_qs(parsed.query)
            topics = qs.get('topics', [''])[0].split()
            start_record(topics)
            self.send_response(200); self.end_headers(); self.wfile.write(b'{}')
        elif parsed.path == '/api/stop_record':
            stop_record()
            self.send_response(200); self.end_headers(); self.wfile.write(b'{}')
        elif parsed.path.startswith('/api/play'):
            qs = parse_qs(parsed.query)
            name = qs.get('name', [''])[0]
            start_play(name)
            self.send_response(200); self.end_headers(); self.wfile.write(b'{}')
        elif parsed.path == '/api/stop_play':
            stop_play()
            self.send_response(200); self.end_headers(); self.wfile.write(b'{}')
        elif parsed.path == '/api/status':
            status = {"recording": record_proc is not None and record_proc.poll() is None,
                      "playing": play_proc is not None and play_proc.poll() is None}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(status).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
    def log_message(self, *a): pass

if __name__ == "__main__":
    print(f"[ROS2 Bag Manager] 启动成功，监听端口: {PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()