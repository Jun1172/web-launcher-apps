"""ros2-topic-inspector —— 话题教程：订阅 + 发布 + 内置数据源（闭环）

功能：
- 内置数据源：一键启动发布器（/demo_talker），自己发布自己看，无需外部节点。
- 订阅查看：自动检索当前可用话题（含类型），订阅后实时回显，类似话题查看器。
- 手动发布：向任意话题发布指定类型消息（JSON），支持 $i 递增与循环。

跨平台 ROS2 环境探测由共享模块 shared_ros2 提供，不固化路径。
"""
import json, os, sys, subprocess, threading, time
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import shared_ros2 as ros2env

APP_DIR = Path(__file__).resolve().parent
SOURCE_PY = APP_DIR / "source.py"


def _run_ros2(args, timeout=20):
    cmd, cwd = ros2env.command(" ".join(args))
    try:
        result = subprocess.run(cmd, shell=True, cwd=cwd,
                                capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout)
    except Exception:
        return "", ""
    return result.stdout, result.stderr


def get_port():
    env_port = os.environ.get("LAUNCHER_APP_PORT")
    if env_port:
        try: return int(env_port)
        except ValueError: pass
    j = APP_DIR / "app.json"
    if j.exists():
        try:
            return int(json.loads(j.read_text(encoding="utf-8")).get("port", 0))
        except Exception: pass
    return 0


PORT = get_port()

# 订阅状态 {topic: {"messages": [...], "thread": t}}
active_subscribers = {}
# 正在运行的发布进程 {名称: Popen}
pub_procs = {}
LOCK = threading.Lock()


# ── 话题：列表 & 订阅 ────────────────────────────────
def get_topics():
    """返回 [{name, type}]，type 可能为空。"""
    stdout, _ = _run_ros2(["topic", "list", "-t"], 20)
    # ros2 topic list -t 输出格式: /name [type]
    out = []
    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if "[" in line and line.rstrip().endswith("]"):
            name = line.split("[")[0].strip()
            typ = line.split("[")[1].rstrip("]").strip()
            out.append({"name": name, "type": typ})
        else:
            out.append({"name": line, "type": ""})
    return out


def subscribe_topic(topic):
    if topic in active_subscribers:
        return

    def worker():
        try:
            while topic in active_subscribers:
                stdout, _ = _run_ros2(["topic", "echo", topic, "--once"], 15)
                if stdout:
                    active_subscribers[topic]["messages"].append({
                        "time": time.strftime("%H:%M:%S"),
                        "data": stdout.strip(),
                    })
                    if len(active_subscribers[topic]["messages"]) > 60:
                        active_subscribers[topic]["messages"].pop(0)
                time.sleep(0.3)
        except Exception:
            pass

    active_subscribers[topic] = {"messages": []}
    threading.Thread(target=worker, daemon=True).start()


def unsubscribe_topic(topic):
    active_subscribers.pop(topic, None)


# ── 发布：内置数据源 & 手动发布 ─────────────────────────
def _spawn_pub(name, topic, mtype, rate, payload, count=0):
    stop_pub(name)
    env = dict(os.environ)
    env.update({
        "PUB_TOPIC": topic,
        "PUB_TYPE": mtype,
        "PUB_RATE": str(rate),
        "PUB_PAYLOAD": payload,
        "PUB_COUNT": str(count),
    })
    py, cwd = ros2env.python_command()
    cmd = f'{py} "{SOURCE_PY}"'
    p = subprocess.Popen(cmd, shell=True, cwd=cwd, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8", errors="replace",
                         **ros2env.source_popen_kwargs())
    pub_procs[name] = p
    return p


def stop_pub(name):
    p = pub_procs.pop(name, None)
    if p and p.poll() is None:
        # 只 terminate 最外层（cmd.exe/shell）会把真正的发布节点留成孤儿；
        # 整棵进程树清理，确保发布节点一并退出。
        ros2env.kill_proc_tree(p.pid)
        try: p.wait(timeout=3)
        except Exception:
            try: p.kill()
            except Exception: pass


def pub_status():
    res = {}
    for name, p in list(pub_procs.items()):
        res[name] = "running" if p.poll() is None else "exit(%s)" % p.poll()
    return res


