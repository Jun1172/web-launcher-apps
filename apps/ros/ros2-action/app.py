"""ros2-action —— 动作教程：动作列表 + send_goal + 内置动作服务器（闭环）

- 内置动作服务器：一键启动 demo_fib（Fibonacci，实时反馈），无需外部节点。
- 动作查询：自动检索当前可用动作（含类型），类似查看器。
- 发送目标：填写目标 JSON 发送，实时回显 feedback 与 result。

跨平台 ROS2 环境探测由共享模块 shared_ros2 提供，不固化路径。
"""
import json, os, sys, subprocess, threading
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import shared_ros2 as ros2env

APP_DIR = Path(__file__).resolve().parent
SOURCE_PY = APP_DIR / "source.py"
CLIENT_PY = APP_DIR / "client.py"


def _run_ros2(args, timeout=30):
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

source_proc = [None]   # 内置动作服务器
action_proc = [None]   # 当前发送目标的客户端进程
action_lines = []      # 客户端 JSON 事件（原始行）
action_state = {"phase": "idle"}  # 结构化状态
action_lock = threading.Lock()


# ── 动作发现 ─────────────────────────────────────────
def get_actions():
    stdout, _ = _run_ros2(["action", "list", "-t"], 20)
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


# ── 发送目标（客户端异步流式）─────────────────────────
def start_goal(action, atype, goaljson):
    stop_goal()
    env = dict(os.environ)
    env.update({
        "ACTION_NAME": action,
        "ACTION_TYPE": atype,
        "GOAL_JSON": goaljson,
    })
    py, cwd = ros2env.python_command()
    cmd = f'{py} "{CLIENT_PY}"'
    p = subprocess.Popen(cmd, shell=True, cwd=cwd, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8", errors="replace",
                         **ros2env.source_popen_kwargs())
    with action_lock:
        action_lines.clear()
        action_state.clear()
        action_state["phase"] = "connecting"
        action_proc[0] = p
    threading.Thread(target=_reader, args=(p,), daemon=True).start()


def _reader(p):
    try:
        for line in p.stdout:
            line = line.strip()
            if not line.startswith('{"'):
                continue
            with action_lock:
                action_lines.append(line)
                if len(action_lines) > 200:
                    action_lines.pop(0)
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                t = ev.get("type")
                if t == "feedback":
                    action_state.update({"phase": "feedback", "data": ev.get("data")})
                elif t == "accepted":
                    action_state["phase"] = "accepted"
                elif t == "result":
                    action_state.update({"phase": "done", "data": ev.get("data"),
                                         "status": ev.get("status")})
                elif t == "rejected":
                    action_state.update({"phase": "rejected", "data": ev.get("msg")})
                elif t == "error":
                    action_state.update({"phase": "error", "data": ev.get("msg")})
    except Exception:
        pass
    with action_lock:
        if action_state.get("phase") not in ("done", "rejected", "error"):
            action_state["phase"] = "closed"


def stop_goal():
    p = action_proc[0]
    action_proc[0] = None
    if p and p.poll() is None:
        ros2env.kill_proc_tree(p.pid)
        try: p.wait(timeout=2)
        except Exception:
            try: p.kill()
            except Exception: pass
    with action_lock:
        if action_state.get("phase") not in ("done", "rejected", "error"):
            action_state["phase"] = "cancelled"


def current_goal_status():
    lines = list(action_lines)
    state = dict(action_state)
    proc = action_proc[0]
    state["running"] = bool(proc and proc.poll() is None)
    state["lines"] = lines[-80:]
    return state


# ── 内置动作服务器 ────────────────────────────────────
def start_source():
    if source_proc[0] and source_proc[0].poll() is None:
        return True
    py, cwd = ros2env.python_command()
    cmd = f'{py} "{SOURCE_PY}"'
    source_proc[0] = subprocess.Popen(cmd, shell=True, cwd=cwd,
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, encoding="utf-8", errors="replace",
                                      **ros2env.source_popen_kwargs())
    return True


def stop_source():
    p = source_proc[0]
    source_proc[0] = None
    if p and p.poll() is None:
        # 只 terminate 最外层（cmd.exe/shell）会把真正的动作服务器留成孤儿；
        # 整棵进程树清理，确保 demo_fib 服务器一并退出。
        ros2env.kill_proc_tree(p.pid)
        try: p.wait(timeout=3)
        except Exception:
            try: p.kill()
            except Exception: pass


def source_status():
    p = source_proc[0]
    if p is not None and p.poll() is None:
        return "running"
    if p is not None:
        source_proc[0] = None
    return "stopped"


HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>动作教程</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#0e1220;color:#dbe3f0;font-family:system-ui}
.wrap{max-width:960px;margin:0 auto;padding:20px}
h2{color:#a78bfa;margin:0 0 4px;font-size:20px}
.sub{color:#64748b;font-size:13px;margin-bottom:18px}
.card{background:#171c30;border:1px solid #26304d;border-radius:12px;padding:18px;margin-bottom:16px}
.card h3{margin:0 0 12px;font-size:15px;color:#e2e8f0;display:flex;align-items:center;gap:8px}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;align-items:center}
select,input{flex:1;min-width:150px;padding:9px 10px;background:#0e1220;color:#dbe3f0;
  border:1px solid #2c3757;border-radius:8px;font-size:13px}
label{font-size:12px;color:#94a3b8;white-space:nowrap}
button{padding:9px 16px;border:none;border-radius:8px;cursor:pointer;font-weight:600;
  font-size:13px;background:#7c5cf0;color:#fff}
button:hover{filter:brightness(1.1)}
button.sec{background:#223053}
button.danger{background:#dc2626}
.status{font-size:12px;color:#94a3b8}
.green{color:#34d399}.red{color:#f87171}.yellow{color:#fbbf24}
.log{background:#0e1220;border:1px solid #26304d;border-radius:8px;padding:10px;
  font-family:ui-monospace,Consolas,monospace;font-size:12px;white-space:pre-wrap;word-break:break-all;
  min-height:120px;max-height:360px;overflow-y:auto;color:#7dd3fc}
.log .ev{display:block;margin:2px 0}
.sys{color:#64748b}.fb{color:#34d399}.ok{color:#a5b4fc}.err{color:#f87171}
.pill{background:#26304d;border-radius:20px;padding:2px 10px;font-size:12px;color:#a5b4fc}
.tabs{display:flex;gap:6px;margin-bottom:14px}
.tab{padding:8px 16px;border-radius:8px;background:#223053;cursor:pointer;color:#94a3b8;font-size:13px}
.tab.on{background:#7c5cf0;color:#fff}
.panel{display:none}.panel.on{display:block}
.code{background:#0e1220;border:1px solid #26304d;border-radius:8px;padding:10px;font-size:12px;color:#7dd3fc;line-height:1.7}
.banner{display:none;background:#7c2d12;border:1px solid #b45309;color:#fdba74;
  border-radius:8px;padding:10px 14px;font-size:13px;margin-bottom:14px;line-height:1.6}
</style>
</head>
<body>
<div class="wrap">
  <h2>🎯 动作教程</h2>
  <div class="sub">动作列表 + send_goal + 内置动作服务器 | 闭环测试</div>

  <div class="banner" id="env-banner">⚠️ 未检测到 ROS2 环境（PATH 里没有 ros2，也找不到可用的 pixi 项目）。请先在激活了 ROS2 的 shell 里启动 launcher（如 Ubuntu `source`、Windows pixi shell），或在已激活环境下运行；否则动作列表会一直为空。</div>

  <div class="tabs">
    <div class="tab on" onclick="show('goal')">发送目标</div>
    <div class="tab" onclick="show('src')">内置动作服务器</div>
  </div>

  <div class="panel on" id="panel-goal">
    <div class="card">
      <h3>🎯 发送目标 <span class="pill" id="act-count">0</span>
        <button class="sec" onclick="loadActions()" style="margin-left:auto">刷新动作</button>
      </h3>
      <div class="row">
        <select id="act-select"><option value="">选择动作...</option></select>
        <span class="pill" id="act-type"></span>
      </div>
      <div class="row" style="margin-top:8px">
        <label>目标</label>
        <input id="goal-editor" value='{"order": 8}' style="flex:1">
      </div>
      <div class="row">
        <button onclick="sendGoal()">发送目标</button>
        <button class="danger" onclick="cancelGoal()">终止目标</button>
        <button class="sec" onclick="clearLog()">清空</button>
        <span class="status" id="goal-state"></span>
      </div>
      <div class="log" id="goal-log"><span class="sys">选择动作并发送目标，实时反馈将显示在这里。</span></div>
      <div class="code" style="margin-top:8px">提示：先到「内置动作服务器」启动 demo_fib，或在别处运行其它动作服务器。</div>
    </div>
  </div>

  <div class="panel" id="panel-src">
    <div class="card">
      <h3>🔄 内置动作服务器</h3>
      <div class="row">
        <button onclick="toggleSource()" id="src-btn">启动服务器</button>
        <span class="status" id="src-status">未启动</span>
      </div>
      <div class="code" style="margin-top:8px">启动后注册动作 <code>demo_fib</code>（Fibonacci），回「发送目标」选择它：<br>
       ・ 目标：<code>{"order": 8}</code> → 计算前 N 项斐波那契，逐项回传 feedback，最后返回完整 sequence。</div>
    </div>
  </div>
</div>

<script>
function show(name){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('on'));
  var idx={goal:0,src:1}[name];
  document.querySelectorAll('.tab')[idx].classList.add('on');
  document.getElementById('panel-'+name).classList.add('on');
}

function loadActions(){
  fetch('/api/actions').then(r=>r.json()).then(list=>{
    var sel=document.getElementById('act-select');
    var prev=sel.value;
    var html='<option value="">选择动作...</option>';
    list.forEach(a=>html+='<option value="'+a.name+'" data-type="'+a.type+'">'+a.name+(a.type?' ['+a.type+']':'')+'</option>');
    sel.innerHTML=html;
    document.getElementById('act-count').textContent=list.length;
    if(prev){for(var i=0;i<sel.options.length;i++){if(sel.options[i].value===prev){sel.value=prev;break;}}}
    onPick();
  }).catch(()=>{});
}

function onPick(){
  var sel=document.getElementById('act-select');
  var opt=sel.options[sel.selectedIndex];
  var typ=opt?opt.getAttribute('data-type'):'';
  document.getElementById('act-type').textContent=typ||'type?';
}

function sendGoal(){
  var sel=document.getElementById('act-select');
  var action=sel.value;
  if(!action){alert('请先选择动作');return;}
  var typ=sel.options[sel.selectedIndex].getAttribute('data-type')||'';
  var goal=document.getElementById('goal-editor').value||'{}';
  setState('发送中...','yellow');
  fetch('/api/astart?action='+encodeURIComponent(action)+'&type='+encodeURIComponent(typ)+'&goal='+encodeURIComponent(goal))
    .then(r=>r.json()).then(()=>poll()).catch(()=>setState('请求失败','red'));
}

function cancelGoal(){fetch('/api/astop').then(()=>setState('已终止','red')).catch(()=>{});}
function clearLog(){document.getElementById('goal-log').innerHTML='<span class="sys">已清空</span>';}

function setState(txt,cls){
  var el=document.getElementById('goal-state');
  el.textContent=txt; el.className='status '+cls;
}

function poll(){
  fetch('/api/astatus').then(r=>r.json()).then(s=>{
    var log=document.getElementById('goal-log');
    if(s.lines && s.lines.length){
      var html='';
      s.lines.forEach(l=>{
        var cls='ev';
        if(l.indexOf('"type":"feedback"')>=0) cls+=' fb';
        else if(l.indexOf('"type":"result"')>=0){cls+=' ok';evalPhase('done');}
        else if(l.indexOf('"type":"accepted"')>=0) cls+='';
        else if(l.indexOf('"type":"sending"')>=0) cls+=' sys';
        else if(l.indexOf('"type":"error"')>=0||l.indexOf('"type":"rejected"')>=0) cls+=' err';
        html+='<span class="'+cls+'">'+esc(l)+'</span>';
      });
      log.innerHTML=html;
      log.scrollTop=log.scrollHeight;
    }
    var map={connecting:'连接中...',feedback:'进行中 (feedback) ',accepted:'已接受目标',done:'已完成',rejected:'被拒绝',error:'错误',cancelled:'已终止',closed:'已结束'};
    var ph=map[s.phase]||s.phase||'';
    if(s.phase==='feedback') ph+=s.data||'';
    setState(ph, s.phase==='done'?'green':(s.phase==='error'||s.phase==='rejected'||s.phase==='cancelled'?'red':'yellow'));
  }).catch(()=>{});
}
function evalPhase(p){}

function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}

function toggleSource(){
  fetch('/api/asrc/toggle').then(()=>{setTimeout(srcStatus,400);}).catch(()=>{});
}
function srcStatus(){
  fetch('/api/asrc/status').then(r=>r.json()).then(s=>{
    var on=s.status==='running';
    document.getElementById('src-btn').textContent=on?'停止服务器':'启动服务器';
    document.getElementById('src-btn').className=on?'danger':'';
    document.getElementById('src-status').textContent=on?'运行中 (demo_fib)':'未启动';
    document.getElementById('src-status').className='status '+(on?'green':'');
    loadActions();
  }).catch(()=>{});
}

loadActions(); setInterval(loadActions,4000); srcStatus(); setInterval(srcStatus,5000); setInterval(poll,600);
fetch('/api/env').then(r=>r.json()).then(e=>{
  if(!e.ok){document.getElementById('env-banner').style.display='block';}
}).catch(()=>{});
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
        if path == "/api/actions":
            self._json(get_actions())
        elif path == "/api/env":
            self._json({"ok": ros2env.available()})
        elif path == "/api/astart":
            action = q.get("action", [""])[0]
            atype = q.get("type", [""])[0]
            goal = q.get("goal", ['{"order": 8}'])[0]
            start_goal(action or "demo_fib", atype or "example_interfaces/action/Fibonacci", goal)
            self._json({"ok": True})
        elif path == "/api/astop":
            stop_goal()
            self._json({"ok": True})
        elif path == "/api/astatus":
            self._json(current_goal_status())
        elif path == "/api/asrc/status":
            self._json({"status": source_status()})
        elif path == "/api/asrc/toggle":
            if source_status() == "running":
                stop_source()
                self._json({"running": False})
            else:
                start_source()
                self._json({"running": True})
        else:
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, *a): pass


if __name__ == "__main__":
    print(f"[ROS2 Action] 启动成功，监听端口: {PORT}")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    try:
        server.serve_forever()
    finally:
        stop_goal()
        stop_source()
        server.server_close()