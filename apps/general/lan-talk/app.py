"""lan-talk —— 端到端加密局域网聊天室 (纯前端应用)"""
import json, os
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

def get_port():
    """优先级: 环境变量 > app.json > 0(系统随机)"""
    env_port = os.environ.get("LAUNCHER_APP_PORT")
    if env_port:
        try: return int(env_port)
        except ValueError: pass
    
    app_json_path = Path(__file__).parent / "app.json"
    if app_json_path.exists():
        try:
            config = json.loads(app_json_path.read_text(encoding="utf-8"))
            # 兼容处理：防止 json 中键名带有意外空格
            port = config.get("port") or config.get("port ")
            if port: return int(port)
        except Exception: pass
    return 0

PORT = get_port()

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>LAN·TALK — 茶水间</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=ZCOOL+QingKe+HuangYou&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<script src="https://unpkg.com/mqtt@5/dist/mqtt.min.js"></script>
<style>
:root{
  --bg0:#08151d; --panel:#0e2331; --panel2:#0a1a24;
  --line:#1c3a4c; --line2:#2a4d63;
  --ink:#d9eaf4; --dim:#6f93a6; --faint:#43627a;
  --amber:#ffc857; --amber-d:#8a6516;
  --green:#57d99c; --coral:#ff7a6b; --cyan:#59cfe4;
  --mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Consolas,monospace;
  --disp:'ZCOOL QingKe HuangYou','Noto Sans SC',sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{
  font-family:'Noto Sans SC',system-ui,'PingFang SC','Microsoft YaHei',sans-serif;
  color:var(--ink);overflow:hidden;display:flex;flex-direction:column;
  background:
    radial-gradient(1100px 560px at 88% -10%, rgba(89,207,228,.09), transparent 60%),
    radial-gradient(900px 520px at -8% 112%, rgba(255,200,87,.07), transparent 60%),
    var(--bg0);
}
body::after{content:'';position:fixed;inset:0;z-index:70;pointer-events:none;
  background:repeating-linear-gradient(0deg,rgba(255,255,255,.022) 0 1px,transparent 1px 3px);
  animation:flick 9s infinite}
@keyframes flick{0%,100%{opacity:.9}50%{opacity:.65}}
body::before{content:'';position:fixed;inset:-40% -25%;z-index:0;pointer-events:none;
  background:linear-gradient(115deg,transparent 45%,rgba(89,207,228,.05) 50%,transparent 55%);
  animation:sweep 15s linear infinite}
@keyframes sweep{from{transform:translateX(-28%)}to{transform:translateX(28%)}}

#app{position:relative;z-index:1;flex:1;display:flex;flex-direction:column;gap:10px;
  width:100%;max-width:1240px;margin:0 auto;padding:14px 16px 8px;min-height:0}

header{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;
  padding:10px 14px;border:1px solid var(--line);border-radius:8px;
  background:linear-gradient(180deg,var(--panel),var(--panel2));box-shadow:0 8px 24px rgba(0,0,0,.35)}
.logo{font-family:var(--disp);font-size:23px;letter-spacing:1px;color:var(--amber);
  display:flex;align-items:center;gap:10px;text-shadow:0 0 18px rgba(255,200,87,.25)}
