"""ros2-param —— 参数教程：节点/参数查询 + get/set + 内置参数节点（闭环）

- 节点查询：自动检索 `ros2 node list`，选中即列出该节点参数，类似参数查看器。
- 参数操作：对任意参数 get / set 并回读确认，`count` 每秒自增会实时刷新。
- 内置参数节点：一键启动 / 停止 `param_demo`（自带 6 个示例参数），无需外部节点。

进程清理：启动前清掉残留同名节点，停止/应用退出时用 kill_proc_tree 整树强杀，
保证 ROS 节点不残留。查询统一走 shared_ros2.run_cli（全局串行 + 超时整树清理），
既避免并发 ros2 子进程堆积导致"请求异常"，也避免超时后孙进程残留。
"""
import json, os, sys, subprocess, threading, time
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import shared_ros2 as ros2env

APP_DIR = Path(__file__).resolve().parent
SOURCE_PY = APP_DIR / "source.py"

# 参数名 -> 说明；仅用于前端提示
PARAM_HINTS = {
    "int_param": "整数参数",
    "float_param": "浮点参数",
    "str_param": "字符串参数",
    "bool_param": "布尔参数",
    "int_array": "整数数组",
    "count": "每秒自增(动态)",
}

LOCK = threading.Lock()
source_proc = [None]


def get_port():
    env_port = os.environ.get("LAUNCHER_APP_PORT")
    if env_port:
        try:
            return int(env_port)
        except ValueError:
            pass
    j = APP_DIR / "app.json"
    if j.exists():
        try:
            return int(json.loads(j.read_text(encoding="utf-8")).get("port", 0))
        except Exception:
            pass
    return 0


PORT = get_port()


def _env_error():
    return ("未检测到 ROS2 环境（PATH 里没有 ros2，也找不到可用的 pixi 项目）。"
            "请先在激活了 ROS2 的 shell 里启动 launcher。")


def _run_ros2(args, timeout=25):
    # 全局串行 + 超时整树清理，避免并发子进程堆积/残留
    return ros2env.run_cli(args, timeout=timeout)


# ── 节点 & 参数查询 ──────────────────────────────
def get_nodes():
    if not ros2env.available():
        return []
    stdout, _, _ = _run_ros2(["node", "list"], 20)
    return [n.strip() for n in stdout.strip().splitlines() if n.strip()]


def get_params(node):
    """返回参数对象列表 [{name}, ...]；失败时返回 {'error': <原因>}。

    前端 renderParams() 用 p.name 读参数名，这里必须给对象而非纯字符串，
    否则 p.name = undefined → undefined.replace() 抛 TypeError，Promise
    .then() 里的同步异常会穿透到链尾 .catch()，误显示"请求异常"。

    空结果也重试：节点刚启动 DDS 尚未注册稳、或撞上残留幽灵节点时，
    `ros2 param list` 可能 rc=0 但没输出，直接返回会误报"0 参数"。
    """
    if not ros2env.available():
        return {"error": _env_error()}
    for attempt in range(4):
        stdout, stderr, rc = _run_ros2(["param", "list", node], 20)
        if rc != 0 or stderr.strip():
            time.sleep(0.6)
            continue
        names = [ln.strip() for ln in stdout.strip().splitlines() if ln.strip()]
        if names:
            return [{"name": n} for n in names]
        if attempt < 3:
            time.sleep(1.0)
            continue
    base = node.lstrip("/")
    if base not in [n.lstrip("/") for n in get_nodes()]:
        return {"error": "节点 %s 当前不在 `ros2 node list` 中（可能是刚退出或未完成注册的残留）。请稍后重试，或先停止再重新启动节点。" % node}
    return {"error": "节点 %s 在线，但 `ros2 param list` 未返回任何参数（ROS2/DDS 发现异常，可能是残留了多个同名节点）。" % node}


def param_get(node, param):
    if not ros2env.available():
        return {"value": "", "error": _env_error()}
    stdout, stderr, _ = _run_ros2(["param", "get", node, param], 20)
    val = stdout.strip()
    if stderr.strip():
        return {"value": "", "error": stderr.strip()[:400]}
    if ": " in val:
        val = val.split(": ", 1)[1].strip()
    return {"value": val, "error": ""}


