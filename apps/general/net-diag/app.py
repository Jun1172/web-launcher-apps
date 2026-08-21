"""net-diag —— 网络诊断工具箱
- 端口 8153（可由环境变量 LAUNCHER_APP_PORT 覆盖）
- 功能：Ping 测试(SSE 流式) + TCP 端口扫描 + DNS 解析 + 本机信息
- 跨平台：优先调用系统 ping 命令（兼容 Windows 中文/英文 与 Linux 输出），
  系统 ping 不可用时回退到 TCP 连接 80/443 端口测延迟
- 前端深色科技风，内嵌 HTML，Canvas 手绘延迟折线图，无需 CDN
"""
import json
import os
import platform
import re
import socket
import subprocess
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("LAUNCHER_APP_PORT", 8153))
IS_WIN = platform.system() == "Windows"

# ── 正则：提取系统 ping 输出中的延迟 ─────────────────────────
# Linux : "64 bytes from 8.8.8.8: icmp_seq=1 ttl=117 time=10.1 ms"
# Win中文: "来自 8.8.8.8 的回复: 字节=32 时间=10ms TTL=117"
# Win英文: "Reply from 8.8.8.8: bytes=32 time=10ms TTL=117"
# 兼容 time= / 时间= 以及 time<1ms / 时间<1ms
TIME_RE = re.compile(r"(?:time|时间)[=<]\s*(\d+\.?\d*)\s*ms", re.IGNORECASE)
SUB_MS_RE = re.compile(r"(?:time|时间)\s*<\s*1\s*ms", re.IGNORECASE)
# 超时/不可达关键字
TIMEOUT_KEYS = ("请求超时", "Request timed out", "timed out",
                "Destination Host Unreachable", "目标主机无法访问",
                "Destination Net Unreachable", "TTL expired in transit")


# ── Ping：优先系统 ping，回退 TCP ───────────────────────────
def system_ping_once(host, timeout=2):
    """调用系统 ping 命令做一次 ping，返回 (延迟ms 或 None, 错误信息 或 None)"""
    try:
        if IS_WIN:
            cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), host]
        else:
            cmd = ["ping", "-c", "1", "-W", str(int(timeout)), host]
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout + 3, encoding="utf-8", errors="replace",
        )
        out = (r.stdout or "") + (r.stderr or "")
        # 超时/不可达检测
        if any(k in out for k in TIMEOUT_KEYS):
            return None, "timeout"
        # 小于 1ms
        if SUB_MS_RE.search(out):
            return 0.5, None
        m = TIME_RE.search(out)
        if m:
            return round(float(m.group(1)), 2), None
        # 没解析到时间且返回码非 0
        if r.returncode != 0:
            return None, "unreachable"
        return None, "parse_error"
    except FileNotFoundError:
        return None, "no_ping_cmd"
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except Exception as e:
        return None, str(e)


def tcp_ping_once(host, timeout=2):
    """TCP 伪 ping：连接 80 / 443 端口测 RTT，返回 (延迟ms 或 None, 错误 或 None)"""
    for port in (80, 443):
        try:
            t0 = time.time()
            with socket.create_connection((host, port), timeout=timeout):
                return round((time.time() - t0) * 1000, 2), None
        except Exception:
            continue
    return None, "tcp_fail"


def ping_once(host, timeout=2):
    """一次 ping：优先系统 ping，失败回退 TCP"""
    latency, err = system_ping_once(host, timeout)
    if latency is not None:
        return {"latency": latency, "timeout": False, "method": "icmp"}
    # 系统 ping 失败，回退 TCP
    latency, err2 = tcp_ping_once(host, timeout)
    if latency is not None:
        return {"latency": latency, "timeout": False,
                "method": "tcp", "fallback": err}
    return {"latency": None, "timeout": True, "method": "tcp",
            "error": err2 or err}


# ── TCPing：端口连通性 ─────────────────────────────────────
def tcping_once(host, port, timeout=2):
    """TCP 端口连通性测试"""
    try:
        t0 = time.time()
        with socket.create_connection((host, port), timeout=timeout):
            return {"port": port, "open": True,
                    "latency": round((time.time() - t0) * 1000, 2)}
    except (socket.timeout, TimeoutError):
        return {"port": port, "open": False, "latency": None,
                "error": "timeout"}
    except Exception as e:
        return {"port": port, "open": False, "latency": None,
                "error": str(e)}