.logo .blk{width:10px;height:23px;background:var(--amber);box-shadow:0 0 14px rgba(255,200,87,.6);animation:blink 2.4s steps(1) infinite}
.logo small{font-family:var(--mono);font-size:10px;color:var(--dim);letter-spacing:2px;text-shadow:none}
@keyframes blink{50%{opacity:.25}}
.hright{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.pill{display:flex;align-items:center;gap:7px;font-family:var(--mono);font-size:11px;color:var(--dim);
  border:1px solid var(--line);border-radius:999px;padding:6px 12px;background:var(--panel2)}
.pill b{color:var(--ink)}
.led{width:8px;height:8px;border-radius:50%;background:var(--coral);animation:pulse 1.5s infinite}
.led.on{background:var(--green)}
@keyframes pulse{50%{opacity:.35}}
.ibtn{background:var(--panel2);border:1px solid var(--line);color:var(--ink);border-radius:6px;
  padding:7px 11px;cursor:pointer;font-size:13px;font-family:inherit;transition:.15s;display:inline-flex;gap:6px;align-items:center}
.ibtn:hover{border-color:var(--amber);color:var(--amber);transform:translateY(-1px);box-shadow:0 4px 14px rgba(255,200,87,.15)}
.ibtn:active{transform:translateY(0)}
.ibtn.muted{opacity:.5}

main{flex:1;display:grid;grid-template-columns:180px 1fr 232px;gap:10px;min-height:0}

.rooms{display:flex;flex-direction:column;min-height:0;background:var(--panel2);border:1px solid var(--line);border-radius:8px}
.rooms h3{font-family:var(--disp);font-size:15px;letter-spacing:2px;color:var(--cyan);padding:12px 12px 8px}
#roomList{flex:1;overflow-y:auto;list-style:none;padding:0 6px 8px}
.room-item{display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:6px;cursor:pointer;
  font-size:13px;border:1px solid transparent;margin-bottom:2px;transition:.12s}
.room-item:hover{background:rgba(89,207,228,.08);border-color:var(--line)}
.room-item.active{background:linear-gradient(90deg,rgba(255,200,87,.12),transparent);border-color:rgba(255,200,87,.3)}
.room-item .rn{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}
.room-item .badge{font-family:var(--mono);font-size:10px;background:var(--coral);color:#fff;border-radius:999px;padding:1px 6px;min-width:18px;text-align:center}

.chatcol{position:relative;display:flex;flex-direction:column;min-height:0;overflow:hidden;
  background:var(--panel2);border:1px solid var(--line);border-radius:8px}
#msgs{flex:1;overflow-y:auto;padding:12px 6px;transition:opacity .18s}
#msgs::-webkit-scrollbar,#users::-webkit-scrollbar,#roomList::-webkit-scrollbar{width:8px}
#msgs::-webkit-scrollbar-thumb,#users::-webkit-scrollbar-thumb,#roomList::-webkit-scrollbar-thumb{background:var(--line2);border-radius:4px}

.msg{display:flex;gap:10px;padding:4px 14px;border-left:2px solid transparent;animation:pop .18s ease-out}
.msg:hover{background:rgba(255,255,255,.03)}
.msg.me{border-left-color:var(--amber);background:linear-gradient(90deg,rgba(255,200,87,.07),transparent 70%)}
.msg .t,.sys .t{font-family:var(--mono);font-size:11px;color:var(--faint);padding-top:3px;flex:none}
.msg .n{font-family:var(--mono);font-weight:700;font-size:13px;flex:none;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.msg .n::before{content:'<';color:var(--faint)} .msg .n::after{content:'>';color:var(--faint)}
.msg .b{font-size:14px;line-height:1.6;word-break:break-word;white-space:pre-wrap}
.msg img.preview{max-width:280px;max-height:220px;border-radius:6px;margin-top:6px;cursor:pointer;border:1px solid var(--line)}
.msg .file-link{color:var(--cyan);text-decoration:underline;cursor:pointer;margin-top:4px;display:inline-block}
.msg .lock{font-size:10px;opacity:.6;margin-left:4px}
@keyframes pop{from{opacity:0;transform:translateY(6px)}}
.sys{display:flex;gap:10px;padding:2px 14px;font-family:var(--mono);font-size:12px;font-style:italic;animation:pop .18s ease-out}
.sys .s{opacity:.9}
.sys.in .s{color:var(--green)} .sys.out .s{color:var(--coral)} .sys.info .s{color:var(--dim)}

#empty{text-align:center;margin-top:11vh;font-family:var(--mono);color:var(--faint)}
#empty .big{font-size:24px;letter-spacing:6px;color:var(--dim);margin-bottom:10px}

#jump{position:absolute;left:50%;bottom:140px;transform:translateX(-50%);display:none;z-index:5;
  background:var(--amber);color:#231a05;border:none;font-weight:700;font-size:12px;font-family:inherit;
  padding:6px 14px;border-radius:999px;cursor:pointer;box-shadow:0 6px 18px rgba(255,200,87,.35)}

#typing{height:22px;padding:0 14px;font-family:var(--mono);font-size:11px;color:var(--cyan);display:flex;align-items:center;gap:6px}
.dots{display:inline-flex;gap:3px}.dots i{width:4px;height:4px;border-radius:50%;background:var(--cyan);animation:bob 1s infinite}
.dots i:nth-child(2){animation-delay:.15s}.dots i:nth-child(3){animation-delay:.3s}
@keyframes bob{30%{transform:translateY(-3px);opacity:.4}}

.composer{display:flex;gap:8px;padding:10px 12px 8px;border-top:1px solid var(--line);background:var(--panel);align-items:flex-end}
textarea{flex:1;resize:none;background:var(--bg0);border:1px solid var(--line);border-radius:6px;
  color:var(--ink);padding:10px 12px;font:inherit;font-size:14px;line-height:1.5;max-height:110px;transition:.15s}
textarea:focus{outline:none;border-color:var(--amber);box-shadow:0 0 0 3px rgba(255,200,87,.12)}
#btnSend{background:var(--amber);color:#231a05;border:none;font-weight:700;border-radius:6px;letter-spacing:3px;
  padding:10px 18px;cursor:pointer;font-size:14px;font-family:inherit;transition:.15s;box-shadow:0 4px 0 var(--amber-d)}
#btnSend:hover{filter:brightness(1.08)}
#btnSend:active{transform:translateY(3px);box-shadow:0 1px 0 var(--amber-d)}
.tool-btn{background:var(--panel2);border:1px solid var(--line);color:var(--ink);border-radius:6px;
  width:42px;height:42px;cursor:pointer;font-size:18px;display:flex;align-items:center;justify-content:center;transition:.15s}
.tool-btn:hover{border-color:var(--amber);color:var(--amber)}
.hint{padding:0 14px 8px;font-family:var(--mono);font-size:10px;color:var(--faint);background:var(--panel)}

aside{display:flex;flex-direction:column;min-height:0;background:var(--panel2);border:1px solid var(--line);border-radius:8px}
aside h3{font-family:var(--disp);font-size:16px;letter-spacing:3px;color:var(--cyan);
  padding:12px 14px 8px;display:flex;justify-content:space-between;align-items:baseline}
aside h3 small{font-family:var(--mono);font-size:10px;color:var(--dim);letter-spacing:0}
#users{flex:1;overflow-y:auto;list-style:none;padding:2px 8px 8px}
.u{display:flex;align-items:center;gap:9px;padding:7px 9px;border-radius:6px;cursor:pointer;
  font-size:13px;border:1px solid transparent;transition:.12s}
.u:hover{background:rgba(89,207,228,.08);border-color:var(--line)}
.u.selected{background:rgba(255,200,87,.12);border-color:rgba(255,200,87,.35)}
.u .dot{width:9px;height:9px;border-radius:2px;flex:none;background:var(--c,#fff);box-shadow:0 0 8px var(--c,#fff)}
.u .dot.off{opacity:.35;box-shadow:none}
.u .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}
.u .tag{margin-left:auto;font-family:var(--mono);font-size:10px;color:var(--faint);flex:none}
.u.me{background:linear-gradient(90deg,rgba(255,200,87,.1),transparent);border-color:rgba(255,200,87,.25)}
.u input[type=checkbox]{accent-color:var(--amber);flex:none}
.aside-tip{padding:8px 14px;border-top:1px dashed var(--line);font-family:var(--mono);font-size:10px;color:var(--faint)}
.aside-actions{padding:8px;border-top:1px dashed var(--line)}
.aside-actions .ibtn{width:100%;justify-content:center}

footer{display:flex;justify-content:space-between;gap:10px;font-family:var(--mono);font-size:11px;color:var(--dim);padding:2px 6px 4px}

#join{position:fixed;inset:0;z-index:50;display:flex;align-items:center;justify-content:center;
  background:rgba(4,10,14,.85);backdrop-filter:blur(4px);transition:opacity .3s}
#join.hide{opacity:0;pointer-events:none}
.term{width:min(460px,92vw);background:var(--panel2);border:1px solid var(--line2);border-radius:10px;
  overflow:hidden;box-shadow:0 30px 80px rgba(0,0,0,.6);animation:rise .4s cubic-bezier(.2,.9,.3,1.15)}
@keyframes rise{from{transform:translateY(18px) scale(.97);opacity:0}}
.term-bar{display:flex;align-items:center;gap:6px;padding:10px 14px;background:var(--panel);
  border-bottom:1px solid var(--line);font-family:var(--mono);font-size:11px;color:var(--dim)}
.term-bar i{width:10px;height:10px;border-radius:50%}
.term-body{padding:26px 26px 24px}
.term-body h1{font-family:var(--disp);font-size:36px;letter-spacing:2px;line-height:1.2}
.term-body h1 b{color:var(--amber)}
.prompt{font-family:var(--mono);font-size:12px;color:var(--green);margin:10px 0 20px}
.prompt .cur{display:inline-block;width:8px;height:13px;background:var(--green);vertical-align:-2px;animation:blink 1s steps(1) infinite}
.f-row{display:flex;gap:8px}
#nickInp,#setNick,#setMqtt,#setPass,#roomPassInp,#joinPass,#invitePass,#newRoomName,#diagUrl,#diagUser,#diagPass{
  flex:1;background:var(--bg0);border:1px solid var(--line);border-radius:6px;color:var(--ink);padding:10px 12px;font:inherit;width:100%}
.dice{width:46px;flex:none;font-size:19px;justify-content:center}
.dice.spin{animation:spin .5s}
@keyframes spin{to{transform:rotate(360deg)}}
#btnJoin{width:100%;margin-top:12px;background:var(--amber);color:#231a05;border:none;border-radius:6px;
  font-weight:700;font-size:15px;letter-spacing:4px;padding:12px;cursor:pointer;font-family:inherit;
  box-shadow:0 4px 0 var(--amber-d);transition:.15s}
#btnJoin:hover{filter:brightness(1.08)}
.perks{margin-top:18px;display:grid;gap:7px;font-size:12px;color:var(--dim);list-style:none}
.perks li::before{content:'▸ ';color:var(--amber)}

#pop,#diag,#invitePop,#newRoomPop{position:fixed;top:66px;right:18px;z-index:40;width:340px;display:none;padding:16px;
  background:var(--panel2);border:1px solid var(--line2);border-radius:10px;box-shadow:0 20px 60px rgba(0,0,0,.55)}