def param_set(node, param, value):
    stdout, stderr, _ = _run_ros2(["param", "set", node, param, value], 20)
    out = stdout.strip() or stderr.strip()
    ok = ("set to" in stdout) or (not stderr and bool(stdout.strip()))
    return {"ok": ok, "out": out}


# ── 内置参数节点 ─────────────────────────────────
def is_running():
    p = source_proc[0]
    if p is not None and p.poll() is None:
        return True
    if p is not None:
        source_proc[0] = None
    return False


def start_source():
    if is_running():
        return True
    # 清掉可能残留的同名 param_demo（避免幽灵节点导致查到死节点/误报 0 参数）
    ros2env.kill_script("ros2-param%s%s" % (os.sep, SOURCE_PY.name))
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
        # 整棵进程树清理，确保 param_demo 一并退出，不留孤儿
        ros2env.kill_proc_tree(p.pid)
        try:
            p.wait(timeout=3)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass


def shutdown_all():
    stop_source()


# ── 前端 ─────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>参数教程</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#0e1220;color:#dbe3f0;font-family:system-ui}
.wrap{max-width:920px;margin:0 auto;padding:20px}
h2{color:#a78bfa;margin:0 0 4px;font-size:20px}
.sub{color:#64748b;font-size:13px;margin-bottom:18px}
.card{background:#171c30;border:1px solid #26304d;border-radius:12px;padding:18px;margin-bottom:16px}
.card h3{margin:0 0 12px;font-size:15px;color:#e2e8f0;display:flex;align-items:center;gap:8px}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center}
select,input{flex:1;min-width:140px;padding:9px 10px;background:#0e1220;color:#dbe3f0;
  border:1px solid #2c3757;border-radius:8px;font-size:13px}
label{font-size:12px;color:#94a3b8;white-space:nowrap}
button{padding:9px 16px;border:none;border-radius:8px;cursor:pointer;font-weight:600;
  font-size:13px;background:#7c5cf0;color:#fff}
button:hover{filter:brightness(1.1)}
button.sec{background:#223053}
button.danger{background:#dc2626}
button.small{padding:6px 12px;font-size:12px}
.status{font-size:12px;color:#94a3b8}
.green{color:#34d399}.red{color:#f87171}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid #26304d}
th{color:#94a3b8;font-weight:600;font-size:12px}
td .val{font-family:ui-monospace,monospace;color:#7dd3fc;word-break:break-all}
.empty{color:#475569;text-align:center;padding:26px;font-size:13px}
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
  <h2>🔧 参数教程</h2>
  <div class="sub">节点/参数查询 + get/set | 内置参数节点闭环测试</div>

  <div class="banner" id="env-banner">⚠️ 未检测到 ROS2 环境（PATH 里没有 ros2，也找不到可用的 pixi 项目）。请先在激活了 ROS2 的 shell 里启动 launcher（如 Ubuntu `source`、Windows pixi shell）。</div>

  <div class="tabs">
    <div class="tab on" onclick="show('pm')">参数操作</div>
    <div class="tab" onclick="show('src')">内置参数节点</div>
  </div>

  <div class="panel on" id="panel-pm">
    <div class="card">
      <h3>📦 参数操作 <button class="sec" onclick="loadNodes()" style="margin-left:auto">刷新节点</button></h3>
      <div class="row">
        <select id="node-select" onchange="onNode(0)"><option value="">选择节点...</option></select>
        <span class="pill" id="param-count">0 参数</span>
      </div>
      <table>
        <thead><tr><th style="width:30%">参数名</th><th style="width:22%">当前值</th><th>新值</th><th></th></tr></thead>
        <tbody id="pbody"><tr><td colspan="4" class="empty">先选择节点</td></tr></tbody>
      </table>
      <div class="status" id="pm-msg" style="margin-top:8px"></div>
    </div>
  </div>

  <div class="panel" id="panel-src">
    <div class="card">
      <h3>🔄 内置参数节点</h3>
      <div class="row">
        <button onclick="toggleSource()" id="src-btn">启动参数节点</button>
        <span class="status" id="src-status">未启动</span>
      </div>
      <div class="code" style="margin-top:8px">启动节点 <code>param_demo</code> 后，回到「参数操作」选择它即可 get/set：<br>
       ・ int_param = 42 &nbsp;・ float_param = 3.14<br>
       ・ str_param = "hello" &nbsp;・ bool_param = true<br>
       ・ int_array = [1,2,3,4] &nbsp;・ count = （每秒自增）</div>
    </div>
  </div>
</div>
<div class="toast" id="toast"></div>

<script>
// 缓存破坏：给所有 GET 请求追加时间戳，避免浏览器缓存旧的错误响应
function noCache(u){return u+(u.indexOf('?')>=0?'&':'?')+'_t='+Date.now();}
function show(name){
  document.querySelectorAll('.tab').forEach(function(t){t.classList.remove('on')});
  document.querySelectorAll('.panel').forEach(function(p){p.classList.remove('on')});
  var idx={pm:0,src:1}[name];
  document.querySelectorAll('.tab')[idx].classList.add('on');
  document.getElementById('panel-'+name).classList.add('on');
}
function toast(msg,ok){
  var t=document.getElementById('toast');
  t.textContent=msg;
  t.style.background=ok?'#065f46':'#7c2d12'; t.style.color='#fff';
  t.style.display='block';
  clearTimeout(t._t);
  t._t=setTimeout(function(){t.style.display='none';},1500);
}

var _loaded='', _busy=false;
function loadNodes(){
  fetch(noCache('/api/nodes')).then(function(r){return r.json()}).then(function(nodes){
    var sel=document.getElementById('node-select');
    var prev=sel.value;
    var html='<option value="">选择节点...</option>';
    nodes.forEach(function(n){html+='<option value="'+n+'">'+n+'</option>';});
    sel.innerHTML=html;
    if(prev && nodes.indexOf(prev)>=0){sel.value=prev;}
  }).catch(function(){});
}

function onNode(attempt){
  var node=document.getElementById('node-select').value;
  if(!node){_loaded='';document.getElementById('pbody').innerHTML='<tr><td colspan="4" class="empty">先选择节点</td></tr>';document.getElementById('param-count').textContent='0 参数';return;}
  if(_busy){return;}
  _busy=true;
  document.getElementById('pbody').innerHTML='<tr><td colspan="4" class="empty">加载中...</td></tr>';
  fetch(noCache('/api/params?node='+encodeURIComponent(node))).then(function(r){return r.json()}).then(function(res){
    _busy=false;
    if(document.getElementById('node-select').value!==node){return;} // 已切换节点则丢弃
    if(res && res.error){_loaded='';renderEmpty('⚠️ '+esc(res.error));return;}
    var list=res||[];
    if(!list.length && (attempt||0)<3){
      document.getElementById('pbody').innerHTML='<tr><td colspan="4" class="empty">节点初始化中，自动重试...</td></tr>';
      setTimeout(function(){onNode((attempt||0)+1);},1200);
      return;
    }
    _loaded=node; renderParams(node,list);
  }).catch(function(){_busy=false;_loaded='';renderEmpty('请求异常，请稍后重试');});
}

function renderEmpty(msg){
  document.getElementById('pbody').innerHTML='<tr><td colspan="4" class="empty">'+msg+'</td></tr>';
  document.getElementById('param-count').textContent='0 参数';
}
function esc(s){return (s||'').replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c]});}
function sid(n){return encodeURIComponent(n);}

function renderParams(node,list){
  var hints=window._HINTS||{};
  document.getElementById('param-count').textContent=list.length+' 参数';
  var html='';
  list.forEach(function(p){
    var hint=hints[p.name]||'';
    html+='<tr data-p="'+p.name+'">'+
      '<td>'+esc(p.name)+(hint?' <span style="color:#64748b;font-size:11px">('+hint+')</span>':'')+'</td>'+
      '<td class="val" id="val-'+sid(p.name)+'">…</td>'+
      '<td><input id="inp-'+sid(p.name)+'" placeholder="新值" style="min-width:0"></td>'+
      '<td style="text-align:right"><button class="sec small" onclick="doSet(\''+p.name.replace(/'/g,"\\'")+'\')">设置</button></td>'+
      '</tr>';
  });
  document.getElementById('pbody').innerHTML=html;
  list.forEach(function(p){refreshVal(node,p.name);});
}

function refreshVal(node,param){
  return fetch(noCache('/api/get?node='+encodeURIComponent(node)+'&param='+encodeURIComponent(param)))
    .then(function(r){return r.json()}).then(function(res){
      var el=document.getElementById('val-'+sid(param));
      if(!el) return;
      if(!res || (res.error&&res.value)){el.textContent=res.value||'∅';return;}
      if(res && res.error){el.textContent='';return;}
      el.textContent=res.value||'∅';
    }).catch(function(){});
}

function doSet(param){
  var node=document.getElementById('node-select').value;
  var inp=document.getElementById('inp-'+sid(param));
  if(!inp||!inp.value){toast('请输入新值',false);return;}
  fetch(noCache('/api/set?node='+encodeURIComponent(node)+'&param='+encodeURIComponent(param)+'&value='+encodeURIComponent(inp.value)))
    .then(function(r){return r.json()}).then(function(res){
      if(res.ok){toast('已设置 '+param+' = '+inp.value,true);refreshVal(node,param);}
      else{toast(res.out||'设置失败',false);}
    }).catch(function(){toast('请求失败',false);});
}

function toggleSource(){
  fetch(noCache('/api/psrc/toggle')).then(function(){
    setTimeout(function(){
      srcStatus(); loadNodes();
      setTimeout(autoSelect,700);
    },400);
  }).catch(function(){});
}
function autoSelect(){
  var sel=document.getElementById('node-select');
  for(var i=0;i<sel.options.length;i++){
    if(sel.options[i].value.indexOf('param_demo')>=0){
      if(sel.value!==sel.options[i].value){sel.value=sel.options[i].value;onNode(0);}
      else if(!_loaded){onNode(0);}
      return;
    }
  }
}
function srcStatus(){
  fetch(noCache('/api/psrc/status')).then(function(r){return r.json()}).then(function(s){
    var on=s.running;
    var btn=document.getElementById('src-btn');
    btn.textContent=on?'停止参数节点':'启动参数节点';
    btn.className=on?'danger':'';
    var st=document.getElementById('src-status');
    st.textContent=on?'运行中 (param_demo)':'未启动';
    st.className='status '+(on?'green':'');
  }).catch(function(){});
}

fetch(noCache('/api/hints')).then(function(r){return r.json()}).then(function(h){
  window._HINTS=h;
  window._VOLATILE=[];
  for(var k in h){if(/自增|递增|计数|动态/.test(h[k])){window._VOLATILE.push(k);}}
}).catch(function(){window._HINTS={};window._VOLATILE=[];});

loadNodes(); setInterval(loadNodes,12000); srcStatus(); setInterval(srcStatus,6000);
// 仅周期刷新"动态参数"(如 count)，避免全量 get 在串行锁下堆积
var _refVol=false;
setInterval(function(){
  if(!_loaded||_busy||_refVol) return;
  var targets=window._VOLATILE||[];
  if(!targets.length) return;
  _refVol=true;
  Promise.all(targets.map(function(n){return refreshVal(_loaded,n);}))
    .then(function(){_refVol=false;}).catch(function(){_refVol=false;});
},6000);

fetch(noCache('/api/env')).then(function(r){return r.json()}).then(function(e){
  if(!e.ok){document.getElementById('env-banner').style.display='block';}
}).catch(function(){});
</script>
</body>
</html>"""


class H(BaseHTTPRequestHandler):
    def _json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urlparse(self.path)
        q = parse_qs(p.query)
        path = p.path
        if path == "/api/nodes":
            self._json(get_nodes())
        elif path == "/api/env":
            self._json({"ok": ros2env.available()})
        elif path == "/api/params":
            node = q.get("node", [""])[0]
            self._json(get_params(node) if node else [])
        elif path == "/api/get":
            node = q.get("node", [""])[0]
            param = q.get("param", [""])[0]
            self._json(param_get(node, param))
        elif path == "/api/set":
            node = q.get("node", [""])[0]
            param = q.get("param", [""])[0]
            value = q.get("value", [""])[0]
            self._json(param_set(node, param, value))
        elif path == "/api/hints":
            self._json(PARAM_HINTS)
        elif path == "/api/psrc/status":
            self._json({"running": is_running()})
        elif path == "/api/psrc/toggle":
            if is_running():
                stop_source()
                self._json({"running": False})
            else:
                start_source()
                self._json({"running": True})
        else:
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"[ROS2 Param] 启动成功，监听端口: {PORT}")
    server = ThreadingHTTPServer((os.environ.get("APP_HOST", "127.0.0.1"), PORT), H)
    try:
        server.serve_forever()
    finally:
        shutdown_all()
        server.server_close()