# ── DNS：解析 A 记录 ───────────────────────────────────────
def dns_resolve(domain):
    """DNS 解析，返回 A 记录列表"""
    try:
        infos = socket.getaddrinfo(
            domain, None, socket.AF_INET, socket.SOCK_STREAM)
        addrs = sorted(set(i[4][0] for i in infos))
        return {"domain": domain, "addresses": addrs,
                "count": len(addrs)}
    except socket.gaierror as e:
        return {"domain": domain, "addresses": [], "count": 0,
                "error": str(e)}


# ── 本机网络信息 ───────────────────────────────────────────
def get_local_info():
    """获取本机主机名、出口 IP、所有网卡 IPv4"""
    hostname = socket.gethostname()
    # 出口 IP：连一个公网 UDP（不发包）拿本地地址
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "127.0.0.1"
    # 所有网卡 IPv4
    all_ips = []
    try:
        for item in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = item[4][0]
            if ip not in all_ips:
                all_ips.append(ip)
    except Exception:
        pass
    return {
        "hostname": hostname,
        "local_ip": local_ip,
        "all_ips": all_ips,
        "platform": f"{platform.system()} {platform.release()}",
    }


# ── 内嵌前端 HTML ─────────────────────────────────────────
HTML = r"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>🌐 网络诊断工具箱</title>
<style>
:root{
  --bg:#0b1120; --glass:rgba(255,255,255,.05); --glass-h:rgba(255,255,255,.09);
  --border:rgba(255,255,255,.08); --border-h:rgba(255,255,255,.18);
  --t1:#f8fafc; --t2:#94a3b8; --t3:#64748b;
  --accent:#06b6d4; --accent-glow:rgba(6,182,212,.3);
  --ok:#34d399; --warn:#fbbf24; --err:#f87171;
}
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  -webkit-font-smoothing:antialiased;color:var(--t1);
  background-color:var(--bg);
  background-image:
    radial-gradient(at 0% 0%,rgba(6,182,212,.18) 0px,transparent 50%),
    radial-gradient(at 100% 0%,rgba(59,130,246,.15) 0px,transparent 50%),
    radial-gradient(at 100% 100%,rgba(168,85,247,.12) 0px,transparent 50%);
  background-attachment:fixed;min-height:100vh;padding:20px}
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(255,255,255,.1);border-radius:3px}

header{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;gap:12px;flex-wrap:wrap}
header h1{font-size:20px;font-weight:600;display:flex;align-items:center;gap:10px;letter-spacing:-.5px}
header h1 .sub{font-size:11px;color:var(--t3);font-weight:400}

/* 本机信息卡 */
.local-card{
  background:var(--glass);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
  border:1px solid var(--border);border-radius:14px;padding:12px 16px;
  display:flex;align-items:center;gap:14px;min-width:0;
}
.local-card .ip{font-size:18px;font-weight:700;font-variant-numeric:tabular-nums;color:var(--accent)}
.local-card .meta{font-size:11px;color:var(--t2);line-height:1.5}
.local-card .meta b{color:var(--t1);font-weight:600}

/* 标签页 */
.tabs{display:flex;gap:6px;background:var(--glass);border:1px solid var(--border);
  border-radius:14px;padding:6px;margin-bottom:18px}
.tab{flex:1;text-align:center;padding:10px;border-radius:10px;font-size:13px;font-weight:500;
  color:var(--t2);cursor:pointer;transition:all .2s;white-space:nowrap}
.tab:hover{color:var(--t1)}
.tab.active{background:var(--accent);color:#00131a;box-shadow:0 4px 12px var(--accent-glow)}

/* 通用面板 */
.panel{display:none}
.panel.active{display:block;animation:fade .25s ease}
@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}

.section{background:var(--glass);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
  border:1px solid var(--border);border-radius:18px;padding:20px;margin-bottom:16px}
.section-title{font-size:13px;font-weight:600;color:var(--t2);margin-bottom:14px;
  display:flex;align-items:center;gap:8px;text-transform:uppercase;letter-spacing:.5px}