#pop.open,#diag.open,#invitePop.open,#newRoomPop.open{display:block;animation:rise .22s}
#pop label,#diag label,#invitePop label,#newRoomPop label{display:block;margin:12px 0 5px;font-family:var(--mono);font-size:10px;letter-spacing:2px;color:var(--dim)}
#pop label:first-child,#diag label:first-child,#invitePop label:first-child,#newRoomPop label:first-child{margin-top:0}
#pop .tip,#invitePop .tip,#newRoomPop .tip{margin:8px 0 12px;font-size:11px;line-height:1.7;color:var(--faint)}
#pop .primary,#diag .primary,#invitePop .primary,#newRoomPop .primary,#invitePop .secondary,#newRoomPop .secondary{
  background:var(--amber);color:#231a05;font-weight:700;border:none;box-shadow:0 3px 0 var(--amber-d);
  width:100%;padding:10px;border-radius:6px;cursor:pointer;margin-top:8px;font-family:inherit}
#invitePop .secondary,#newRoomPop .secondary{background:var(--panel);color:var(--ink);box-shadow:none;border:1px solid var(--line)}

#diagLog{background:#050d12;border:1px solid var(--line);border-radius:6px;padding:10px;height:220px;overflow:auto;
  font-family:var(--mono);font-size:11px;line-height:1.7;white-space:pre-wrap;margin-top:8px}
#diagLog .ok{color:var(--green)} #diagLog .bad{color:var(--coral)} #diagLog .info{color:var(--cyan)} #diagLog .dim{color:var(--dim)}

#emojiPanel{position:absolute;bottom:70px;left:12px;z-index:10;display:none;width:280px;max-height:200px;overflow-y:auto;
  background:var(--panel);border:1px solid var(--line2);border-radius:8px;padding:10px;box-shadow:0 12px 30px rgba(0,0,0,.5)}
#emojiPanel.open{display:grid;grid-template-columns:repeat(8,1fr);gap:4px}
#emojiPanel span{font-size:22px;cursor:pointer;text-align:center;padding:4px;border-radius:4px}
#emojiPanel span:hover{background:rgba(255,200,87,.15)}

@media(max-width:900px){
  main{grid-template-columns:1fr}
  .rooms{order:-2;max-height:100px}
  #roomList{display:flex;flex-wrap:wrap;gap:4px}
  aside{order:-1;max-height:140px}
  #users{display:flex;flex-wrap:wrap;gap:4px}
}
</style>
</head>
<body>

<div id="join">
  <div class="term">
    <div class="term-bar">
      <i style="background:#ff7a6b"></i><i style="background:#ffc857"></i><i style="background:#57d99c"></i>
      <span>lan-talk mqtt · e2ee · no-log</span>
    </div>
    <div class="term-body">
      <h1>接入 <b>#茶水间</b></h1>
      <div class="prompt">guest@mqtt:~$ ./join --e2ee --no-log <span class="cur"></span></div>
      <div class="f-row">
        <input id="nickInp" maxlength="16" placeholder="输入你的昵称…" autocomplete="off">
        <button class="ibtn dice" id="diceJoin" title="随机昵称">🎲</button>
      </div>
      <label style="display:block;margin:12px 0 5px;font-family:var(--mono);font-size:10px;letter-spacing:2px;color:var(--dim)">茶水间口令（加密）</label>
      <input id="joinPass" type="password" placeholder="默认 chashuijian，可改" autocomplete="off">
      <button id="btnJoin">进 入 频 道 ⏎</button>
      <ul class="perks">
        <li>消息 AES 加密，刷新即焚</li>
        <li>桌面通知 · 标题未读提示</li>
        <li>可选人发起私密加密群组</li>
      </ul>
    </div>
  </div>
</div>

<div id="app">
  <header>
    <div class="logo"><span class="blk"></span>LAN·TALK <small>茶水间</small></div>
    <div class="hright">
      <div class="pill"><i id="led" class="led"></i><span id="pillTxt">未连接</span></div>
      <div class="pill">🔒 <b id="encTxt">加密</b></div>
      <div class="pill">👥 在线 <b id="cnt">0</b></div>
      <button class="ibtn" id="btnNotify" title="桌面通知">📢</button>
      <button class="ibtn" id="btnClear" title="清屏">🧹 清屏</button>
      <button class="ibtn" id="btnDiag" title="连接诊断">📡 诊断</button>
      <button class="ibtn" id="btnSet" title="设置">⚙ 设置</button>
    </div>
  </header>

  <main>
    <section class="rooms">
      <h3>频道</h3>
      <ul id="roomList"></ul>
    </section>

    <section class="chatcol">
      <div id="msgs"></div>
      <button id="jump"></button>
      <div id="typing"></div>
      <div class="composer">
        <button class="tool-btn" id="btnEmoji" title="表情">😊</button>
        <button class="tool-btn" id="btnFile" title="图片/文件">📎</button>
        <textarea id="inp" rows="1" placeholder="先取个昵称…"></textarea>
        <button id="btnSend">发 送</button>
      </div>
      <div class="hint">Enter 发送 · Shift+Enter 换行 · 🔒 端到端加密 · 消息不保存</div>
      <div id="emojiPanel"></div>
    </section>

    <aside>
      <h3 id="asideTitle">在线名单 <small id="ucnt">0 人</small></h3>
      <ul id="users"></ul>
      <div class="aside-actions" id="asideActions">
        <button class="ibtn" id="btnCreateRoom">创建私密群</button>
      </div>
      <div class="aside-tip" id="asideTip">勾选用户后点「创建私密群」· 点名字可 @</div>
    </aside>
  </main>

  <footer>
    <span id="stRoom">#茶水间</span> · <span id="stMode">未连接</span>
    <span>无日志 / 加密传输 / 刷新即焚</span>
  </footer>
</div>

<div id="pop">
  <label>昵称 NICK</label>
  <div class="f-row">
    <input id="setNick" maxlength="16" autocomplete="off">
    <button class="ibtn dice" id="diceSet">🎲</button>
  </div>
  <label>MQTT WebSocket 地址</label>
  <input id="setMqtt" placeholder="ws://1.15.30.237:8083/mqtt" autocomplete="off">
  <label>当前频道加密口令</label>
  <input id="setPass" type="password" placeholder="房间口令" autocomplete="off">
  <p class="tip">口令相同的人才能解密消息。保存后会重新派生密钥。<br>建议生产环境使用 wss://</p>
  <button class="primary" id="setSave">保 存 并 重 连</button>
</div>

<div id="diag">
  <label>连接诊断</label>
  <input id="diagUrl" value="ws://1.15.30.237:8083/mqtt">
  <div class="f-row" style="margin-top:6px">
    <input id="diagUser" placeholder="用户名（可选）">
    <input id="diagPass" placeholder="密码（可选）">
  </div>
  <button class="primary" id="btnRunDiag">开始诊断</button>
  <div id="diagLog"></div>
</div>

<div id="invitePop">
  <label>私密频道邀请</label>
  <p class="tip" id="inviteTxt">有人邀请你加入私密群</p>
  <label>加入口令（可改）</label>
  <input id="invitePass" type="password" autocomplete="off">
  <button class="primary" id="inviteAccept">加 入</button>
  <button class="secondary" id="inviteReject">忽 略</button>
