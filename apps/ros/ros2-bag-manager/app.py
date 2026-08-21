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
record_start_time = 0
play_start_time = 0
record_topics_count = 0
log_lines = []   # 运行日志（最近 200 条）

def log(msg):
    """追加一条运行日志，最多保留 200 条。"""
    import time as _t
    line = f"[{_t.strftime('%H:%M:%S')}] {msg}"
    log_lines.append(line)
    if len(log_lines) > 200:
        del log_lines[:len(log_lines) - 200]

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
    global record_proc, record_start_time, record_topics_count
    stop_record()
    import time as _t
    path = os.path.join(bag_dir, "record_bag")
    cmd = f"ros2 bag record -o {path} {' '.join(topics)}"
    log(f"开始录制 {len(topics)} 个话题: {', '.join(topics)}")
    log(f"保存路径: {path}")
    record_proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    record_start_time = _t.time()
    record_topics_count = len(topics)
    log("录制进程已启动")

def stop_record():
    global record_proc, record_topics_count
    if record_proc:
        log("停止录制...")
        record_proc.terminate()
        try:
            record_proc.wait(timeout=5)
        except Exception:
            record_proc.kill()
        record_proc = None
        record_topics_count = 0
        import glob as _g, os as _os
        bags = sorted(_g.glob(_os.path.join(bag_dir, "record_bag*")),
                       key=_os.path.getmtime, reverse=True)
        if bags:
            log(f"录制完成，已保存: {_os.path.basename(bags[0])}")
        else:
            log("录制已停止（未发现输出文件）")

def start_play(name):
    global play_proc, play_start_time
    stop_play()
    import time as _t
    path = os.path.join(bag_dir, name)
    if not os.path.isdir(path):
        log(f"播放失败: 找不到 Bag '{name}'")
        return
    cmd = f"ros2 bag play {path}"
    log(f"开始播放: {name}")
    play_proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    play_start_time = _t.time()
    log("播放进程已启动")

def stop_play():
    global play_proc
    if play_proc:
        log("停止播放...")
        play_proc.terminate()
        try:
            play_proc.wait(timeout=5)
        except Exception:
            play_proc.kill()
        play_proc = None
        log("播放已停止")

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
.topic-list label{display:flex;align-items:center;padding:4px 6px;cursor:pointer;border-radius:4px}
.topic-list label:hover{background:#fdf2f8}
.topic-list input[type=checkbox]{width:auto;margin:0 8px 0 0;flex:0 0 auto}
#log{background:#0f172a;color:#e2e8f0;padding:12px 15px;border-radius:8px;font-family:'Consolas','Monaco',monospace;font-size:12px;line-height:1.6;max-height:220px;overflow-y:auto;white-space:pre-wrap;word-break:break-all}
#log .log-line{display:block}
.log-time{color:#94a3b8}
.log-info{color:#60a5fa}
.log-warn{color:#fbbf24}
.log-ok{color:#34d399}
.log-err{color:#f87171}
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

  <div class="card">
    <h3>运行日志</h3>
    <div id="log">等待操作...</div>
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
async function loadLog(){
  try{
    const res=await fetch('/api/log');
    const lines=await res.json();
    const el=document.getElementById('log');
    if(!lines.length){el.innerHTML='<span style=color:#64748b>等待操作...</span>';return}
    el.innerHTML=lines.map(l=>{
      let cls='log-info';
      if(/完成|启动|保存|开始/.test(l))cls='log-ok';
      else if(/失败|错误|停止/.test(l))cls='log-warn';
      const t=l.slice(0,10),m=l.slice(10);
      return '<span class=log-line><span class=log-time>'+t+'</span><span class='+cls+'>'+m+'</span></span>';
    }).join('');
    el.scrollTop=el.scrollHeight;
  }catch(e){}
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
    const rs=document.getElementById('rec-status');
    const ps=document.getElementById('play-status');
    if(d.recording){
      const el=Math.floor((Date.now()/1000-d.rec_start));
      rs.textContent='状态: 录制中... 已运行 '+el+'s ('+d.rec_topics+' 个话题)';
    }else rs.textContent='状态: 空闲';
    if(d.playing){
      const el=Math.floor((Date.now()/1000-d.play_start));
      ps.textContent='状态: 播放中... 已运行 '+el+'s';
    }else ps.textContent='状态: 空闲';
    loadLog();
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
            rec_alive = record_proc is not None and record_proc.poll() is None
            play_alive = play_proc is not None and play_proc.poll() is None
            # 进程已退出但变量没清，补一条日志
            if record_proc is not None and not rec_alive:
                log("录制进程已退出")
                stop_record()
            if play_proc is not None and not play_alive:
                log("播放进程已结束")
                stop_play()
            status = {
                "recording": rec_alive,
                "rec_start": int(record_start_time),
                "rec_topics": record_topics_count,
                "playing": play_alive,
                "play_start": int(play_start_time),
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(status).encode())
        elif parsed.path == '/api/log':
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(log_lines[-200:], ensure_ascii=False).encode('utf-8'))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
    def log_message(self, *a): pass

if __name__ == "__main__":
    print(f"[ROS2 Bag Manager] 启动成功，监听端口: {PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()