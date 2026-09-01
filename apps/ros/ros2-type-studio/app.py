"""ros2-type-studio —— 消息工作室：类型模板库 + 实时波形/消息查看器

- 类型模板库：内置常用 ROS2 消息类型模板，选模板自动填充类型与消息 JSON，可自定义任意类型/消息。
- 发布：source.py 增强发布器（$i 递归递增），支持一次/循环发布。
- 实时波形/消息查看：subscribe.py 通用订阅器订阅任意类型话题，自动提取数值通道，
  Canvas 画实时曲线 + 原始消息回显（发布 → 立即在下方看波形，闭环演示）。

跨平台 ROS2 环境探测由 shared_ros2 提供。
"""
import json, os, sys, subprocess, threading, time
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import shared_ros2 as ros2env

APP_DIR = Path(__file__).resolve().parent
SOURCE_PY = APP_DIR / "source.py"
SUB_PY = APP_DIR / "subscribe.py"


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

# ── 类型模板库 ────────────────────────────────────────
TEMPLATES = [
    {"id": "String", "name": "字符串 std_msgs/String",
     "type": "std_msgs/String", "payload": {"data": "Hello ROS2 $i"}},
    {"id": "Float64", "name": "浮点 std_msgs/Float64",
     "type": "std_msgs/Float64", "payload": {"data": "$i"}},
    {"id": "Int32", "name": "整数 std_msgs/Int32",
     "type": "std_msgs/Int32", "payload": {"data": "$i"}},
    {"id": "Bool", "name": "布尔 std_msgs/Bool",
     "type": "std_msgs/Bool", "payload": {"data": True}},
    {"id": "Int32MultiArray", "name": "整数数组 std_msgs/Int32MultiArray",
     "type": "std_msgs/Int32MultiArray", "payload": {"data": [1, 2, 3, 4, 5]}},
    {"id": "Float64MultiArray", "name": "浮点数组 std_msgs/Float64MultiArray",
     "type": "std_msgs/Float64MultiArray", "payload": {"data": [1.1, 2.2, 3.3]}},
    {"id": "Point", "name": "点 geometry_msgs/Point",
     "type": "geometry_msgs/Point", "payload": {"x": 1.0, "y": 2.0, "z": 3.0}},
    {"id": "Vector3", "name": "向量 geometry_msgs/Vector3",
     "type": "geometry_msgs/Vector3", "payload": {"x": 0.0, "y": 0.0, "z": 1.0}},
    {"id": "Twist", "name": "速度 geometry_msgs/Twist",
     "type": "geometry_msgs/Twist",
     "payload": {"linear": {"x": "$i"}, "angular": {"z": 0.5}}},
    {"id": "Imu", "name": "惯性 sensor_msgs/Imu",
     "type": "sensor_msgs/Imu",
     "payload": {"linear_acceleration": {"x": 9.81}, "angular_velocity": {"z": "$i"}}},
    {"id": "JointState", "name": "关节态 sensor_msgs/JointState",
     "type": "sensor_msgs/JointState",
     "payload": {"name": ["j1", "j2"], "position": [0.0, 0.5], "velocity": [0.0, 0.0]}},
    {"id": "Custom", "name": "✏️ 自定义类型…", "type": "", "payload": {}},
]

pub_procs = {}
LOCK = threading.Lock()


def _spawn_pub(topic, mtype, rate, payload, count=0):
    stop_pub()
    env = dict(os.environ)
    env.update({
        "PUB_TOPIC": topic, "PUB_TYPE": mtype, "PUB_RATE": str(rate),
        "PUB_PAYLOAD": payload, "PUB_COUNT": str(count),
    })
    py, cwd = ros2env.python_command()
    cmd = f'{py} "{SOURCE_PY}"'
    p = subprocess.Popen(cmd, shell=True, cwd=cwd, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8", errors="replace",
                         **ros2env.source_popen_kwargs())
    with LOCK:
        pub_procs["pub"] = p
    return p


def stop_pub():
    with LOCK:
        p = pub_procs.pop("pub", None)
    if p and p.poll() is None:
        ros2env.kill_proc_tree(p.pid)
        try: p.wait(timeout=3)
        except Exception:
            try: p.kill()
            except Exception: pass