</div>

<div id="newRoomPop">
  <label>新建私密群</label>
  <p class="tip" id="newRoomTip">将邀请已勾选的用户</p>
  <label>群名称</label>
  <input id="newRoomName" placeholder="例如：摸鱼小分队" maxlength="20">
  <label>加密口令</label>
  <input id="roomPassInp" type="password" placeholder="群口令，成员需一致" autocomplete="off">
  <button class="primary" id="newRoomOk">创 建 并 邀 请</button>
  <button class="secondary" id="newRoomCancel">取 消</button>
</div>

<input type="file" id="fileInput" accept="image/*,*/*" hidden>

<script>
(function(){
'use strict';
const $=s=>document.querySelector(s);
const PALETTE=['#ffc857','#57d99c','#ff7a6b','#59cfe4','#c7a1ff','#f2e85c','#ff9ecb','#9eddff'];
const myId = Math.random().toString(36).slice(2,10) + Date.now().toString(36);
let myName = '', notifyOn = true, client = null, connected = false;
let originTitle = document.title;
let totalUnread = 0;

const TOPIC_MSG = 'chat/messages';
const TOPIC_PRESENCE = 'chat/presence';
const TOPIC_INVITE = 'chat/invite';
const MAX_FILE_SIZE = 800 * 1024;
const PUBLIC_ROOM = 'public';
const DEFAULT_PASS = 'chashuijian';

const box=$('#msgs'), inp=$('#inp'), jump=$('#jump'), typingEl=$('#typing'),
      usersEl=$('#users'), cntEl=$('#cnt'), ucntEl=$('#ucnt'),
      led=$('#led'), pillTxt=$('#pillTxt'), stMode=$('#stMode'), stRoom=$('#stRoom'),
      overlay=$('#join'), nickInp=$('#nickInp'), pop=$('#pop'),
      diag=$('#diag'), emojiPanel=$('#emojiPanel'), fileInput=$('#fileInput'),
      roomListEl=$('#roomList'), asideTitle=$('#asideTitle'), asideTip=$('#asideTip'),
      asideActions=$('#asideActions');

const pad=n=>String(n).padStart(2,'0');
const fmt=ts=>{const d=new Date(ts);return pad(d.getHours())+':'+pad(d.getMinutes());};
const hash=s=>{let h=7;for(const c of s)h=(h*31+c.codePointAt(0))>>>0;return h;};
const colorOf=n=>PALETTE[hash(n)%PALETTE.length];
const el=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e;};
const ADJ=['摸鱼','隐身','佛系','暴躁','野生','像素','复古','快乐','低调','夜行','带电','软糖'];
const NOUN=['水母','河马','路由器','台灯','企鹅','仓鼠','电报机','仙人掌','考拉','恐龙','猫爪','信号塔'];
const pick=a=>a[Math.floor(Math.random()*a.length)];
const randomName=()=>pick(ADJ)+pick(NOUN)+(Math.random()<.45?String(Math.floor(Math.random()*90+10)):'');

const EMOJIS = [
  '😀','😂','🤣','😊','😍','🥰','😘','😜','🤔','🙄','😴','😭','😤',
  '👍','👎','👏','🔥','✨','🎉','❤️','💙','💚','💛','💜','🖤','💯',
  '✅','❌','⭐','🌟','🎈','🎁','🍕','🍔','🍟','☕','🍵','🍺','🍻',
  '🍦','🍩','🍪','🍉','🍇','🍓','🍒','🍑'
];

/* ── 加密 ── */
const keyCache = new Map();
async function deriveKey(password) {
  if (keyCache.has(password)) return keyCache.get(password);
  const enc = new TextEncoder();
  const keyMaterial = await crypto.subtle.importKey('raw', enc.encode(password), 'PBKDF2', false, ['deriveKey']);
  const key = await crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt: enc.encode('lan-talk-v1-salt'), iterations: 100000, hash: 'SHA-256' },
    keyMaterial, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']
  );
  keyCache.set(password, key);
  return key;
}
function bufToB64(buf) {
  const bytes = new Uint8Array(buf);
  let s = '';
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return btoa(s);
}
function b64ToBuf(b64) {
  const s = atob(b64);
  const bytes = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) bytes[i] = s.charCodeAt(i);
  return bytes;
}
async function encryptText(text, password) {
  const key = await deriveKey(password);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encoded = new TextEncoder().encode(text);
  const cipher = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, encoded);
  const packed = new Uint8Array(iv.length + cipher.byteLength);
  packed.set(iv, 0);
  packed.set(new Uint8Array(cipher), iv.length);
  return bufToB64(packed);
}
async function decryptText(b64, password) {
  const key = await deriveKey(password);
  const raw = b64ToBuf(b64);
  const iv = raw.slice(0, 12);
  const data = raw.slice(12);
  const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, data);
  return new TextDecoder().decode(plain);
}

/* ── 房间 ── */
const rooms = new Map();
let currentRoomId = PUBLIC_ROOM;

function ensurePublicRoom(pass) {
  if (!rooms.has(PUBLIC_ROOM)) {
    rooms.set(PUBLIC_ROOM, {
      id: PUBLIC_ROOM, name: '茶水间', topic: TOPIC_MSG,
      password: pass || DEFAULT_PASS, history: [], unread: 0, private: false, members: []
    });
  } else if (pass) rooms.get(PUBLIC_ROOM).password = pass;
}
function roomTopic(roomId) {
  return roomId === PUBLIC_ROOM ? TOPIC_MSG : `chat/room/${roomId}`;
}
function getCurrentRoom() { return rooms.get(currentRoomId); }

function renderRoomList() {
  roomListEl.innerHTML = '';
  for (const r of rooms.values()) {
    const li = el('li', 'room-item' + (r.id === currentRoomId ? ' active' : ''));
    li.dataset.id = r.id;
    li.appendChild(el('span', 'rn', (r.private ? '🔒 ' : '#') + r.name));
    if (r.unread > 0 && r.id !== currentRoomId) {
      li.appendChild(el('span', 'badge', String(r.unread > 99 ? '99+' : r.unread)));
    }
    li.addEventListener('click', () => switchRoom(r.id));
    roomListEl.appendChild(li);
  }
  const cur = getCurrentRoom();
  stRoom.textContent = cur ? (cur.private ? '🔒 ' : '#') + cur.name : '';
}

function switchRoom(roomId) {
  if (!rooms.has(roomId)) return;
  currentRoomId = roomId;
  const room = rooms.get(roomId);
  room.unread = 0;
  box.innerHTML = '';
  if (room.history && room.history.length) {
    room.history.forEach(h => box.appendChild(h.cloneNode(true)));
    box.scrollTop = box.scrollHeight;
  } else showEmpty();
  window.pinned = true; window.unread = 0; jump.style.display = 'none';
  renderRoomList();
  updateTotalUnread();
  renderUsers();
  inp.focus();
}

function pushHistory(roomId, node) {
  const r = rooms.get(roomId);
  if (!r) return;
  if (!r.history) r.history = [];
  r.history.push(node.cloneNode(true));
  if (r.history.length > 200) r.history.shift();
}