/* 输入行 */
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.input{flex:1;min-width:160px;background:rgba(0,0,0,.25);border:1px solid var(--border);
  border-radius:10px;padding:11px 14px;color:var(--t1);font-size:14px;font-family:inherit;
  transition:all .2s;outline:none}
.input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-glow)}
.input::placeholder{color:var(--t3)}
.input.sm{flex:0 0 110px;min-width:0}
.btn{padding:11px 20px;border:0;border-radius:10px;cursor:pointer;font-size:14px;font-weight:600;
  transition:all .2s;display:inline-flex;align-items:center;justify-content:center;gap:6px;white-space:nowrap}
.btn:disabled{opacity:.5;cursor:not-allowed;transform:none!important}
.btn-primary{background:var(--accent);color:#00131a;box-shadow:0 4px 12px var(--accent-glow)}
.btn-primary:hover:not(:disabled){background:#0891b2;transform:translateY(-1px)}
.btn-muted{background:rgba(255,255,255,.08);color:var(--t1);border:1px solid var(--border)}
.btn-muted:hover:not(:disabled){background:var(--glass-h)}

/* 统计卡 */
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:14px}
.stat{background:rgba(0,0,0,.2);border:1px solid var(--border);border-radius:12px;padding:12px;text-align:center}
.stat .v{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums}
.stat .l{font-size:11px;color:var(--t2);margin-top:3px}

/* Canvas */
.canvas-wrap{background:rgba(0,0,0,.3);border:1px solid var(--border);border-radius:14px;
  padding:8px;margin-top:14px;position:relative}
canvas{display:block;width:100%;height:220px}

/* 结果列表 */
.log{max-height:240px;overflow-y:auto;margin-top:14px}
.log-item{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;
  border-bottom:1px solid rgba(255,255,255,.04);font-size:13px;font-variant-numeric:tabular-nums}
.log-item:last-child{border:0}
.log-item .seq{color:var(--t3);width:40px;flex-shrink:0}
.log-item .lat{font-weight:600}
.log-item .lat.ok{color:var(--ok)}
.log-item .lat.timeout{color:var(--err)}
.log-item .mtd{font-size:10px;color:var(--t3);background:rgba(255,255,255,.06);
  padding:1px 6px;border-radius:4px;margin-left:auto;margin-right:8px}

/* 端口结果 */
.port-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;margin-top:14px}
.port{background:rgba(0,0,0,.2);border:1px solid var(--border);border-radius:12px;padding:14px;text-align:center}
.port.open{border-color:rgba(52,211,153,.35);background:rgba(52,211,153,.07)}
.port.closed{border-color:rgba(248,113,113,.3);background:rgba(248,113,113,.06)}
.port .p{font-size:18px;font-weight:700;font-variant-numeric:tabular-nums}
.port .s{font-size:12px;font-weight:600;margin-top:4px}
.port.open .s{color:var(--ok)}
.port.closed .s{color:var(--err)}
.port .ms{font-size:11px;color:var(--t2);margin-top:3px;font-variant-numeric:tabular-nums}

/* DNS 列表 */
.dns-list{margin-top:14px}
.dns-item{display:flex;align-items:center;gap:10px;padding:10px 12px;
  border-bottom:1px solid rgba(255,255,255,.04);font-size:13px}
.dns-item:last-child{border:0}
.dns-item .idx{color:var(--t3);width:24px;flex-shrink:0}
.dns-item .addr{font-family:monospace;color:var(--accent);font-weight:600}
.dns-item .copy{margin-left:auto;font-size:11px;color:var(--t2);cursor:pointer;
  padding:3px 8px;border-radius:6px;background:rgba(255,255,255,.06);border:1px solid var(--border)}
.dns-item .copy:hover{color:var(--t1);background:var(--glass-h)}

.empty{text-align:center;color:var(--t3);font-size:13px;padding:24px}

/* Toast */
.__toast{position:fixed;left:50%;top:24px;transform:translateX(-50%);z-index:9999;
  padding:10px 20px;background:rgba(20,25,45,.92);backdrop-filter:blur(12px);
  border:1px solid var(--border);color:var(--t1);border-radius:12px;font-size:13px;
  font-weight:500;box-shadow:0 12px 24px rgba(0,0,0,.4);animation:fp .3s cubic-bezier(.34,1.56,.64,1)}