def pub_status():
    with LOCK:
        p = pub_procs.get("pub")
    return {"running": bool(p) and p.poll() is None,
            "exit": None if (p is None or p.poll() is None) else p.poll()}


# ── 波形 / 消息查看（通用订阅） ────────────────────────
#   {topic: {"proc": Popen, "raws": [...], "sums": [...], "heads": [], "error": str|None}}
_active = {}


def run_ros2(args, timeout=20):
    return ros2env.run_cli(args, timeout=timeout)


def _shorten_type(t):
    """std_msgs/msg/Int32MultiArray -> std_msgs/Int32MultiArray，与发布端写法一致。"""
    parts = [p for p in t.split("/") if p]
    if len(parts) == 3 and parts[1].lower() in ("msg", "srv", "action"):
        return parts[0] + "/" + parts[2]
    return t


def get_topics():
    stdout, _, _ = run_ros2(["topic", "list", "-t"], 20)
    out = []
    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if "[" in line and line.endswith("]"):
            name = line.split("[")[0].strip()
            typ = _shorten_type(line.split("[")[1].rstrip("]").strip())
            out.append({"name": name, "type": typ})
        else:
            out.append({"name": line, "type": ""})
    return out


def _guess_type(topic):
    for t in get_topics():
        if t["name"] == topic and t["type"]:
            return t["type"]
    return "std_msgs/String"


def subscribe(topic, mtype):
    with LOCK:
        st = _active.get(topic)
        if st and st["proc"] and st["proc"].poll() is None:
            return {"ok": True, "running": True}
        _unsub_locked(topic)
        st = {"proc": None, "raws": [], "sums": [], "heads": [], "error": None}
        _active[topic] = st

    env = dict(os.environ)
    env["SUB_TOPIC"] = topic
    env["SUB_TYPE"] = mtype or _guess_type(topic)
    env["RCUTILS_LOGGING_USE_STDOUT"] = "0"
    py, cwd = ros2env.python_command()
    cmd = f'{py} "{SUB_PY}"'
    p = subprocess.Popen(cmd, shell=True, cwd=cwd, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace",
                         **ros2env.source_popen_kwargs())
    st["proc"] = p
    threading.Thread(target=_reader, args=(topic, p, st), daemon=True).start()
    return {"ok": True, "running": True}


def _reader(topic, p, st):
    for raw in p.stdout:
        raw = raw.rstrip("\n")
        if not raw:
            continue
        if raw.startswith("RAW\t"):
            try:
                st["raws"].append({"t": time.strftime("%H:%M:%S"), "data": raw[4:]})
                if len(st["raws"]) > 50:
                    del st["raws"][0]
            except Exception:
                pass
        elif raw.startswith("SUM\t"):
            try:
                obj = json.loads(raw[4:])
                st["sums"].append(obj)
                if len(st["sums"]) > 500:
                    del st["sums"][: len(st["sums"]) - 500]
                if obj.get("paths"):
                    st["heads"] = obj["paths"]
            except Exception:
                pass
        elif raw.startswith("ERR\t"):
            try:
                e = json.loads(raw[4:])
                st["error"] = e.get("error", raw[4:])
            except Exception:
                st["error"] = raw[4:]


def unsubscribe(topic):
    with LOCK:
        _unsub_locked(topic)


def _unsub_locked(topic):
    st = _active.pop(topic, None)
    if st and st["proc"]:
        ros2env.kill_proc_tree(st["proc"].pid)
        try:
            st["proc"].wait(timeout=3)
        except Exception:
            try:
                st["proc"].kill()
            except Exception:
                pass


def get_data(topic):
    with LOCK:
        st = _active.get(topic)
        if not st:
            return {"error": "未订阅", "running": False}
        return {"running": (st["proc"] and st["proc"].poll() is None),
                "error": st["error"], "raw": list(st["raws"]),
                "sum": list(st["sums"]), "channels": list(st["heads"])}


def shutdown_all():
    stop_pub()
    for t in list(_active):
        unsubscribe(t)