/* ── 通知 ── */
async function ensureNotifyPermission() {
  if (!('Notification' in window)) return false;
  if (Notification.permission === 'granted') return true;
  if (Notification.permission !== 'denied') {
    return (await Notification.requestPermission()) === 'granted';
  }
  return false;
}
function desktopNotify(title, body) {
  if (!notifyOn) return;
  if (document.visibilityState === 'visible' && document.hasFocus()) return;
  if (!('Notification' in window) || Notification.permission !== 'granted') return;
  try {
    const n = new Notification(title, { body: (body || '').slice(0, 120), tag: 'lan-talk-' + Date.now() });
    n.onclick = () => { window.focus(); n.close(); };
  } catch (e) {}
}
function updateTotalUnread() {
  let titleUnread = 0;
  for (const r of rooms.values()) {
    if (r.id !== currentRoomId) titleUnread += r.unread;
  }
  if (document.visibilityState === 'hidden') titleUnread += window.totalUnread;
  document.title = titleUnread > 0 ? `(${titleUnread}) LAN·TALK — 茶水间` : originTitle;
  renderRoomList();
}
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') {
    window.totalUnread = 0;
    const cur = getCurrentRoom();
    if (cur) cur.unread = 0;
    updateTotalUnread();
  }
});
window.addEventListener('focus', () => {
  window.totalUnread = 0;
  const cur = getCurrentRoom();
  if (cur) cur.unread = 0;
  updateTotalUnread();
});

/* ── MQTT ── */
function getMqttUrl() {
  return (sessionStorage.getItem('mqttUrl') || 'ws://1.15.30.237:8083/mqtt').trim();
}
function connectMqtt() {
  if (client) { try { client.end(true); } catch (e) {} }
  updateStatus('connecting');
  client = mqtt.connect(getMqttUrl(), {
    clientId: 'web_' + myId, clean: true, reconnectPeriod: 4000, connectTimeout: 10000,
    will: {
      topic: `${TOPIC_PRESENCE}/${myId}`,
      payload: JSON.stringify({ id: myId, name: myName || '???', status: 'offline' }),
      qos: 1, retain: true
    }
  });
  client.on('connect', () => {
    connected = true;
    updateStatus('connected');
    client.subscribe(TOPIC_MSG, { qos: 1 });
    client.subscribe(`${TOPIC_PRESENCE}/#`, { qos: 1 });
    client.subscribe(`${TOPIC_INVITE}/${myId}`, { qos: 1 });
    for (const r of rooms.values()) {
      if (r.private) client.subscribe(r.topic, { qos: 1 });
    }
    publishPresence('online');
    if (myName) sys('已连接 Broker（消息已加密）', 'info');
  });
  client.on('reconnect', () => updateStatus('connecting'));
  client.on('close', () => { connected = false; updateStatus('closed'); });
  client.on('error', err => { console.error(err); updateStatus('error'); });
  client.on('message', async (topic, payload) => {
    try {
      const data = JSON.parse(payload.toString());
      if (topic === TOPIC_MSG) await handleChat(data, PUBLIC_ROOM);
      else if (topic.startsWith('chat/room/')) {
        const rid = topic.slice('chat/room/'.length);
        if (rooms.has(rid)) await handleChat(data, rid);
      } else if (topic.startsWith(TOPIC_PRESENCE + '/')) handlePresence(data);
      else if (topic === `${TOPIC_INVITE}/${myId}`) handleInvite(data);
    } catch (e) { console.warn(e); }
  });
}
function publish(topic, obj, retain = false) {
  if (!client || !connected) return;
  client.publish(topic, JSON.stringify(obj), { qos: 1, retain });
}
function publishPresence(status) {
  if (!myName) return;
  publish(`${TOPIC_PRESENCE}/${myId}`, { id: myId, name: myName, status, ts: Date.now() }, true);
}
function updateStatus(s) {
  led.className = 'led' + (s === 'connected' ? ' on' : '');
  const map = { connected: '已连接', connecting: '连接中…', closed: '已断开', error: '连接失败' };
  const t = map[s] || '未连接';
  pillTxt.textContent = t;
  stMode.textContent = t;
}

/* ── 在线 / 群成员 ── */
const peers = new Map();
const selectedPeers = new Set();

function handlePresence(data) {
  if (!data || !data.id || data.id === myId) return;
  if (data.status === 'offline') {
    if (peers.has(data.id)) {
      const p = peers.get(data.id);
      if (currentRoomId === PUBLIC_ROOM) sys(p.name + ' 离开了', 'out');
      peers.delete(data.id);
      selectedPeers.delete(data.id);
      renderUsers();
    }
    return;
  }
  const old = peers.get(data.id);
  peers.set(data.id, { id: data.id, name: data.name || '???', ts: Date.now() });
  for (const r of rooms.values()) {
    if (!r.private || !r.members) continue;
    const m = r.members.find(x => x.id === data.id);
    if (m) m.name = data.name || m.name;
  }
  if (!old && currentRoomId === PUBLIC_ROOM) sys(data.name + ' 进入了茶水间', 'in');
  renderUsers();
}

function isPeerOnline(id) {
  return id === myId || peers.has(id);
}

function renderUsers() {
  usersEl.innerHTML = '';
  const room = getCurrentRoom();

  if (room && room.private) {
    asideTitle.innerHTML = '群成员 <small id="ucnt"></small>';
    const uc = $('#ucnt');
    const members = room.members || [];
    const sorted = [...members].sort((a, b) => {
      if (a.id === myId) return -1;
      if (b.id === myId) return 1;
      return (a.name || '').localeCompare(b.name || '', 'zh');
    });
    sorted.forEach(m => {
      const me = m.id === myId;
      const online = isPeerOnline(m.id);
      usersEl.appendChild(memberLi(m, me, online));
    });
    if (uc) uc.textContent = members.length + ' 人';
    cntEl.textContent = String(peers.size + (myName ? 1 : 0));
    asideActions.style.display = 'none';
    asideTip.textContent = '绿点表示当前在线 · 点名字可 @';
  } else {
    asideTitle.innerHTML = '在线名单 <small id="ucnt"></small>';
    const uc = $('#ucnt');
    if (myName) usersEl.appendChild(userLi({ id: myId, name: myName }, true));
    const list = [...peers.values()].sort((a, b) => a.name.localeCompare(b.name, 'zh'));
    list.forEach(p => usersEl.appendChild(userLi(p, false)));
    const n = list.length + (myName ? 1 : 0);
    cntEl.textContent = n;
    if (uc) uc.textContent = n + ' 人';
    asideActions.style.display = '';
    asideTip.textContent = '勾选用户后点「创建私密群」· 点名字可 @';
  }
}

function userLi(p, me) {
  const li = el('li', 'u' + (me ? ' me' : '') + (selectedPeers.has(p.id) ? ' selected' : ''));
  if (!me) {
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = selectedPeers.has(p.id);
    cb.addEventListener('click', e => {
      e.stopPropagation();
      if (cb.checked) selectedPeers.add(p.id);
      else selectedPeers.delete(p.id);
      li.classList.toggle('selected', cb.checked);
    });
    li.appendChild(cb);
  }
  const dot = el('i', 'dot');
  dot.style.setProperty('--c', colorOf(p.name));
  li.appendChild(dot);
  li.appendChild(el('span', 'nm', p.name));
  if (me) li.appendChild(el('span', 'tag', '(我)'));
  else li.addEventListener('click', e => {
    if (e.target.tagName === 'INPUT') return;
    inp.value += '@' + p.name + ' ';
    inp.focus();
  });
  return li;
}