@keyframes fp{from{transform:translateX(-50%) translateY(-20px);opacity:0}}
.spin{display:inline-block;width:14px;height:14px;border:2px solid rgba(0,0,0,.25);
  border-top-color:#00131a;border-radius:50%;animation:sp .6s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
</style></head><body>

<header>
  <h1>🌐 网络诊断工具箱 <span class="sub">v1.0.0 · :<span id="portLbl">8153</span></span></h1>
  <div class="local-card">
    <div style="font-size:22px">💻</div>
    <div>
      <div class="ip" id="localIp">—</div>
      <div class="meta" id="localMeta">加载中…</div>
    </div>
  </div>
</header>

<div class="tabs" id="tabs">
  <div class="tab active" data-t="ping">📡 Ping 测试</div>
  <div class="tab" data-t="port">🔌 端口扫描</div>
  <div class="tab" data-t="dns">🔎 DNS 解析</div>
</div>

<!-- Ping 面板 -->
<div class="panel active" id="p-ping">
  <div class="section">
    <div class="section-title">📡 Ping 测试 · SSE 流式</div>
    <div class="row">
      <input class="input" id="pingHost" placeholder="目标 IP 或域名（如 8.8.8.8）" value="8.8.8.8">
      <input class="input sm" id="pingCount" type="number" value="10" min="1" max="50" title="次数">
      <button class="btn btn-primary" id="pingBtn" onclick="startPing()">开始</button>
      <button class="btn btn-muted" id="pingStop" onclick="stopPing()" style="display:none">停止</button>
    </div>
    <div class="canvas-wrap"><canvas id="pingChart"></canvas></div>
    <div class="stats" id="pingStats"></div>
  </div>
  <div class="section">
    <div class="section-title">📋 实时结果</div>
    <div class="log" id="pingLog"><div class="empty">输入目标后点击「开始」</div></div>
  </div>
</div>

<!-- 端口扫描面板 -->
<div class="panel" id="p-port">
  <div class="section">
    <div class="section-title">🔌 TCP 端口扫描</div>
    <div class="row">
      <input class="input" id="portHost" placeholder="目标 IP 或域名" value="127.0.0.1">
      <input class="input" id="portList" placeholder="端口，逗号分隔（80,443,8080）" value="80,443,8080,22,3306" style="flex:2">
      <button class="btn btn-primary" id="portBtn" onclick="startPort()">扫描</button>
    </div>
    <div class="port-grid" id="portGrid"><div class="empty">点击「扫描」开始检测</div></div>
  </div>
</div>

<!-- DNS 面板 -->
<div class="panel" id="p-dns">
  <div class="section">
    <div class="section-title">🔎 DNS 解析</div>
    <div class="row">
      <input class="input" id="dnsDomain" placeholder="域名（如 www.baidu.com）" value="www.baidu.com">
      <button class="btn btn-primary" id="dnsBtn" onclick="startDns()">解析</button>
    </div>
    <div class="dns-list" id="dnsList"><div class="empty">输入域名后点击「解析」</div></div>
  </div>
</div>

<script>
// ── 工具函数 ──────────────────────────────────────────
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function toast(msg){
  const d=document.createElement('div');d.className='__toast';d.textContent=msg;
  document.body.appendChild(d);
  setTimeout(()=>{d.style.transition='opacity .2s';d.style.opacity='0';setTimeout(()=>d.remove(),200);},2500);
}
async function copy(t){try{await navigator.clipboard.writeText(t);toast('已复制：'+t);}catch(e){toast('复制失败');}}

// ── 标签页切换 ────────────────────────────────────────
document.getElementById('tabs').addEventListener('click',e=>{
  const t=e.target.closest('.tab');if(!t)return;
  document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===t));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.getElementById('p-'+t.dataset.t).classList.add('active');
  if(t.dataset.t==='ping')requestAnimationFrame(drawPing);
});

// ── 本机信息 ─────────────────────────────────────────
async function loadLocal(){
  try{
    const r=await fetch('/api/whoami');const d=await r.json();
    document.getElementById('localIp').textContent=d.local_ip||'—';
    document.getElementById('localMeta').innerHTML=
      '主机名 <b>'+esc(d.hostname)+'</b> · '+esc(d.platform||'')+
      (d.all_ips&&d.all_ips.length>1?' · 共 '+d.all_ips.length+' 个 IP':'');
    document.getElementById('portLbl').textContent=d.port||'8153';
  }catch(e){document.getElementById('localMeta').textContent='加载失败';}
}
loadLocal();