# ── 前端 ──────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>类型模板 · 波形</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#0e1220;color:#dbe3f0;font-family:system-ui}
.wrap{max-width:1400px;margin:0 auto;padding:20px}
h2{color:#fdba74;margin:0 0 4px;font-size:20px}
.sub{color:#64748b;font-size:13px;margin-bottom:16px}
.card{background:#171c30;border:1px solid #26304d;border-radius:12px;padding:18px;margin-bottom:16px}
.two-col{display:grid;grid-template-columns:380px 1fr;gap:16px;align-items:start}
.two-col .col>.card{margin-bottom:16px}
@media(max-width:920px){.two-col{grid-template-columns:1fr}}
.card h3{margin:0 0 12px;font-size:15px;color:#e2e8f0}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;align-items:center}
label{font-size:12px;color:#94a3b8;white-space:nowrap}
select,input,textarea{background:#0e1220;color:#dbe3f0;border:1px solid #2c3757;border-radius:8px;font-size:13px;padding:9px 10px}
select{flex:1;min-width:120px}
input{flex:1;min-width:90px}
textarea{width:100%;min-height:110px;font-family:ui-monospace,Consolas,monospace;resize:vertical}
button{padding:9px 16px;border:none;border-radius:8px;cursor:pointer;font-weight:600;font-size:13px;background:#fb923c;color:#1f0f00}
button:hover{filter:brightness(1.1)}
button.sec{background:#223053;color:#dbe3f0}
button.danger{background:#dc2626;color:#fff}
button.green{background:#22c55e;color:#04240f}
.status{font-size:12px;color:#94a3b8}
.green{color:#34d399}.red{color:#f87171}.yellow{color:#fbbf24}
.hint{font-size:11px;color:#64748b;margin-top:6px}
.code{background:#0e1220;border:1px solid #26304d;border-radius:8px;padding:8px 10px;font-family:ui-monospace,Consolas,monospace;font-size:12px;color:#7dd3fc;margin-top:8px}
#plot{width:100%;height:380px;background:#0e1220;border:1px solid #26304d;border-radius:8px}
.chans{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}
.chip{background:#223053;border:1px solid #2c3757;border-radius:20px;padding:4px 12px;font-size:12px;cursor:pointer;color:#a5b4fc;user-select:none}
.chip.on{background:#22c55e;color:#04240f;border-color:#22c55e}
.msgrows{max-height:220px;overflow-y:auto}
.msg{background:#0e1220;border-left:3px solid #22c55e;padding:8px 10px;margin:6px 0;border-radius:6px;font-family:ui-monospace,monospace;font-size:12px;color:#7dd3fc;white-space:pre-wrap;word-break:break-all}
.mt{color:#64748b;font-size:11px;margin-bottom:2px}
.empty{color:#475569;text-align:center;padding:16px;font-size:13px}
</style>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
</head>
<body>
<div class="wrap">
  <h2>🧬 消息工作室</h2>
  <div class="sub">左侧发布任意类型消息 → 右侧订阅并实时查看波形/原始消息</div>

  <div class="two-col">
  <div class="col">
  <div class="card">
    <h3>📋 类型模板库</h3>
    <div class="row">
      <select id="tmpl" onchange="applyTmpl()"></select>
      <span class="status" id="tmpl-desc"></span>
    </div>
  </div>

  <div class="card">
    <h3>🚀 发布配置</h3>
    <div class="row">
      <label>话题</label><input id="pub-topic" value="/type_demo">
    </div>
    <div class="row">
      <label>类型</label><input id="pub-type" value="std_msgs/String">
      <label>频率</label><input id="pub-rate" type="number" value="1" min="0.1" step="0.1" style="max-width:90px"><label>Hz</label>
    </div>
    <div class="row"><label>消息 JSON</label></div>
    <textarea id="payload">{"data":"Hello ROS2 $i"}</textarea>
    <div class="hint">支持嵌套 JSON；字符串里的 <code>$i</code> 随每次发布递增（给波形用）。</div>
    <div class="row" style="margin-top:12px">
      <button onclick="pubOnce()">发布一次</button>
      <button onclick="pubLoop()">循环发布</button>
      <button class="danger" onclick="pubStop()">停止</button>
      <span class="status" id="pub-status"></span>
    </div>
  </div>
  </div><!-- /col 左 -->

  <div class="col">
  <div class="card" id="plotcard">
    <h3>📈 实时波形 / 消息查看</h3>
    <div class="row">
      <select id="topic"><option value="">选择话题...</option></select>
      <input id="sub-type" placeholder="类型(自动填写)" style="flex:0 0 190px">
      <button class="green" id="sub-btn" onclick="toggleSub()">订阅</button>
      <button class="sec" onclick="refreshTopics()">刷新</button>
    </div>
    <div class="status" id="sub-status"></div>
    <div id="plot"></div>
    <div class="chans" id="chans"><span class="empty">暂无数值通道（该话题可能是纯文本/图片）</span></div>
    <div class="row">
      <label>窗口</label>
      <select id="window" onchange="replot()">
        <option value="10">10 秒</option><option value="20" selected>20 秒</option>
        <option value="60">60 秒</option>
      </select>
      <button class="sec" onclick="clearRows()">清空数据</button>
    </div>
    <div class="msgrows" id="rawrows"><div class="empty">等待消息...</div></div>
  </div><!-- /plotcard -->
  </div><!-- /col 右 -->
  </div><!-- /two-col -->
</div>
<script>
function esc(s){return (s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function v(id){return document.getElementById(id).value;}
function setV(id,val){document.getElementById(id).value=val;document.getElementById(id).setAttribute('data-touched','1');}

// ── 类型模板 ──
var TM=[];
function applyTmpl(){
  var sel=document.getElementById('tmpl');
  var t=TM.find(x=>x.id===sel.value); if(!t)return;
  if(t.type!==undefined&&t.type!==null)setV('pub-type',t.type||'');
  document.getElementById('payload').value=JSON.stringify(t.payload,null,2);
  document.getElementById('tmpl-desc').textContent=t.name||'';
  if(t.id==='Custom')document.getElementById('pub-type').focus();
}
function loadTmpl(){
  fetch('/api/templates?_t='+Date.now()).then(r=>r.json()).then(list=>{
    TM=list||[];
    var html='';TM.forEach(t=>{html+='<option value="'+esc(t.id)+'">'+esc(t.name)+'</option>';});
    document.getElementById('tmpl').innerHTML=html;
  }).catch(()=>{});
}
function pubParams(count){
  return 'topic='+encodeURIComponent(v('pub-topic'))+
    '&type='+encodeURIComponent(v('pub-type'))+
    '&rate='+encodeURIComponent(v('pub-rate'))+
    '&payload='+encodeURIComponent(v('payload'))+
    '&count='+encodeURIComponent(count);
}
function pubOnce(){fetch('/api/pub?'+pubParams(1)).then(refreshPub).catch(refreshPub);}
function pubLoop(){fetch('/api/pub?'+pubParams(0)).then(refreshPub).catch(refreshPub);}
function pubStop(){fetch('/api/pub/stop').then(refreshPub).catch(refreshPub);}
function refreshPub(){
  fetch('/api/pub/status?_t='+Date.now()).then(r=>r.json()).then(s=>{
    var el=document.getElementById('pub-status');
    if(s.running){el.textContent='发布中 …';el.className='status green';}
    else{el.textContent='空闲';el.className='status';}
  }).catch(()=>{});
}

// ── 波形 / 消息查看 ──
var subscribed=false, selChans={}, allSums=[], intervals=[];
var chart=null;
function refreshTopics(){
  fetch('/api/topics?_t='+Date.now()).then(r=>r.json()).then(list=>{
    var sel=document.getElementById('topic'), prev=sel.value;
    var html='<option value="">选择话题...</option>';
    list.forEach(t=>{html+='<option value="'+t.name+'" data-type="'+(t.type||'')+'">'+t.name+(t.type?' ['+t.type+']':'')+'</option>';});
    sel.innerHTML=html;
    if(prev){for(var i=0;i<sel.options.length;i++){if(sel.options[i].value===prev){sel.value=prev;break;}}}
  }).catch(()=>{});
}
document.getElementById('topic').onchange=function(){
  var o=this.options[this.selectedIndex];
  if(o&&o.dataset.type){
    // ROS2 规范类型如 std_msgs/msg/Int32 -> 精简为 std_msgs/Int32，与发布端写法一致
    var parts=o.dataset.type.split('/');
    document.getElementById('sub-type').value=(parts.length===3)?parts[0]+'/'+parts[2]:o.dataset.type;
  }
};
function toggleSub(){
  if(!subscribed){
    var t=v('topic'), mt=v('sub-type').trim();
    if(!t){alert('请先选择话题');return;}
    subscribed=true;
    document.getElementById('sub-btn').textContent='停止';document.getElementById('sub-btn').classList.add('danger');
    document.getElementById('sub-btn').classList.remove('green');
    fetch('/api/sub?topic='+encodeURIComponent(t)+'&type='+encodeURIComponent(mt)).catch(()=>{});
    intervals=[setInterval(loadData,300), setInterval(replot,300)];
    loadData();
  }else{
    subscribed=false;
    document.getElementById('sub-btn').textContent='订阅';document.getElementById('sub-btn').classList.remove('danger');
    document.getElementById('sub-btn').classList.add('green');
    fetch('/api/unsub?topic='+encodeURIComponent(v('topic')));
    intervals.forEach(id=>clearInterval(id)); intervals=[];
    selChans={}; allSums=[];
  }
}
function loadData(){
  if(!subscribed)return;
  fetch('/api/data?topic='+encodeURIComponent(v('topic'))).then(r=>r.json()).then(d=>{
    if(d.error){document.getElementById('sub-status').innerHTML='<span class="yellow">'+esc(d.error)+'</span>';return;}
    document.getElementById('sub-status').innerHTML=d.running?'<span class="green">订阅中</span>':'<span class="yellow">已断开</span>'+(d.error?' <span class="red">'+esc(d.error)+'</span>':'');
    if(d.running)allSums=d.sum;
    if(d.channels&&d.channels.length){
      // 首次收到通道且尚未勾选任何通道时，自动勾选首个标量通道，让曲线立即可见
      if(!Object.keys(selChans).length){
        var first=d.channels.find(c=>c.type==='scalar')||d.channels[0];
        if(first)selChans[first.path]=true;
      }
      var ch=document.getElementById('chans');
      ch.innerHTML=d.channels.map(cp=>{
        var on=!!selChans[cp.path];
        return '<span class="chip '+(on?'on':'')+'" onclick="toggleChan(\''+esc(cp.path.replace(/'/g,"\\'"))+'\')">'+esc(cp.path)+' ('+(cp.type==='scalar'?'标量':'数组x'+cp.len)+')</span>';
      }).join('')||'<span class="empty">无可视化数值字段</span>';
    }
    var rr=document.getElementById('rawrows');
    if(d.raw&&d.raw.length){
      var html='';d.raw.slice(-12).forEach(m=>{html+='<div class="msg"><div class="mt">'+m.t+'</div>'+esc(m.data)+'</div>';});
      rr.innerHTML=html;
    }else{rr.innerHTML='<div class="empty">等待消息...</div>';}
  }).catch(()=>{});
}
function toggleChan(key){
  if(selChans[key])delete selChans[key];else selChans[key]=true;
  replot();
}
function clearRows(){
  allSums=[];
  fetch('/api/clear?topic='+encodeURIComponent(v('topic'))).catch(()=>{});
  document.getElementById('rawrows').innerHTML='<div class="empty">已清空</div>';
  replot();
}
function windowSel(){return parseFloat(v('window')||20);}
function replot(){
  if(!subscribed)return;
  var keys=Object.keys(selChans); if(!keys.length){drawEmpty();return;}
  drawChart(keys);
}
function drawEmpty(){
  if(!subscribed)return;
  if(!chart)chart=echarts.init(document.getElementById('plot'));
  var option=baseOption();
  option.title={show:true,text:'点击上方通道勾选后显示曲线',left:'center',top:'middle',textStyle:{color:'#64748b',fontSize:13,fontWeight:'normal'}};
  chart.setOption(option);
}
function findVal(s,key){
  if(!s.paths)return null;
  for(var i=0;i<s.paths.length;i++){if(s.paths[i].path===key){if(s.paths[i].type==='scalar')return s.paths[i].value;if(s.paths[i].head&&s.paths[i].head.length)return s.paths[i].head[0];return null;}}
  return null;
}
function baseOption(){
  return {
    backgroundColor:'transparent',
    color:['#22c55e','#38bdf8','#f59e0b','#f472b6','#a78bfa','#34d399','#fb7185','#facc15'],
    grid:{left:55,right:18,top:42,bottom:52},
    tooltip:{trigger:'axis',axisPointer:{type:'cross'}},
    legend:{type:'scroll',top:4,textStyle:{color:'#cbd5e1'},pageTextStyle:{color:'#94a3b8'}},
    toolbox:{right:10,itemSize:14,feature:{
      dataZoom:{title:{zoom:'框选放大',back:'还原'},iconStyle:{borderColor:'#64748b'}},
      restore:{title:'重置视图'},
      saveAsImage:{title:'保存图片',pixelRatio:2}
    }},
    dataZoom:[
      {type:'inside',xAxisIndex:0,filterMode:'none'},
      {type:'inside',yAxisIndex:0,filterMode:'none'},
      {type:'slider',xAxisIndex:0,filterMode:'none',bottom:8,height:12},
      {type:'slider',yAxisIndex:0,filterMode:'none',right:2,width:12}
    ],
    xAxis:{type:'time',axisLabel:{color:'#94a3b8',fontSize:11},axisLine:{lineStyle:{color:'#2c3757'}},splitLine:{show:false}},
    yAxis:{type:'value',scale:true,axisLabel:{color:'#94a3b8',fontSize:11},axisLine:{lineStyle:{color:'#2c3757'}},splitLine:{lineStyle:{color:'#1f2b45',type:'dashed'}}},
    series:[]
  };
}
function drawChart(keys){
  if(!chart)chart=echarts.init(document.getElementById('plot'));
  var option=baseOption();
  if(!allSums.length){
    option.title={show:true,text:'等待数据中…',left:'center',top:'middle',textStyle:{color:'#64748b',fontSize:13,fontWeight:'normal'}};
    chart.setOption(option);return;
  }
  var win=windowSel(), now=allSums[allSums.length-1].t, t0=now-win;
  var series=keys.map(k=>({name:k,type:'line',showSymbol:false,sampling:'lttb',large:true,data:[]}));
  allSums.forEach(s=>{
    if(s.t<t0)return;
    for(var i=0;i<keys.length;i++){
      var val=findVal(s,keys[i]);
      if(val!==null&&typeof val==='number')series[i].data.push([Math.round(s.t*1000),val]);
    }
  });
  option.series=series;
  chart.setOption(option);
}
window.addEventListener('resize',()=>{if(chart)chart.resize();});

setInterval(refreshPub,2500);
setInterval(refreshTopics,5000);
loadTmpl();
refreshTopics();
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
        if path == "/api/templates":
            self._json(TEMPLATES)
        elif path == "/api/pub":
            topic = q.get("topic", ["/type_demo"])[0] or "/type_demo"
            mtype = q.get("type", ["std_msgs/String"])[0] or "std_msgs/String"
            try: rate = float(q.get("rate", ["1"])[0])
            except ValueError: rate = 1.0
            payload = q.get("payload", ["{}"])[0] or "{}"
            try: count = int(q.get("count", ["0"])[0])
            except ValueError: count = 0
            _spawn_pub(topic, mtype, rate, payload, count)
            self._json({"ok": True, "type": mtype})
        elif path == "/api/pub/stop":
            stop_pub()
            self._json({"ok": True})
        elif path == "/api/pub/status":
            self._json(pub_status())
        elif path == "/api/topics":
            self._json(get_topics())
        elif path == "/api/sub":
            topic = q.get("topic", [""])[0]
            mtype = q.get("type", [""])[0]
            self._json(subscribe(topic, mtype))
        elif path == "/api/unsub":
            topic = q.get("topic", [""])[0]
            unsubscribe(topic)
            self._json({})
        elif path == "/api/data":
            topic = q.get("topic", [""])[0]
            self._json(get_data(topic))
        elif path == "/api/clear":
            topic = q.get("topic", [""])[0]
            with LOCK:
                st = _active.get(topic)
                if st:
                    st["raws"] = []
                    st["sums"] = []
            self._json({"ok": True})
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
    print(f"[Type Studio] 启动成功，监听端口: {PORT}")
    server = ThreadingHTTPServer((os.environ.get("APP_HOST", "127.0.0.1"), PORT), H)
    try:
        server.serve_forever()
    finally:
        shutdown_all()
        server.server_close()