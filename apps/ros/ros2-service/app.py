"""ros2-service —— 服务教程：服务列表 + 调用 + 内置服务端（闭环）

- 内置服务端：一键启动服务节点（自带 demo_* 服务），无需外部节点。
- 服务列表：自动检索当前可调用服务（含类型），类似服务查看器。
- 服务调用：选中服务后填入请求参数（ROS2 YAML 格式）调用并查看响应。

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

# 已知服务类型的请求模板（方便一键填写）
REQUEST_TEMPLATES = {
    "example_interfaces/srv/AddTwoInts": "{a: 3, b: 4}",
    "std_srvs/srv/SetBool": "{data: true}",
    "std_srvs/srv/Trigger": "{}",
    "std_srvs/srv/Empty": "{}",
    "example_interfaces/srv/SetBool": "{data: true}",
    "example_interfaces/srv/Trigger": "{}",
}


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

source_proc = [None]  # 内置服务端 Popen


def get_services():
    """返回 [{name, type}]。"""
    stdout, _ = _run_ros2(["service", "list", "-t"], 20)
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


def call_service(service, svc_type, request):
    """调用服务，返回 {ok, out, err}。"""
    # 构造命令，request 用双引号包裹避免 shell 空格问题
    cmd_args = ["service", "call", service, svc_type, f'"{request}"']
    stdout, stderr = _run_ros2(cmd_args)
    return {"ok": not stderr, "out": stdout.strip(), "err": stderr.strip()}


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
        # 只 terminate 最外层（cmd.exe/shell）会把真正的 ROS 服务节点留成孤儿；
        # 整棵进程树清理，确保 demo_* 服务节点一并退出。
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
<title>服务教程</title>
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
textarea{width:100%;padding:10px;background:#0e1220;color:#dbe3f0;border:1px solid #2c3757;
  border-radius:8px;font-family:ui-monospace,Consolas,monospace;font-size:12px;min-height:70px;resize:vertical}
label{font-size:12px;color:#94a3b8;white-space:nowrap}
button{padding:9px 16px;border:none;border-radius:8px;cursor:pointer;font-weight:600;
  font-size:13px;background:#7c5cf0;color:#fff}
button:hover{filter:brightness(1.1)}
button.sec{background:#223053}
button.danger{background:#dc2626}
button:disabled{opacity:.4;cursor:not-allowed}
.status{font-size:12px;color:#94a3b8}
.green{color:#34d399}.red{color:#f87171}.yellow{color:#fbbf24}
.out{background:#0e1220;border:1px solid #26304d;border-radius:8px;padding:10px;
  font-family:ui-monospace,Consolas,monospace;font-size:12px;white-space:pre-wrap;word-break:break-all;
  min-height:60px;max-height:320px;overflow-y:auto;color:#7dd3fc}
.system-msg{color:#64748b;font-style:italic}
.pill{background:#26304d;border-radius:20px;padding:2px 10px;font-size:12px;color:#a5b4fc}
.tabs{display:flex;gap:6px;margin-bottom:14px}
.tab{padding:8px 16px;border-radius:8px;background:#223053;cursor:pointer;color:#94a3b8;font-size:13px}
.tab.on{background:#7c5cf0;color:#fff}
.panel{display:none}.panel.on{display:block}
.hint{font-size:12px;color:#94a3b8;line-height:1.7}
.code{background:#0e1220;border:1px solid #26304d;border-radius:8px;padding:10px;font-size:12px;color:#7dd3fc}
.banner{display:none;background:#7c2d12;border:1px solid #b45309;color:#fdba74;
  border-radius:8px;padding:10px 14px;font-size:13px;margin-bottom:14px;line-height:1.6}
</style>
</head>
<body>
<div class="wrap">
  <h2>🧪 服务教程</h2>
  <div class="sub">服务列表 + 调用 + 内置服务端 | 闭环测试，无需外部节点</div>

  <div class="banner" id="env-banner">⚠️ 未检测到 ROS2 环境（PATH 里没有 ros2，也找不到可用的 pixi 项目）。请先在激活了 ROS2 的 shell 里启动 launcher（如 Ubuntu `source`、Windows pixi shell），或在已激活环境下运行；否则服务列表会一直为空。</div>

  <div class="tabs">
    <div class="tab on" onclick="show('svc')">服务调用</div>
    <div class="tab" onclick="show('src')">内置服务端</div>
  </div>

  <div class="panel on" id="panel-svc">
    <div class="card">
      <h3>🔎 服务调用 <span class="pill" id="svc-count">0</span>
        <button class="sec" onclick="refreshList()" style="margin-left:auto">刷新列表</button>
      </h3>
      <div class="row">
        <select id="svc-select" onchange="onPick()"><option value="">选择服务...</option></select>
        <span class="pill" id="svc-type"></span>
      </div>
      <div class="row" style="margin-top:8px">
        <label>请求参数</label>
        <textarea id="svc-req" placeholder='例如 {a: 3, b: 4}'>{a: 3, b: 4}</textarea>
      </div>
      <div class="row">
        <button onclick="doCall()">调用服务</button>
        <button class="sec" onclick="clearOut()">清空</button>
        <span class="status status-msg" id="call-msg"></span>
      </div>
      <div class="out" id="svc-out"><span class="system-msg">调用结果将显示在这里</span></div>
      <div class="hint" style="margin-top:8px">提示：右上角「刷新」自动检索当前可用服务；先到「内置服务端」启动之后可测 <code>/demo_*</code> 服务。</div>
    </div>
  </div>

  <div class="panel" id="panel-src">
    <div class="card">
      <h3>🔄 内置服务端</h3>
      <div class="row">
        <button onclick="toggleSource()" id="src-btn">启动服务端</button>
        <span class="status" id="src-status">未启动</span>
      </div>
      <div class="code" style="margin-top:8px">启动后注册以下服务，可回到「服务调用」测试：<br>・ /demo_add_two_ints &nbsp;(AddTwoInts) → <code>{a: 3, b: 4}</code><br>・ /demo_setbool &nbsp;(SetBool) → <code>{data: true}</code><br>・ /demo_trigger &nbsp;(Trigger) → <code>{}</code></div>
    </div>
  </div>
</div>

<script>
function show(name){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('on'));
  var idx={svc:0,src:1}[name];
  document.querySelectorAll('.tab')[idx].classList.add('on');
  document.getElementById('panel-'+name).classList.add('on');
}

var TEMPLATES=null;
function ensureTemplates(){ if(TEMPLATES) return; TEMPLATES={}; }

function refreshList(){
  fetch('/api/services').then(r=>r.json()).then(list=>{
    var sel=document.getElementById('svc-select');
    var prev=sel.value;
    var html='<option value="">选择服务...</option>';
    list.forEach(s=>{
      html+='<option value="'+s.name+'" data-type="'+s.type+'">'+s.name+(s.type?' ['+s.type+']':'')+'</option>';
    });
    sel.innerHTML=html;
    document.getElementById('svc-count').textContent=list.length;
    if(prev){for(var i=0;i<sel.options.length;i++){if(sel.options[i].value===prev){sel.value=prev;break;}}}
    if(sel.value) onPick();
  }).catch(()=>{});
}

function onPick(){
  var sel=document.getElementById('svc-select');
  var opt=sel.options[sel.selectedIndex];
  var typ=opt?opt.getAttribute('data-type'):'';
  document.getElementById('svc-type').textContent=typ||'type?';
}

function currentType(){
  var sel=document.getElementById('svc-select');
  var opt=sel.options[sel.selectedIndex];
  return opt?opt.getAttribute('data-type')||'':'';
}

function doCall(){
  var svc=document.getElementById('svc-select').value;
  if(!svc){alert('请先选择服务');return;}
  var typ=currentType();
  var req=document.getElementById('svc-req').value || '{}';
  var msg=document.getElementById('call-msg');
  msg.textContent='调用中...'; msg.className='status yellow';
  fetch('/api/call?service='+encodeURIComponent(svc)+'&type='+encodeURIComponent(typ)+'&req='+encodeURIComponent(req))
    .then(r=>r.json()).then(res=>{
      document.getElementById('svc-out').textContent=(res.out?res.out:'')+(res.err?('\n[ERR]'+res.err):'');
      if(res.err){msg.textContent='调用失败';msg.className='status red';}
      else{msg.textContent='调用完成';msg.className='status green';}
    }).catch(e=>{msg.textContent='错误: '+e;msg.className='status red';});
}

function clearOut(){
  document.getElementById('svc-out').innerHTML='<span class="system-msg">调用结果将显示在这里</span>';
  document.getElementById('call-msg').textContent='';
}

function toggleSource(){
  fetch('/api/srv/toggle').then(()=>{ setTimeout(srcStatus,500);}).catch(()=>{});
}
function srcStatus(){
  fetch('/api/srv/status').then(r=>r.json()).then(s=>{
    var btn=document.getElementById('src-btn');
    var st=document.getElementById('src-status');
    var on = s.status==='running';
    btn.textContent=on?'停止服务端':'启动服务端';
    btn.className=on?'danger':'';
    st.textContent=on?'运行中 (demo_add_two_ints, demo_setbool, demo_trigger)':'未启动';
    st.className='status '+(on?'green':'');
  }).catch(()=>{});
  fetch('/api/services').then(r=>r.json()).then(list=>{
    document.getElementById('svc-count').textContent=list.length;
  }).catch(()=>{});
}

refreshList(); setInterval(refreshList,4000); srcStatus(); setInterval(srcStatus,4000);
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
        if path == "/api/services":
            self._json(get_services())
        elif path == "/api/env":
            self._json({"ok": ros2env.available()})
        elif path == "/api/call":
            svc = q.get("service", [""])[0]
            typ = q.get("type", [""])[0]
            req = q.get("req", ["{}"])[0]
            self._json(call_service(svc, typ, req))
        elif path == "/api/srv/status":
            self._json({"status": source_status()})
        elif path == "/api/srv/toggle":
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
    print(f"[ROS2 Service] 启动成功，监听端口: {PORT}")
    server = ThreadingHTTPServer((os.environ.get("APP_HOST", "127.0.0.1"), PORT), H)
    try:
        server.serve_forever()
    finally:
        stop_source()
        server.server_close()