def shutdown_all():
    for name in list(pub_procs):
        stop_pub(name)
    subs = list(active_subscribers)
    for t in subs:
        unsubscribe_topic(t)


# 内置数据源：仅发布一个 /demo_talker（std_msgs/String），保持简单
_SOURCE_KEYS = ("source",)


def _sources_running():
    return any(pub_procs.get(k) is not None and pub_procs[k].poll() is None
               for k in _SOURCE_KEYS)


def _stop_sources():
    for k in _SOURCE_KEYS:
        stop_pub(k)


# ── 前端 ──────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>话题教程</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#0e1220;color:#dbe3f0;font-family:system-ui}
.wrap{max-width:960px;margin:0 auto;padding:20px}
h2{color:#a78bfa;margin:0 0 4px;font-size:20px}
.sub{color:#64748b;font-size:13px;margin-bottom:18px}
.card{background:#171c30;border:1px solid #26304d;border-radius:12px;padding:18px;margin-bottom:16px}
.card h3{margin:0 0 12px;font-size:15px;color:#e2e8f0;display:flex;align-items:center;gap:8px}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}
select,input{flex:1;min-width:140px;padding:9px 10px;background:#0e1220;color:#dbe3f0;
  border:1px solid #2c3757;border-radius:8px;font-size:13px}
input[type=number]{max-width:90px}
label{font-size:12px;color:#94a3b8;align-self:center;white-space:nowrap}
button{padding:9px 16px;border:none;border-radius:8px;cursor:pointer;font-weight:600;
  font-size:13px;background:#7c5cf0;color:#fff}
button:hover{filter:brightness(1.1)}
button.sec{background:#223053}
button.warn{background:#d97706}
button.danger{background:#dc2626}
button:disabled{opacity:.4;cursor:not-allowed}
.code{padding:8px;background:#0e1220;border:1px solid #26304d;border-radius:8px;
  font-family:ui-monospace,Consolas,monospace;font-size:12px;color:#7dd3fc;
  white-space:pre-wrap;word-break:break-all}
.status{font-size:12px;color:#94a3b8;margin-top:8px}
.green{color:#34d399}.yellow{color:#fbbf24}.red{color:#f87171}
.messages{max-height:420px;overflow-y:auto}
.msg{background:#0e1220;border-left:3px solid #7c5cf0;padding:10px 12px;margin:8px 0;border-radius:6px}
.mt{color:#64748b;font-size:11px;margin-bottom:4px}
.md{font-family:ui-monospace,Consolas,monospace;font-size:12px;white-space:pre-wrap;word-break:break-all}
.empty{color:#475569;text-align:center;padding:30px;font-size:13px}
.hr{border:none;border-top:1px solid #26304d;margin:14px 0}
.pill{background:#26304d;border-radius:20px;padding:2px 10px;font-size:12px;color:#a5b4fc}
.tabs{display:flex;gap:6px;margin-bottom:14px}
.tab{padding:8px 16px;border-radius:8px;background:#223053;cursor:pointer;color:#94a3b8;font-size:13px}
.tab.on{background:#7c5cf0;color:#fff}
.panel{display:none}.panel.on{display:block}
</style>
</head>
<body>
<div class="wrap">
  <h2>📡 话题教程</h2>
  <div class="sub">订阅 + 发布 | 内置数据源闭环测试，无需外部节点</div>

  <div class="tabs">
    <div class="tab on" onclick="show('sub')">订阅查看</div>
    <div class="tab" onclick="show('pub')">发布测试</div>
    <div class="tab" onclick="show('src')">内置数据源</div>
  </div>

  <!-- 订阅查看 -->
  <div class="panel on" id="panel-sub">
    <div class="card">
      <h3>📥 订阅查看 <span class="pill" id="sub-count">0</span></h3>
      <div class="row">
        <select id="topic-select"><option value="">选择话题...</option></select>
        <button onclick="toggleSubscribe()" id="sub-btn">订阅</button>
        <button class="sec" onclick="refreshTopics()">刷新</button>
        <button class="warn" onclick="clearMsgs()">清空</button>
      </div>
      <div class="messages" id="messages"><div class="empty">选择话题并点击「订阅」</div></div>
    </div>
  </div>

  <!-- 发布测试 -->
  <div class="panel" id="panel-pub">
    <div class="card">
      <h3>📤 手动发布</h3>
      <div class="row">
        <input id="p-topic" value="/manual_talk" placeholder="话题名">
        <input id="p-type" value="std_msgs/String" placeholder="类型">
        <input id="p-rate" type="number" value="1" min="0.1" step="0.1">
        <label>Hz</label>
      </div>
      <div class="row"><input id="p-payload" value='{"data":"hello $i"}' placeholder='JSON 负载' style="flex:1"></div>
      <div class="row">
        <button onclick="pubOnce()">发布一次</button>
        <button onclick="pubLoop(1)">循环发布</button>
        <button class="danger" onclick="pubStop()">停止</button>
        <span class="status" id="manual-status"></span>
      </div>
      <div class="code" style="margin-top:6px">提示：负载中 $i 会随每次发布递增；可选内置话题 <code>/manual_talk</code> 直接订阅查看。</div>
    </div>
  </div>

  <!-- 内置数据源 -->
  <div class="panel" id="panel-src">
    <div class="card">
      <h3>🔄 内置数据源</h3>
      <div class="row">
        <button onclick="srcToggle()" id="src-btn">启动数据源</button>
        <span class="status" id="src-status">未启动</span>
      </div>
      <div class="code" style="margin-top:8px">启动后自动发布话题 <code>/demo_talker</code>（std_msgs/String，内容「Hello ROS2 #n」），可在「订阅查看」中选择并订阅。</div>
    </div>
  </div>
</div>

<script>
var subscribed=false, currentTopic='', refreshTimer=null;

function show(name){
  document.querySelectorAll('.tab').forEach(function(t){t.classList.remove('on')});
  document.querySelectorAll('.panel').forEach(function(p){p.classList.remove('on')});
  var idx={sub:0,pub:1,src:2}[name];
  document.querySelectorAll('.tab')[idx].classList.add('on');
  document.getElementById('panel-'+name).classList.add('on');
}

function refreshTopics(){
  fetch('/api/topics').then(r=>r.json()).then(list=>{
    var sel=document.getElementById('topic-select');
    var prev=sel.value;
    var html='<option value="">选择话题...</option>';
    list.forEach(t=>{
      html+='<option value="'+t.name+'"'+(t.type?''+' data-type="'+t.type+'"':'')+'>'+t.name+(t.type?' ['+t.type+']':'')+'</option>';
    });
    sel.innerHTML=html;
    if(prev){for(var i=0;i<sel.options.length;i++){if(sel.options[i].value===prev){sel.value=prev;break;}}}
  }).catch(()=>{});
}

function toggleSubscribe(){
  var btn=document.getElementById('sub-btn');
  if(!subscribed){
    var t=document.getElementById('topic-select').value;
    if(!t){alert('请先选择话题');return;}
    if(t==='/demo_talker'||t==='/manual_talk'){ /* 本应用发布的话题可直接订阅 */ }
    currentTopic=t; subscribed=true;
    btn.textContent='停止'; btn.classList.add('danger');
    fetch('/api/sub?topic='+encodeURIComponent(t));
    refreshTimer=setInterval(loadMsgs,500);
  }else{
    subscribed=false;
    btn.textContent='订阅'; btn.classList.remove('danger');
    if(refreshTimer){clearInterval(refreshTimer);refreshTimer=null;}
    if(currentTopic) fetch('/api/unsub?topic='+encodeURIComponent(currentTopic));
    currentTopic='';
  }
}

function loadMsgs(){
  if(!currentTopic)return;
  fetch('/api/msgs?topic='+encodeURIComponent(currentTopic)).then(r=>r.json()).then(data=>{
    var d=document.getElementById('messages');
    document.getElementById('sub-count').textContent=data.length;
    if(!data.length){d.innerHTML='<div class="empty">等待消息...</div>';return;}
    var html='';
    data.forEach(m=>{html+='<div class="msg"><div class="mt">'+m.time+'</div><div class="md">'+esc(m.data)+'</div></div>';});
    d.innerHTML=html; d.scrollTop=d.scrollHeight;
  }).catch(()=>{});
}

function clearMsgs(){
  document.getElementById('messages').innerHTML='<div class="empty">已清空</div>';
  document.getElementById('sub-count').textContent='0';
}

function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}

function pubParams(count){
  return 'topic='+encodeURIComponent(v('p-topic'))+
    '&type='+encodeURIComponent(v('p-type'))+
    '&rate='+encodeURIComponent(v('p-rate'))+
    '&payload='+encodeURIComponent(v('p-payload'))+
    '&count='+encodeURIComponent(count);
}
function v(id){return document.getElementById(id).value;}

function pubOnce(){fetch('/api/pub?'+pubParams(1)).then(refreshPub).catch(()=>{});}
function pubLoop(){fetch('/api/pub?'+pubParams(0)).then(refreshPub).catch(()=>{});}
function pubStop(){fetch('/api/pub/stop').then(refreshPub).catch(()=>{});}
function refreshPub(){
  fetch('/api/pub/status').then(r=>r.json()).then(s=>{
    document.getElementById('manual-status').textContent = s.manual?('发布中 '+s.manual):'空闲';
    document.getElementById('manual-status').className='status green';
    if(s.manual && s.manual!=='running'){document.getElementById('manual-status').textContent='已停止('+s.manual+')';document.getElementById('manual-status').className='status red';}
  }).catch(()=>{});
}

function srcToggle(){
  // 先执行启动/停止，再刷新状态（点击"启动数据源"必须调用 toggle 接口，不能只读状态）
  fetch('/api/src/toggle').then(()=>{ setTimeout(srcStatusOnly,400); }).catch(srcStatusOnly);
}

function srcStatusOnly(){fetch('/api/src').then(r=>r.json()).then(s=>{
  var btn=document.getElementById('src-btn');
  var st=document.getElementById('src-status');
  if(s.running){btn.textContent='停止数据源';btn.className='danger';st.textContent='运行中: '+s.topics.join(', ');st.className='status green';}
  else{btn.textContent='启动数据源';btn.className='';st.textContent='未启动';st.className='status';}
}).catch(()=>{});}

refreshTopics(); setInterval(refreshTopics,4000); setInterval(srcStatusOnly,3000);
</script>
</body>
</html>"""


class H(BaseHTTPRequestHandler):
    def _json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urlparse(self.path)
        q = parse_qs(p.query)
        path = p.path
        if path == "/api/topics":
            self._json(get_topics())
        elif path == "/api/sub":
            t = q.get("topic", [""])[0]
            if t: subscribe_topic(t)
            self._json({})
        elif path == "/api/unsub":
            t = q.get("topic", [""])[0]
            if t: unsubscribe_topic(t)
            self._json({})
        elif path == "/api/msgs":
            t = q.get("topic", [""])[0]
            self._json(active_subscribers.get(t, {}).get("messages", []))
        elif path == "/api/pub":
            topic = q.get("topic", ["/manual_talk"])[0]
            mtype = q.get("type", ["std_msgs/String"])[0]
            try: rate = float(q.get("rate", ["1"])[0])
            except ValueError: rate = 1.0
            payload = q.get("payload", ["{}"])[0]
            try: count = int(q.get("count", ["0"])[0])
            except ValueError: count = 0
            _spawn_pub("manual", topic, mtype, rate, payload, count)
            self._json({"ok": True})
        elif path == "/api/pub/stop":
            stop_pub("manual")
            self._json({"ok": True})
        elif path == "/api/pub/status":
            self._json(pub_status())
        elif path == "/api/src":
            # 内置数据源：单个 /demo_talker 发布器
            running = _sources_running()
            self._json({"running": running,
                        "topics": ["/demo_talker"] if running else []})
        elif path == "/api/src/toggle":
            if _sources_running():
                _stop_sources()
            else:
                _spawn_pub("source", "/demo_talker", "std_msgs/String", 1,
                           '{"data":"Hello ROS2 #$i"}', 0)
            self._json({})
        else:
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, *a): pass


if __name__ == "__main__":
    print(f"[ROS2 Topic Inspector] 启动成功，监听端口: {PORT}")
    server = ThreadingHTTPServer((os.environ.get("APP_HOST", "127.0.0.1"), PORT), H)
    try:
        server.serve_forever()
    finally:
        shutdown_all()
        server.server_close()