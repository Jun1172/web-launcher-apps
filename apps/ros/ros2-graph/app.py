"""ros2-graph —— 交互式节点关系图

可视化当前 ROS2 系统里的节点，及其与话题 / 服务 / 动作服务器的连接关系：
- 节点（圆）：发布者、订阅者角色一目了然。
- 话题（菱形） / 服务（方角） / 动作（八角）：作为中间连接池。
- 连线：发布者→话题→订阅者的消息流、客户端→服务端、动作 client→server。

数据来源：`ros2 node list` + 逐个 `ros2 node info <node>`（通过 shared_ros2.run_cli
全局串行，避免并发捣乱 ros2 子进程）。节点多时逐个 info 会较慢，前端显示加载态。
"""
import json, os, sys, threading, time
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import shared_ros2 as ros2env

APP_DIR = Path(__file__).resolve().parent


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

# 关系节标题。英文 key 为 `ros2 node info` 实际输出；中文为兼容中文环境。
_SECTION_HEAD = {
    "Publishers": "publishers", "发布者": "publishers",
    "Subscribers": "subscribers", "Subscription": "subscribers", "订阅者": "subscribers",
    "Services": "services", "服务": "services",
    "Service Servers": "service_servers", "服务端": "service_servers",
    "Service Clients": "service_clients", "客户端": "service_clients",
    "Action Servers": "action_servers", "动作服务端": "action_servers",
    "Action Clients": "action_clients", "动作客户端": "action_clients",
}

_CACHE = {"data": None, "ts": 0, "lock": threading.Lock()}


def _parse_node_info(node, stdout):
    """把 `ros2 node info <node>` 文本解析为关系字典；解析失败返回空字典。

    兼容默认文本与 yaml(-v) 两种输出，节标题（无缩进或 2 空格）后跟缩进>=4 的条目：
      Publically: /name: type    或     Publishers:\n    /name\n      Type: xxx
    """
    res = {"publishers": [], "subscribers": [], "services": [],
           "service_servers": [], "service_clients": [],
           "action_servers": [], "action_clients": []}
    cur = None
    for line in stdout.splitlines():
        s = line.strip()
        if not s:
            continue
        indent = len(line) - len(line.lstrip(" "))
        # 节标题：缩进 0~2 且以冒号结尾、且冒号前的词能匹配到某节
        if s.endswith(":") and indent <= 2:
            head = s[:-1].strip()
            field = _SECTION_HEAD.get(head)
            if field:
                cur = field
            else:
                cur = None  # 未知标题，暂时不归类
            continue
        # 数据条目仅当处于某节内，且缩进>=4 才视为条目
        if cur is None or indent < 4:
            continue
        name = s.split(":", 1)[0].strip()
        if not name or name == cur:
            continue
        res[cur].append(name)
    return res


def _node_pubsub(node):
    stdout, stderr, rc = ros2env.run_cli(["node", "info", node], timeout=25)
    if rc != 0 or not stdout.strip():
        return None
    return _parse_node_info(node, stdout)


def get_graph(force=False):
    """返回完整关系图数据。带 3 秒缓存避免高频刷新反复跑 node info。"""
    with _CACHE["lock"]:
        if not force and _CACHE["data"] and time.time() - _CACHE["ts"] < 3:
            return _CACHE["data"]
        stdout, _, rc = ros2env.run_cli(["node", "list"], timeout=20)
        nodes_raw = [n.strip() for n in stdout.strip().splitlines() if n.strip()]
        nodes = []
        topics, services, actions = set(), set(), set()
        for name in nodes_raw:
            info = _node_pubsub(name)
            if info is None:
                infos = {"publishers": [], "subscribers": [], "services": [],
                         "service_servers": [], "service_clients": [],
                         "action_servers": [], "action_clients": []}
            else:
                infos = info
            nodes.append({"name": name, **infos})
            topics |= set(infos["publishers"]) | set(infos["subscribers"])
            services |= set(infos["services"]) | set(infos["service_servers"]) | set(infos["service_clients"])
            actions |= set(infos["action_servers"]) | set(infos["action_clients"])
        data = {
            "nodes": nodes,
            "topics": sorted(topics),
            "services": sorted(services),
            "actions": sorted(actions),
            "ts": time.time(),
        }
        _CACHE["data"], _CACHE["ts"] = data, time.time()
        return data


def shutdown_all():
    pass