function memberLi(m, me, online) {
  const li = el('li', 'u' + (me ? ' me' : ''));
  const dot = el('i', 'dot' + (online ? '' : ' off'));
  dot.style.setProperty('--c', colorOf(m.name || '?'));
  li.appendChild(dot);
  li.appendChild(el('span', 'nm', m.name || '未知'));
  if (me) li.appendChild(el('span', 'tag', '(我)'));
  else {
    li.appendChild(el('span', 'tag', online ? '在线' : '离线'));
    li.addEventListener('click', () => {
      inp.value += '@' + (m.name || '') + ' ';
      inp.focus();
    });
  }
  return li;
}

setInterval(() => { if (myName && connected) publishPresence('online'); }, 8000);

/* ── 消息 ── */
async function handleChat(data, roomId) {
  if (!data || data.id === myId) return;
  const room = rooms.get(roomId);
  if (!room) return;

  if (data.type === 'typing') {
    if (roomId === currentRoomId) setTyping(data.id, data.name, !!data.on);
    return;
  }

  if (data.type === 'members' && data.members && room.private) {
    room.members = data.members;
    if (roomId === currentRoomId) renderUsers();
    return;
  }
  if (data.type === 'join' && room.private) {
    if (!room.members) room.members = [];
    if (!room.members.some(x => x.id === data.id)) {
      room.members.push({ id: data.id, name: data.from || data.name || '???' });
    } else {
      const m = room.members.find(x => x.id === data.id);
      if (m && data.from) m.name = data.from;
    }
    if (roomId === currentRoomId) {
      renderUsers();
      sys((data.from || '有人') + ' 加入了本群', 'in');
    }
    return;
  }

  let displayText = '';
  let filePayload = null;
  try {
    if (data.enc && data.cipher) {
      const plain = await decryptText(data.cipher, room.password);
      if (data.type === 'text') displayText = plain;
      else {
        const meta = JSON.parse(plain);
        filePayload = { ...data, ...meta, content: meta.content };
      }
    } else if (data.type === 'text') {
      displayText = data.text || '[无法解密的明文]';
    } else filePayload = data;
  } catch (e) {
    displayText = '🔒 [解密失败：口令可能不一致]';
  }

  const isCurrent = roomId === currentRoomId;
  if (data.type === 'text' || displayText) {
    addMsg(data.from, displayText || '', data.ts, false, isCurrent, roomId, true);
  } else if (filePayload) {
    addFileMsg(data.from, filePayload, false, isCurrent, roomId, true);
  }

  if (!isCurrent) {
    room.unread = (room.unread || 0) + 1;
    updateTotalUnread();
  } else if (document.visibilityState === 'hidden') {
    window.totalUnread++;
    updateTotalUnread();
  }
  const preview = data.type === 'text' ? (displayText || '').slice(0, 80) : (data.type === 'image' ? '[图片]' : '[文件]');
  desktopNotify((room.private ? '🔒 ' : '#') + room.name + ' · ' + data.from, preview);
}

/* ── 渲染 ── */
window.pinned = true; window.unread = 0;
function removeEmpty() { const e = $('#empty'); if (e) e.remove(); }
function showEmpty() {
  box.innerHTML = '';
  const d = el('div'); d.id = 'empty';
  d.innerHTML = '<div class="big">░░ 频道很安静 ░░</div><div>说点什么打破沉默 —— 消息加密且只存在于此刻</div>';
  box.appendChild(d);
}
function addMsg(name, text, ts, mine, show = true, roomId = currentRoomId, encrypted = false) {
  const row = el('div', 'msg' + (mine ? ' me' : ''));
  const n = el('span', 'n', name); n.style.color = colorOf(name);
  const b = el('div', 'b');
  b.textContent = text;
  if (encrypted) b.appendChild(el('span', 'lock', ' 🔒'));
  row.append(el('span', 't', fmt(ts)), n, b);
  pushHistory(roomId, row);
  if (show) {
    removeEmpty();
    box.appendChild(row);
    scrollOrJump(mine);
  }
}
function addFileMsg(name, data, mine, show = true, roomId = currentRoomId, encrypted = false) {
  const row = el('div', 'msg' + (mine ? ' me' : ''));
  const n = el('span', 'n', name); n.style.color = colorOf(name);
  const b = el('div', 'b');
  if (data.type === 'image') {
    const img = document.createElement('img');
    img.className = 'preview';
    img.src = data.content;
    img.title = data.filename || '图片';
    img.onclick = () => window.open(data.content, '_blank');
    b.appendChild(document.createTextNode('[图片] ' + (data.filename || '') + (encrypted ? ' 🔒' : '')));
    b.appendChild(document.createElement('br'));
    b.appendChild(img);
  } else {
    const a = el('a', 'file-link', '📎 ' + (data.filename || '文件') + ' （点击下载）' + (encrypted ? ' 🔒' : ''));
    a.href = data.content;
    a.download = data.filename || 'file';
    b.appendChild(a);
  }
  row.append(el('span', 't', fmt(data.ts || Date.now())), n, b);
  pushHistory(roomId, row);
  if (show) {
    removeEmpty();
    box.appendChild(row);
    scrollOrJump(mine);
  }
}
function scrollOrJump(mine) {
  if (window.pinned || mine) box.scrollTop = box.scrollHeight;
  else {
    window.unread++;
    jump.textContent = '↓ ' + window.unread + ' 条新消息';
    jump.style.display = 'block';
  }
}
function sys(text, kind) {
  removeEmpty();
  const row = el('div', 'sys ' + (kind || 'info'));
  row.append(el('span', 't', fmt(Date.now())), el('span', 's', '— ' + text));
  box.appendChild(row);
  pushHistory(currentRoomId, row);
  if (window.pinned) box.scrollTop = box.scrollHeight;
}
box.addEventListener('scroll', () => {
  window.pinned = box.scrollTop + box.clientHeight >= box.scrollHeight - 70;
  if (window.pinned) { window.unread = 0; jump.style.display = 'none'; }
});
jump.addEventListener('click', () => { box.scrollTop = box.scrollHeight; window.unread = 0; jump.style.display = 'none'; });

/* ── 正在输入 ── */
const typingPeers = new Map();
let typingOn = false, typingTimer = null;
function setTyping(id, name, on) {
  const cur = typingPeers.get(id);
  if (cur) clearTimeout(cur.t);
  if (on) typingPeers.set(id, { name, t: setTimeout(() => { typingPeers.delete(id); renderTyping(); }, 3200) });
  else typingPeers.delete(id);
  renderTyping();
}
function renderTyping() {
  typingEl.innerHTML = '';
  const names = [...typingPeers.values()].map(x => x.name).slice(0, 3);
  if (!names.length) return;
  const dots = el('span', 'dots'); dots.innerHTML = '<i></i><i></i><i></i>';
  typingEl.append(el('span', '', names.join('、') + ' 正在输入'), dots);
}
function typingPing() {
  if (!myName || !connected) return;
  const room = getCurrentRoom();
  if (!room) return;
  if (!typingOn) {
    typingOn = true;
    publish(room.topic, { type: 'typing', id: myId, name: myName, on: true });
  }
  clearTimeout(typingTimer);
  typingTimer = setTimeout(typingOff, 1400);
}
function typingOff() {
  clearTimeout(typingTimer);
  if (typingOn) {
    typingOn = false;
    const room = getCurrentRoom();
    if (room) publish(room.topic, { type: 'typing', id: myId, name: myName, on: false });
  }
}