// ════════════ Ping ════════════
let pingData=[],pingES=null,pinging=false;
const cv=document.getElementById('pingChart');
const cx=cv.getContext('2d');
function resizeCanvas(){
  const r=cv.getBoundingClientRect();
  const dpr=window.devicePixelRatio||1;
  cv.width=Math.max(300,r.width*dpr);
  cv.height=220*dpr;
  cx.setTransform(dpr,0,0,dpr,0,0);
}
function drawPing(){
  resizeCanvas();
  const W=cv.getBoundingClientRect().width,H=220;
  const pad={l:48,r:16,t:14,b:24};
  const pW=W-pad.l-pad.r,pH=H-pad.t-pad.b;
  cx.clearRect(0,0,W,H);
  cx.fillStyle='rgba(255,255,255,.35)';
  cx.font='11px ui-monospace,monospace';
  // 空状态
  if(pingData.length===0){
    cx.fillStyle='rgba(255,255,255,.25)';
    cx.font='13px system-ui';
    cx.textAlign='center';
    cx.fillText('点击「开始」查看延迟趋势',W/2,H/2);
    cx.textAlign='left';
    return;
  }
  const valid=pingData.filter(d=>d.latency!=null).map(d=>d.latency);
  const maxLat=valid.length?Math.max(...valid):0;
  const yMax=Math.max(maxLat*1.2,10);
  const xMax=Math.max(pingData.length,1);
  // 网格 + Y 轴标签
  cx.strokeStyle='rgba(255,255,255,.07)';
  cx.lineWidth=1;
  cx.textAlign='right';cx.textBaseline='middle';
  for(let i=0;i<=4;i++){
    const y=pad.t+pH-pH*i/4;
    cx.beginPath();cx.moveTo(pad.l,y);cx.lineTo(W-pad.r,y);cx.stroke();
    cx.fillStyle='rgba(255,255,255,.3)';
    cx.fillText((yMax*i/4).toFixed(0),pad.l-6,y);
  }
  // X 轴标签
  cx.textAlign='center';cx.textBaseline='top';
  const xStep=Math.max(1,Math.ceil(xMax/8));
  for(let i=0;i<xMax;i+=xStep){
    const x=pad.l+(xMax>1?pW*i/(xMax-1):pW/2);
    cx.fillStyle='rgba(255,255,255,.3)';
    cx.fillText(String(i+1),x,H-pad.b+6);
  }
  // 折线
  cx.strokeStyle='#06b6d4';cx.lineWidth=2;cx.beginPath();
  let started=false;
  pingData.forEach((d,i)=>{
    const x=pad.l+(xMax>1?pW*i/(xMax-1):pW/2);
    if(d.latency!=null){
      const y=pad.t+pH-pH*(d.latency/yMax);
      if(!started){cx.moveTo(x,y);started=true;}else cx.lineTo(x,y);
    }else{started=false;}
  });
  cx.stroke();
  // 数据点 + 超时标记
  pingData.forEach((d,i)=>{
    const x=pad.l+(xMax>1?pW*i/(xMax-1):pW/2);
    if(d.latency!=null){
      const y=pad.t+pH-pH*(d.latency/yMax);
      cx.fillStyle='#06b6d4';
      cx.beginPath();cx.arc(x,y,3.5,0,Math.PI*2);cx.fill();
    }else{
      // 超时：红色 ×
      const y=pad.t+pH;
      cx.strokeStyle='#f87171';cx.lineWidth=2;
      cx.beginPath();cx.moveTo(x-4,y-4);cx.lineTo(x+4,y+4);
      cx.moveTo(x+4,y-4);cx.lineTo(x-4,y+4);cx.stroke();
    }
  });
  cx.textAlign='left';cx.textBaseline='alphabetic';
}
function pingStats(){
  const valid=pingData.filter(d=>d.latency!=null).map(d=>d.latency);
  const total=pingData.length;
  if(valid.length===0){
    document.getElementById('pingStats').innerHTML=
      ['发送','接收','丢包','平均'].map(l=>`<div class="stat"><div class="v">${total}</div><div class="l">${l}</div></div>`).join('');
    return;
  }
  const avg=valid.reduce((a,b)=>a+b,0)/valid.length;
  const mn=Math.min(...valid),mx=Math.max(...valid);
  const loss=total-valid.length;
  const lossP=total?(loss/total*100).toFixed(0):0;
  const cards=[
    ['发送',total],['接收',valid.length],['丢包',lossP+'%'],
    ['平均',avg.toFixed(1)+'ms'],['最小',mn.toFixed(1)+'ms'],['最大',mx.toFixed(1)+'ms']
  ];
  document.getElementById('pingStats').innerHTML=cards.map(c=>
    `<div class="stat"><div class="v">${c[1]}</div><div class="l">${c[0]}</div></div>`).join('');
}
function pingLogHTML(d){
  const lat=d.latency!=null?d.latency.toFixed(1)+'ms':'超时';
  const cls=d.latency!=null?'ok':'timeout';
  const mt=d.method==='icmp'?'ICMP':'TCP';
  return `<div class="log-item"><span class="seq">#${d.seq}</span>`+
    `<span class="lat ${cls}">${lat}</span>`+
    `<span class="mtd">${mt}</span></div>`;
}
function startPing(){
  const host=document.getElementById('pingHost').value.trim();
  if(!host){toast('请输入目标');return;}
  const count=Math.max(1,Math.min(50,parseInt(document.getElementById('pingCount').value)||10));
  pingData=[];pinging=true;
  document.getElementById('pingLog').innerHTML='';
  drawPing();pingStats();
  const btn=document.getElementById('pingBtn');
  btn.disabled=true;btn.innerHTML='<span class="spin"></span> 测试中';
  document.getElementById('pingStop').style.display='inline-flex';
  pingES=new EventSource('/api/ping?host='+encodeURIComponent(host)+'&count='+count);
  pingES.onmessage=(e)=>{
    const d=JSON.parse(e.data);
    if(d.done){finishPing();return;}
    pingData.push(d);
    document.getElementById('pingLog').insertAdjacentHTML('beforeend',pingLogHTML(d));
    const log=document.getElementById('pingLog');log.scrollTop=log.scrollHeight;
    drawPing();pingStats();
  };
  pingES.onerror=()=>finishPing();
}
function stopPing(){if(pingES){pingES.close();pingES=null;}finishPing();}
function finishPing(){
  if(pingES){pingES.close();pingES=null;}
  pinging=false;
  const btn=document.getElementById('pingBtn');
  btn.disabled=false;btn.textContent='开始';
  document.getElementById('pingStop').style.display='none';
}
window.addEventListener('resize',()=>{if(document.getElementById('p-ping').classList.contains('active'))drawPing();});