# ── 前端 ──────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>关系图</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#0e1220;color:#dbe3f0;font-family:system-ui}
.wrap{padding:16px}
.head{display:flex;align-items:center;gap:12px;margin-bottom:12px;flex-wrap:wrap}
h2{color:#67e8f9;margin:0;font-size:20px}
.sub{color:#64748b;font-size:13px}
button{padding:8px 16px;border:none;border-radius:8px;cursor:pointer;font-weight:600;font-size:13px;background:#0891b2;color:#fff}
button:hover{filter:brightness(1.1)}
button.sec{background:#223053}
.stats{font-size:12px;color:#94a3b8}
.legend{display:flex;gap:14px;font-size:12px;color:#94a3b8;flex-wrap:wrap}
.legend i{display:inline-block;width:12px;height:12px;margin-right:4px;vertical-align:-1px}
.grid{display:flex;gap:12px;height:calc(100vh - 120px);min-height:420px}
#canvas-panel{flex:1;background:#121829;border:1px solid #1f2b45;border-radius:12px;position:relative;overflow:hidden}
#graph{margin:0;display:block}
.side{width:230px;background:#171c30;border:1px solid #26304d;border-radius:12px;padding:12px;overflow-y:auto;font-size:12px}
.side h4{margin:0 0 8px;font-size:13px;color:#e2e8f0}
.pool{margin-bottom:14px}
.tag{display:inline-block;background:#223053;border-radius:6px;padding:2px 8px;margin:2px;color:#a5b4fc;font-size:11px}
.nodelist{max-height:220px;overflow-y:auto;margin-bottom:10px}
.nli{padding:4px 6px;border-radius:6px;cursor:pointer;color:#c7d2fe}
.nli:hover{background:#1f2b45}
.nli.on{background:#0891b2;color:#fff}
.emptyload{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#475569;font-size:14px;flex-direction:column;gap:10px}
.toast{position:fixed;top:16px;right:16px;padding:10px 16px;border-radius:8px;font-size:13px;z-index:99;display:none}
.toast.ok{background:#065f46;color:#fff}.toast.err{background:#7c2d12;color:#fff}
</style>
</head>
<body>
<div class="wrap">
  <div class="head">
    <h2>🕸️ ROS2 关系图</h2>
    <button onclick="refresh()">🔄 刷新</button>
    <button class="sec" onclick="auto=!auto;document.getElementById('auto-btn').textContent=auto?'自动 ON':'自动 OFF'">自动 OFF</button>
    <span class="stats" id="stats"></span>
  </div>
  <div class="legend">
    <span><i style="background:#7c5cf0;border-radius:50%"></i>节点</span>
    <span><i style="background:#f59e0b;transform:rotate(45deg);border-radius:3px"></i>话题</span>
    <span><i style="background:#34d399"></i>服务</span>
    <span><i style="background:#f472b6"></i>动作</span>
    <span style="color:#64748b">（鼠标滚轮缩放，拖动画布）</span>
  </div>
  <div class="grid">
    <div id="canvas-panel">
      <svg id="graph"></svg>
      <div class="emptyload" id="loading"><span>正在扫描节点关系（逐个 node info 较慢，请稍候）…</span><button class="sec" onclick="refresh(true)">强制刷新</button></div>
    </div>
    <div class="side">
      <h4>📦 话题</h4>
      <div class="pool" id="topics-pool"></div>
      <h4>🧪 服务</h4>
      <div class="pool" id="svcs-pool"></div>
      <h4>🎯 动作</h4>
      <div class="pool" id="acts-pool"></div>
      <h4>⚙️ 节点</h4>
      <div class="nodelist" id="nodes-list"></div>
    </div>
  </div>
</div>
<div class="toast" id="toast"></div>
<script>
var DATA=null, auto=false, selectedNode=null;
var SVG_NS='http://www.w3.org/2000/svg';
var svg=document.getElementById('graph');
function toast(m,ok){var t=document.getElementById('toast');t.textContent=m;t.style.background=ok?'#065f46':'#7c2d12';t.style.display='block';clearTimeout(t._t);t._t=setTimeout(()=>t.style.display='none',1500);}

function refresh(force){
  var ld=document.getElementById('loading');
  ld.style.display='flex'; svg.innerHTML='';
  fetch('/api/graph?_t='+Date.now()+(force?'&force=1':'')).then(r=>r.json()).then(g=>{
    DATA=g; document.getElementById('loading').style.display='none';
    render();
  }).catch(()=>{document.getElementById('loading').innerHTML='<span style="color:#f87171">扫描失败</span><button class="sec" onclick="refresh(true)">重试</button>';});
}

function layout(g, W, H){
  // 话题/服务/动作放中间一列，节点分布在左右两侧；key 用与渲染一致的前缀(T:/S:/A:)
  var prefix={};
  g.topics.forEach(t=>prefix[t]='T:');
  g.services.forEach(s=>prefix[s]='S:');
  g.actions.forEach(a=>prefix[a]='A:');
  var mids=Object.keys(prefix);
  var nodes=g.nodes;
  var MARGIN=70;
  var slots=Math.max(nodes.length, mids.length||1);
  var slotH=(H-40)/Math.max(slots,1);
  var pos={};
  mids.forEach((m,i)=>{ pos[prefix[m]+m]={x:W/2, y:30+slotH*(i+0.5)}; });
  var nPos=nodes.map((n,i)=>({n:n, y:30+slotH*(i+0.5)}));
  var half=Math.ceil(nodes.length/2);
  nodes.forEach((n,i)=>{ pos[n.name]={x: i<half? MARGIN : W-MARGIN, y: nPos[i].y}; });
  return pos;
}

function render(){
  if(!DATA)return;
  var panel=document.getElementById('canvas-panel');
  var W=panel.clientWidth, H=panel.clientHeight;
  svg.setAttribute('width',W); svg.setAttribute('height',H);
  svg.innerHTML='';
  // 背景网格
  var defs=document.createElementNS(SVG_NS,'defs');
  var pat=document.createElementNS(SVG_NS,'pattern');
  pat.id='dot';pat.setAttribute('patternUnits','userSpaceOnUse');pat.setAttribute('width','40');pat.setAttribute('height','40');
  var c=document.createElementNS(SVG_NS,'circle');c.setAttribute('cx','1');c.setAttribute('cy','1');c.setAttribute('r','1');c.setAttribute('fill','#1f2b45');
  pat.appendChild(c);defs.appendChild(pat);svg.appendChild(defs);
  var bg=document.createElementNS(SVG_NS,'rect');bg.setAttribute('width',W);bg.setAttribute('height',H);bg.setAttribute('fill','url(#dot)');svg.appendChild(bg);

  var pos=layout(DATA,W,H);
  var nodeById={}; DATA.nodes.forEach(n=>nodeById[n.name]=n);
  var connections=[]; // {x1,y1,x2,y2,kind}

  // 连线：发布者→话题→订阅者；client→server
  function link(a,b,kind){ if(!a||!b)return; var pa=pos[a],pb=pos[b]; if(!pa||!pb)return; connections.push({a:a,b:b,kind:kind}); }

  DATA.nodes.forEach(n=>{
    n.publishers.forEach(t=>link(n.name,'T:'+t,'pub'));
    n.subscribers.forEach(t=>link('T:'+t,n.name,'sub'));
    n.service_servers.forEach(s=>link('S:'+s,n.name,'srv'));
    n.service_clients.forEach(s=>link(n.name,'S:'+s,'srv'));
    n.action_servers.forEach(a=>link('A:'+a,n.name,'act'));
    n.action_clients.forEach(a=>link(n.name,'A:'+a,'act'));
  });
  // topic/service/action 池的名称映射
  var T={},S={},A={};
  DATA.topics.forEach(t=>T['T:'+t]=t); DATA.services.forEach(s=>S['S:'+s]=s); DATA.actions.forEach(a=>A['A:'+a]=a);
  // 连线绘制放最底层
  connections.forEach(l=>{
    var pa=pos[l.a],pb=pos[l.b];
    var line=document.createElementNS(SVG_NS,'line');
    line.setAttribute('x1',pa.x);line.setAttribute('y1',pa.y);line.setAttribute('x2',pb.x);line.setAttribute('y2',pb.y);
    var color={pub:'#7c5cf0',sub:'#7dd3fc',srv:'#34d399',act:'#f472b6'}[l.kind]||'#475569';
    line.setAttribute('stroke',color);line.setAttribute('stroke-width','1.5');
    line.setAttribute('stroke-opacity', l.kind==='srv'||l.kind==='act'?0.6:0.5);
    line.setAttribute('stroke-dasharray', (l.kind==='sub')?'4 3':'');
    svg.appendChild(line);
  });
  // 中间池（话题→菱形、服务→方角、动作→八角）
  Object.keys(T).concat(Object.keys(S)).concat(Object.keys(A)).forEach(k=>{
    var p=pos[k]; if(!p)return;
    var full,color;
    if(T[k]){full=T[k];color='#f59e0b';} else if(S[k]){full=S[k];color='#34d399';} else {full=A[k];color='#f472b6';}
    var shape=(k[0]==='T')?'rect':(k[0]==='S')?'rect':'rect';
    var g=document.createElementNS(SVG_NS,'g');
    var rect=document.createElementNS(SVG_NS,'rect');
    var w=Math.max(120, full.length*7+30), h=22;
    rect.setAttribute('x',p.x-w/2);rect.setAttribute('y',p.y-h/2);rect.setAttribute('width',w);rect.setAttribute('height',h);
    rect.setAttribute('rx', k[0]==='A'?4:6);
    rect.setAttribute('fill',color);rect.setAttribute('fill-opacity','0.15');
    rect.setAttribute('stroke',color);rect.setAttribute('stroke-width','1.2');
    var txt=document.createElementNS(SVG_NS,'text');
    txt.setAttribute('x',p.x);txt.setAttribute('y',p.y+4);txt.setAttribute('text-anchor','middle');
    txt.setAttribute('fill',color);txt.setAttribute('font-size','11');
    txt.textContent=full;
    g.appendChild(rect); g.appendChild(txt); svg.appendChild(g);
  });
  // 节点
  DATA.nodes.forEach(n=>{
    var p=pos[n.name]; if(!p)return;
    var g=document.createElementNS(SVG_NS,'g');
    g.style.cursor='pointer'; g.dataset.node=n.name;
    g.addEventListener('click',()=>{selectedNode=selectedNode===n.name?null:n.name;render();});
    var on=selectedNode===n.name;
    var circle=document.createElementNS(SVG_NS,'circle');
    circle.setAttribute('cx',p.x);circle.setAttribute('cy',p.y);circle.setAttribute('r',16);
    circle.setAttribute('fill', on?'#6d28d9':'#7c5cf0');circle.setAttribute('stroke','#a78bfa');
    circle.setAttribute('stroke-width',on?2.5:1.2);
    var txt=document.createElementNS(SVG_NS,'text');
    txt.setAttribute('x',p.x);txt.setAttribute('y',p.y+28);txt.setAttribute('text-anchor','middle');
    txt.setAttribute('fill','#c7d2fe');txt.setAttribute('font-size','11');
    txt.textContent=n.name;
    // 角色角标
    g.appendChild(circle); g.appendChild(txt);
    svg.appendChild(g);
  });

  // 侧栏
  document.getElementById('topics-pool').innerHTML=(DATA.topics||[]).map(t=>'<span class="tag">'+esc(t)+'</span>').join('')||'<span style="color:#475569">无</span>';
  document.getElementById('svcs-pool').innerHTML=(DATA.services||[]).map(t=>'<span class="tag">'+esc(t)+'</span>').join('')||'<span style="color:#475569">无</span>';
  document.getElementById('acts-pool').innerHTML=(DATA.actions||[]).map(t=>'<span class="tag">'+esc(t)+'</span>').join('')||'<span style="color:#475569">无</span>';
  document.getElementById('nodes-list').innerHTML=(DATA.nodes||[]).map(n=>'<div class="nli'+(selectedNode===n.name?' on':'')+'" onclick="selNode(\''+esc(n.name.replace(/'/g,"\\'"))+'\')">'+esc(n.name)+'</div>').join('')||'<div style="color:#475569">无节点</div>';
  document.getElementById('stats').textContent=(DATA.nodes||[]).length+' 节点 · '+(DATA.topics||[]).length+' 话题 · '+(DATA.services||[]).length+' 服务 · '+(DATA.actions||[]).length+' 动作';
}
function selNode(n){selectedNode=selectedNode===n?null:n;render();}

function esc(s){return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}

// 缩放与拖动
(function(){
  var scale=1,tx=0,ty=0,drag=null;
  function apply(){svg.style.transform='scale('+scale+') translate('+tx+'px,'+ty+'px)';svg.style.transformOrigin='0 0';}
  svg.addEventListener('wheel',e=>{e.preventDefault();var d=e.deltaY<0?1.12:0.89;scale=Math.max(0.2,Math.min(3,scale*d));apply();},{passive:false});
  svg.addEventListener('pointerdown',e=>{if(e.target!==svg){return;}drag={x:e.clientX,y:e.clientY,tx:tx,ty:ty};svg.setPointerCapture(e.pointerId);});
  svg.addEventListener('pointermove',e=>{if(!drag)return;tx=drag.tx+(e.clientX-drag.x);ty=drag.ty+(e.clientY-drag.y);apply();});
  svg.addEventListener('pointerup',()=>drag=null);
})();
document.getElementById('auto-btn').addEventListener('click',function(){auto=!auto;this.textContent=auto?'自动 ON':'自动 OFF';if(auto)refresh();});
setInterval(()=>{if(auto)refresh();},8000);
window.addEventListener('resize',()=>{if(DATA)render();});
refresh();
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
        if path == "/api/graph":
            self._json(get_graph(force="force" in q))
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
    print(f"[ROS2 Graph] 启动成功，监听端口: {PORT}")
    server = ThreadingHTTPServer((os.environ.get("APP_HOST", "127.0.0.1"), PORT), H)
    try:
        server.serve_forever()
    finally:
        shutdown_all()
        server.server_close()