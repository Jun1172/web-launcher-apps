"""ros2-topic-inspector —— 话题数据查看器"""
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

active_subscribers = {}

def get_topics():
    """获取话题列表"""
    try:
        result = subprocess.run("ros2 topic list", shell=True, capture_output=True, text=True, timeout=3)
        return [t.strip() for t in result.stdout.strip().split('\n') if t.strip()]
    except:
        return []

def subscribe_topic(topic):
    """订阅话题并持续获取数据"""
    if topic in active_subscribers:
        return
    
    def worker():
        try:
            cmd = f'ros2 topic echo {topic} --no-arr --once'
            while topic in active_subscribers:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=2)
                if result.stdout:
                    active_subscribers[topic]["messages"].append({
                        "time": time.strftime("%H:%M:%S"),
                        "data": result.stdout.strip()
                    })
                    if len(active_subscribers[topic]["messages"]) > 50:
                        active_subscribers[topic]["messages"].pop(0)
                time.sleep(0.5)
        except:
            pass
    
    active_subscribers[topic] = {"messages": []}
    threading.Thread(target=worker, daemon=True).start()

def unsubscribe_topic(topic):
    """取消订阅"""
    if topic in active_subscribers:
        del active_subscribers[topic]

HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body{margin:0;background:#f5f3ff;font-family:system-ui}
.container{max-width:900px;margin:20px auto;padding:20px}
h2{color:#5b21b6;margin-bottom:20px}
.controls{display:flex;gap:10px;margin-bottom:20px}
select{flex:1;padding:10px;border:2px solid #ddd6fe;border-radius:8px;font-size:14px}
button{padding:10px 20px;background:#8b5cf6;color:#fff;border:none;border-radius:8px;cursor:pointer;font-weight:bold}
button:hover{background:#7c3aed}
button.stop{background:#ef4444}
.messages{background:#fff;border-radius:12px;padding:20px;box-shadow:0 4px 6px rgba(0,0,0,0.1);max-height:500px;overflow-y:auto}
.message{background:#f5f3ff;padding:12px;margin:8px 0;border-radius:8px;border-left:4px solid #8b5cf6}
.message-time{color:#6b7280;font-size:12px;margin-bottom:5px}
.message-data{font-family:monospace;font-size:13px;white-space:pre-wrap;word-break:break-all;background:#fff;padding:8px;border-radius:4px}
.empty{color:#9ca3af;text-align:center;padding:40px}
.stats{margin-top:10px;color:#6b7280;font-size:13px}
.tip{background:#fffbeb;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:13px;line-height:1.7;color:#78350f}
.tip code{background:#fef3c7;padding:2px 6px;border-radius:4px;font-family:monospace;color:#92400e}
.tip a{color:#2563eb;text-decoration:none}
.tip a:hover{text-decoration:underline}
</style>
</head>
<body>
<div class="container">
  <h2> 话题查看器</h2>
  <div class="tip"><strong>💡 使用提示：</strong>没有话题可订阅？请先启动话题源：执行 <code>ros2 run demo_nodes_cpp talker</code>，或打开 <a href="http://127.0.0.1:8200/" target="_blank">ROS2 演示节点</a> 启动「话题发布者」。下方列表会自动检索当前可用话题。</div>
  <div class="controls">
    <select id="topic-select"><option value="">选择话题...</option></select>
    <button id="sub-btn" onclick="toggleSubscribe()">订阅</button>
    <button onclick="clearMessages()">清空</button>
  </div>
  <div class="stats" id="stats"></div>
  <div class="messages" id="messages"><div class="empty">选择话题并点击订阅</div></div>
</div>
<script>
let subscribed=false;
let currentTopic='';   // 当前正在订阅的话题
let refreshInterval=null;

async function loadTopics(){
  const res=await fetch('/api/topics');
  const topics=await res.json();
  const select=document.getElementById('topic-select');
  // 保留当前选中的话题
  const prev=select.value;
  select.innerHTML='<option value="">选择话题...</option>'+topics.map(t=>`<option value="${t}">${t}</option>`).join('');
  if(prev && [...select.options].some(o=>o.value===prev)){
    select.value=prev;
  }
}

async function toggleSubscribe(){
  const btn=document.getElementById('sub-btn');
  if(!subscribed){
    // ── 订阅：必须选择话题 ──
    const select=document.getElementById('topic-select');
    const picked=select.value;
    if(!picked) return alert('请先选择话题');
    currentTopic=picked;
    subscribed=true;
    btn.textContent='停止';
    btn.classList.add('stop');
    await fetch('/api/subscribe?topic='+encodeURIComponent(currentTopic));
    refreshInterval=setInterval(refreshMessages,500);
  }else{
    // ── 停止：用之前订阅的话题直接退订，不再要求选择 ──
    subscribed=false;
    btn.textContent='订阅';
    btn.classList.remove('stop');
    if(refreshInterval){ clearInterval(refreshInterval); refreshInterval=null; }
    if(currentTopic){
      await fetch('/api/unsubscribe?topic='+encodeURIComponent(currentTopic));
    }
    currentTopic='';
  }
}

async function refreshMessages(){
  if(!currentTopic) return;
  const res=await fetch('/api/messages?topic='+encodeURIComponent(currentTopic));
  const data=await res.json();
  const msgsDiv=document.getElementById('messages');
  if(data.length===0){
    msgsDiv.innerHTML='<div class="empty">等待消息...</div>';
  }else{
    msgsDiv.innerHTML=data.map(m=>`
      <div class="message">
        <div class="message-time"> ${m.time}</div>
        <div class="message-data">${m.data}</div>
      </div>
    `).join('');
    msgsDiv.scrollTop=msgsDiv.scrollHeight;
  }
  document.getElementById('stats').textContent=`已接收 ${data.length} 条消息`;
}

function clearMessages(){
  document.getElementById('messages').innerHTML='<div class="empty">已清空</div>';
  document.getElementById('stats').textContent='';
}

loadTopics();
setInterval(loadTopics,5000);
</script>
</body>
</html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/topics':
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(get_topics(), ensure_ascii=False).encode("utf-8"))
        elif parsed.path.startswith('/api/subscribe'):
            qs = parse_qs(parsed.query)
            topic = qs.get('topic', [''])[0]
            if topic:
                subscribe_topic(topic)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{}')
        elif parsed.path.startswith('/api/unsubscribe'):
            qs = parse_qs(parsed.query)
            topic = qs.get('topic', [''])[0]
            if topic:
                unsubscribe_topic(topic)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{}')
        elif parsed.path.startswith('/api/messages'):
            qs = parse_qs(parsed.query)
            topic = qs.get('topic', [''])[0]
            messages = active_subscribers.get(topic, {}).get("messages", [])
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(messages, ensure_ascii=False).encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
    def log_message(self, *a): pass

if __name__ == "__main__":
    print(f"[ROS2 Topic Inspector] 启动成功，监听端口: {PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()