// ════════════ 端口扫描 ════════════
async function startPort(){
  const host=document.getElementById('portHost').value.trim();
  const ports=document.getElementById('portList').value.trim();
  if(!host){toast('请输入目标');return;}
  if(!ports){toast('请输入端口');return;}
  const btn=document.getElementById('portBtn');
  btn.disabled=true;btn.innerHTML='<span class="spin"></span> 扫描中';
  document.getElementById('portGrid').innerHTML='<div class="empty">扫描中…</div>';
  try{
    const r=await fetch('/api/tcping?host='+encodeURIComponent(host)+'&ports='+encodeURIComponent(ports));
    const d=await r.json();
    if(d.error){document.getElementById('portGrid').innerHTML='<div class="empty">⚠ '+esc(d.error)+'</div>';return;}
    const html=d.results.map(p=>{
      const cls=p.open?'open':'closed';
      const st=p.open?'开放':'关闭';
      const lat=p.latency!=null?p.latency.toFixed(1)+'ms':(p.error||'—');
      return `<div class="port ${cls}"><div class="p">:${p.port}</div><div class="s">${st}</div><div class="ms">${esc(lat)}</div></div>`;
    }).join('');
    document.getElementById('portGrid').innerHTML=html||'<div class="empty">无结果</div>';
  }catch(e){document.getElementById('portGrid').innerHTML='<div class="empty">⚠ '+esc(e.message)+'</div>';}
  finally{btn.disabled=false;btn.textContent='扫描';}
}