/* ── 发送 ── */
async function sendChat() {
  const text = inp.value.trim();
  if (!text || !myName) return;
  const room = getCurrentRoom();
  if (!room) return;
  const ts = Date.now();
  try {
    const cipher = await encryptText(text, room.password);
    publish(room.topic, { type: 'text', id: myId, from: myName, enc: true, cipher, ts });
    addMsg(myName, text, ts, true, true, room.id, true);
  } catch (e) {
    alert('加密失败：' + e.message);
    return;
  }
  inp.value = '';
  autosize();
  typingOff();
  inp.focus();
}
async function sendFile(file) {
  if (!file || !myName) return;
  if (file.size > MAX_FILE_SIZE) { alert('文件太大（最大约 800KB）'); return; }
  const room = getCurrentRoom();
  if (!room) return;
  const reader = new FileReader();
  reader.onload = async () => {
    const isImage = file.type.startsWith('image/');
    const meta = { type: isImage ? 'image' : 'file', filename: file.name, content: reader.result };
    try {
      const cipher = await encryptText(JSON.stringify(meta), room.password);
      const payload = { type: isImage ? 'image' : 'file', id: myId, from: myName, enc: true, cipher, ts: Date.now() };
      publish(room.topic, payload);
      addFileMsg(myName, { ...meta, ts: payload.ts }, true, true, room.id, true);
    } catch (e) { alert('加密失败：' + e.message); }
  };
  reader.readAsDataURL(file);
}
$('#btnSend').addEventListener('click', () => sendChat());
inp.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
    e.preventDefault();
    sendChat();
  }
});
inp.addEventListener('input', () => { autosize(); typingPing(); });
function autosize() {
  inp.style.height = 'auto';
  inp.style.height = Math.min(inp.scrollHeight, 110) + 'px';
}

$('#btnFile').addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) sendFile(fileInput.files[0]);
  fileInput.value = '';
});
EMOJIS.forEach(e => {
  const s = el('span', '', e);
  s.onclick = () => { inp.value += e; inp.focus(); emojiPanel.classList.remove('open'); };
  emojiPanel.appendChild(s);
});
$('#btnEmoji').addEventListener('click', e => { e.stopPropagation(); emojiPanel.classList.toggle('open'); });
document.addEventListener('click', () => emojiPanel.classList.remove('open'));

$('#btnClear').addEventListener('click', () => {
  box.style.opacity = '0';
  setTimeout(() => {
    const room = getCurrentRoom();
    if (room) room.history = [];
    showEmpty();
    box.style.opacity = '1';
    sys('屏幕已被清空，什么都没发生过。', 'info');
  }, 180);
});

$('#btnNotify').addEventListener('click', async function () {
  if (!notifyOn) {
    const ok = await ensureNotifyPermission();
    if (!ok) { alert('请在浏览器设置中允许通知'); return; }
    notifyOn = true;
  } else notifyOn = false;
  this.textContent = notifyOn ? '📢' : '🚫';
  this.classList.toggle('muted', !notifyOn);
  if (notifyOn) desktopNotify('LAN·TALK', '桌面通知已开启');
});

function roll(btn, inputEl) {
  btn.classList.remove('spin'); void btn.offsetWidth; btn.classList.add('spin');
  let i = 0;
  const iv = setInterval(() => {
    inputEl.value = randomName();
    if (++i >= 7) clearInterval(iv);
  }, 60);
}
$('#diceJoin').addEventListener('click', function () { roll(this, nickInp); });
$('#diceSet').addEventListener('click', function () { roll(this, $('#setNick')); });

/* ── 私密群 ── */
let pendingInvite = null;

function handleInvite(data) {
  if (!data || data.type !== 'invite' || !data.roomId) return;
  if (rooms.has(data.roomId)) return;
  pendingInvite = data;
  const memNames = (data.members || []).map(m => m.name).filter(Boolean).join('、');
  $('#inviteTxt').textContent = `${data.from} 邀请你加入「${data.roomName || '私密群'}」` +
    (memNames ? `\n成员：${memNames}` : '');
  $('#invitePass').value = data.passwordHint || '';
  $('#invitePop').classList.add('open');
  desktopNotify('私密群邀请', data.from + ' 邀请你加入 ' + (data.roomName || '私密群'));
}

$('#inviteAccept').addEventListener('click', () => {
  if (!pendingInvite) return;
  const pass = $('#invitePass').value.trim() || pendingInvite.passwordHint || DEFAULT_PASS;
  const members = pendingInvite.members || [
    { id: pendingInvite.fromId, name: pendingInvite.from },
    { id: myId, name: myName }
  ];
  if (!members.some(m => m.id === myId)) members.push({ id: myId, name: myName });
  joinPrivateRoom(pendingInvite.roomId, pendingInvite.roomName || '私密群', pass, members, true);
  const room = rooms.get(pendingInvite.roomId);
  if (room) {
    publish(room.topic, { type: 'join', id: myId, from: myName, ts: Date.now() });
    publish(room.topic, { type: 'members', members: room.members, ts: Date.now() });
  }
  pendingInvite = null;
  $('#invitePop').classList.remove('open');
});
$('#inviteReject').addEventListener('click', () => {
  pendingInvite = null;
  $('#invitePop').classList.remove('open');
});

function joinPrivateRoom(roomId, name, password, members, switchTo) {
  const topic = roomTopic(roomId);
  const list = (members || []).map(m => ({ id: m.id, name: m.name || '???' }));
  if (!list.some(m => m.id === myId) && myName) list.push({ id: myId, name: myName });
  rooms.set(roomId, {
    id: roomId, name, topic, password,
    history: [], unread: 0, private: true, members: list
  });
  if (client && connected) client.subscribe(topic, { qos: 1 });
  renderRoomList();
  if (switchTo) {
    switchRoom(roomId);
    sys('已加入私密频道「' + name + '」· 共 ' + list.length + ' 人', 'in');
  }
}

function openNewRoomPop() {
  const ids = [...selectedPeers];
  if (!ids.length) {
    alert('请先在右侧在线名单勾选至少一位用户');
    return;
  }
  const names = ids.map(id => peers.get(id)?.name || id).join('、');
  $('#newRoomTip').textContent = '将邀请：' + names;
  $('#newRoomName').value = '私密·' + (myName || '群').slice(0, 6);
  $('#roomPassInp').value = Math.random().toString(36).slice(2, 10);
  $('#newRoomPop').classList.add('open');
}
$('#btnCreateRoom').addEventListener('click', openNewRoomPop);
$('#newRoomCancel').addEventListener('click', () => $('#newRoomPop').classList.remove('open'));