// ════════════ DNS ════════════
async function startDns(){
  const domain=document.getElementById('dnsDomain').value.trim();
  if(!domain){toast('请输入域名');return;}
  const btn=document.getElementById('dnsBtn');
  btn.disabled=true;btn.innerHTML='<span class="spin"></span> 解析中';
  document.getElementById('dnsList').innerHTML='<div class="empty">解析中…</div>';
  try{
    const r=await fetch('/api/dns?domain='+encodeURIComponent(domain));
    const d=await r.json();
    if(d.error){document.getElementById('dnsList').innerHTML='<div class="empty">⚠ '+esc(d.error)+'</div>';return;}
    if(!d.addresses||d.addresses.length===0){
      document.getElementById('dnsList').innerHTML='<div class="empty">无 A 记录</div>';return;
    }
    const html=d.addresses.map((a,i)=>
      `<div class="dns-item"><span class="idx">${i+1}</span>`+
      `<span class="addr">${esc(a)}</span>`+
      `<span class="copy" onclick="copy('${esc(a)}')">复制</span></div>`).join('');
    document.getElementById('dnsList').innerHTML=html;
    toast('解析到 '+d.addresses.length+' 条 A 记录');
  }catch(e){document.getElementById('dnsList').innerHTML='<div class="empty">⚠ '+esc(e.message)+'</div>';}
  finally{btn.disabled=false;btn.textContent='解析';}
}

// 首次绘制（等待布局完成）
requestAnimationFrame(()=>{resizeCanvas();drawPing();});
pingStats();
</script></body></html>"""


# ── HTTP 处理器 ───────────────────────────────────────────
class H(BaseHTTPRequestHandler):
    # 用 HTTP/1.1，配合 Connection: close 让 SSE 流在结束时关闭
    protocol_version = "HTTP/1.1"

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json;charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def handle_ping(self, q):
        """SSE 流式返回每次 ping 结果"""
        host = q.get("host", [""])[0].strip()
        count = q.get("count", ["10"])[0]
        try:
            count = max(1, min(int(count), 50))
        except ValueError:
            count = 10
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream;charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            for i in range(1, count + 1):
                if not host:
                    res = {"seq": i, "latency": None, "timeout": True,
                           "method": "tcp", "error": "no host"}
                else:
                    res = ping_once(host)
                    res["seq"] = i
                self.wfile.write(
                    ("data: " + json.dumps(res, ensure_ascii=False) + "\n\n")
                    .encode("utf-8"))
                self.wfile.flush()
                # 仅 TCP 回退时补一拍节奏；系统 ping 自带 ~1s 间隔
                if res.get("method") == "tcp" and res.get("latency") is not None:
                    time.sleep(1)
        except (BrokenPipeError, ConnectionResetError):
            # 客户端已断开
            return
        # 发送结束标记
        try:
            self.wfile.write(
                ("data: " + json.dumps({"done": True},
                 ensure_ascii=False) + "\n\n").encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def handle_tcping(self, q):
        host = q.get("host", [""])[0].strip()
        ports_raw = q.get("ports", ["80,443,8080"])[0]
        if not host:
            self._json({"error": "缺少 host 参数"})
            return
        # 解析端口列表
        ports = []
        for p in ports_raw.split(","):
            p = p.strip()
            if not p:
                continue
            try:
                n = int(p)
                if 1 <= n <= 65535 and n not in ports:
                    ports.append(n)
            except ValueError:
                continue
        if not ports:
            self._json({"error": "未识别到有效端口"})
            return
        results = [tcping_once(host, p, timeout=2) for p in ports]
        self._json({"host": host, "count": len(results), "results": results})

    def handle_dns(self, q):
        domain = q.get("domain", [""])[0].strip()
        if not domain:
            self._json({"error": "缺少 domain 参数"})
            return
        self._json(dns_resolve(domain))

    def handle_whoami(self):
        info = get_local_info()
        info["port"] = PORT
        self._json(info)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/api/ping":
            self.handle_ping(q)
            return
        if u.path == "/api/tcping":
            self.handle_tcping(q)
            return
        if u.path == "/api/dns":
            self.handle_dns(q)
            return
        if u.path == "/api/whoami":
            self.handle_whoami()
            return
        # 首页
        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html;charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"net-diag → http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