$('#newRoomOk').addEventListener('click', () => {
  const ids = [...selectedPeers];
  if (!ids.length) { alert('请勾选用户'); return; }
  const roomId = 'r_' + Math.random().toString(36).slice(2, 12);
  const roomName = ($('#newRoomName').value.trim() || '私密群').slice(0, 20);
  const password = $('#roomPassInp').value.trim() || Math.random().toString(36).slice(2, 10);

  const members = [{ id: myId, name: myName }];
  ids.forEach(tid => {
    const p = peers.get(tid);
    members.push({ id: tid, name: p ? p.name : tid });
  });

  joinPrivateRoom(roomId, roomName, password, members, true);

  ids.forEach(tid => {
    publish(`${TOPIC_INVITE}/${tid}`, {
      type: 'invite',
      roomId,
      roomName,
      from: myName,
      fromId: myId,
      passwordHint: password,
      members,
      ts: Date.now()
    });
  });

  const room = rooms.get(roomId);
  if (room) publish(room.topic, { type: 'members', members, ts: Date.now() });

  selectedPeers.clear();
  renderUsers();
  $('#newRoomPop').classList.remove('open');
  sys('已创建「' + roomName + '」· 成员 ' + members.map(m => m.name).join('、'), 'info');
});

/* ── 加入 / 设置 / 诊断 ── */
function join(name, pass) {
  myName = (name || '').trim().slice(0, 16) || randomName();
  const roomPass = (pass || $('#joinPass')?.value || DEFAULT_PASS).trim() || DEFAULT_PASS;
  sessionStorage.setItem('nick', myName);
  sessionStorage.setItem('publicPass', roomPass);
  ensurePublicRoom(roomPass);
  currentRoomId = PUBLIC_ROOM;
  overlay.classList.add('hide');
  inp.placeholder = '以 ' + myName + ' 的身份说点什么…';
  connectMqtt();
  renderUsers();
  renderRoomList();
  showEmpty();
  sys('欢迎你，' + myName + '。消息已 AES 加密，刷新即焚。', 'in');
  ensureNotifyPermission();
  inp.focus();
}
$('#btnJoin').addEventListener('click', () => join(nickInp.value, $('#joinPass').value));
nickInp.addEventListener('keydown', e => { if (e.key === 'Enter') join(nickInp.value, $('#joinPass').value); });

$('#btnSet').addEventListener('click', e => {
  e.stopPropagation();
  diag.classList.remove('open');
  $('#invitePop').classList.remove('open');
  $('#newRoomPop').classList.remove('open');
  $('#setNick').value = myName;
  $('#setMqtt').value = getMqttUrl();
  const cur = getCurrentRoom();
  $('#setPass').value = cur ? cur.password : '';
  pop.classList.toggle('open');
});
$('#btnDiag').addEventListener('click', e => {
  e.stopPropagation();
  pop.classList.remove('open');
  $('#diagUrl').value = getMqttUrl();
  diag.classList.toggle('open');
});
document.addEventListener('click', e => {
  if (pop.classList.contains('open') && !pop.contains(e.target) && e.target.id !== 'btnSet') pop.classList.remove('open');
  if (diag.classList.contains('open') && !diag.contains(e.target) && e.target.id !== 'btnDiag') diag.classList.remove('open');
});
$('#setSave').addEventListener('click', () => {
  const nv = $('#setNick').value.trim().slice(0, 16);
  const url = $('#setMqtt').value.trim();
  const pass = $('#setPass').value.trim();
  if (nv && nv !== myName) {
    myName = nv;
    sessionStorage.setItem('nick', myName);
    publishPresence('online');
    for (const r of rooms.values()) {
      if (r.members) {
        const m = r.members.find(x => x.id === myId);
        if (m) m.name = myName;
      }
    }
    renderUsers();
    sys('你现在叫「' + nv + '」了', 'info');
  }
  if (pass) {
    const cur = getCurrentRoom();
    if (cur) {
      cur.password = pass;
      if (cur.id === PUBLIC_ROOM) sessionStorage.setItem('publicPass', pass);
      sys('当前频道口令已更新', 'info');
    }
  }
  if (url) {
    sessionStorage.setItem('mqttUrl', url);
    connectMqtt();
  }
  pop.classList.remove('open');
});

let diagClient = null, diagTimer = null;
function diagLog(msg, cls) {
  const d = new Date();
  const p = n => String(n).padStart(2, '0');
  const s = document.createElement('span');
  s.className = cls || 'dim';
  s.textContent = `[${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}] ${msg}\n`;
  $('#diagLog').appendChild(s);
  $('#diagLog').scrollTop = $('#diagLog').scrollHeight;
}
$('#btnRunDiag').addEventListener('click', () => {
  try { diagClient && diagClient.end(true); } catch (e) {}
  clearTimeout(diagTimer);
  $('#diagLog').innerHTML = '';
  const url = $('#diagUrl').value.trim();
  const user = $('#diagUser').value || undefined;
  const pass = $('#diagPass').value || undefined;
  diagLog('目标: ' + url, 'info');
  if (!/^wss?:\/\//.test(url)) { diagLog('❌ 地址必须以 ws:// 或 wss:// 开头', 'bad'); return; }
  diagLog('① WebSocket 握手…', 'info');
  let ws1;
  try { ws1 = new WebSocket(url, 'mqtt'); } catch (e) { diagLog('❌ ' + e.message, 'bad'); return; }
  const t0 = Date.now();
  ws1.onopen = () => { diagLog('✅ 握手通过（' + (Date.now() - t0) + 'ms）', 'ok'); try { ws1.close(); } catch (e) {} };
  ws1.onerror = () => {};
  ws1.onclose = e => { if (!e.wasClean) diagLog('❌ 端口不通或无 ws 服务', 'bad'); };
  fetch(url.replace(/^ws/, 'http'), { mode: 'no-cors' }).then(() => diagLog('✅ HTTP 有应答', 'info')).catch(() => diagLog('❌ HTTP 无应答', 'bad'));
  diagLog('② MQTT CONNACK…', 'info');
  try {
    diagClient = mqtt.connect(url, {
      clientId: 'diag_' + Math.random().toString(36).slice(2, 8),
      clean: true, connectTimeout: 8000, reconnectPeriod: 0, username: user, password: pass
    });
  } catch (e) { diagLog('❌ ' + e.message, 'bad'); return; }
  diagClient.on('connect', () => { diagLog('✅ MQTT 连接成功', 'ok'); try { diagClient.end(); } catch (e) {} });
  diagClient.on('error', e => diagLog('⚠ ' + ((e && e.message) || e), 'bad'));
  diagClient.on('close', () => diagLog('连接已关闭', 'dim'));
  diagTimer = setTimeout(() => { diagLog('⏱ 10 秒未收到 CONNACK', 'bad'); try { diagClient.end(true); } catch (e) {} }, 10000);
});

window.addEventListener('beforeunload', () => { if (myName) publishPresence('offline'); });

ensurePublicRoom(sessionStorage.getItem('publicPass') || DEFAULT_PASS);
showEmpty();
updateStatus('closed');
renderRoomList();
nickInp.value = randomName();
$('#joinPass').value = sessionStorage.getItem('publicPass') || DEFAULT_PASS;
const saved = sessionStorage.getItem('nick');
if (saved) join(saved, sessionStorage.getItem('publicPass') || DEFAULT_PASS);
})();
</script>
</body>
</html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML.encode("utf-8"))
    def log_message(self, *a): pass

if __name__ == "__main__":
    print(f"[LAN·TALK] 启动成功，监听端口: {PORT}")
    ThreadingHTTPServer((os.environ.get("APP_HOST", "127.0.0.1"), PORT), H).serve_forever()