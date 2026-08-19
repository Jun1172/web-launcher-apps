"""mqtt-debug —— MQTT 调试工具（前后端分离 + 异常捕获修复版）"""
import json, time, threading, os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

try:
    import paho.mqtt.client as mqtt
    HAVE_MQTT = True
except ImportError:
    HAVE_MQTT = False

PORT = int(os.environ.get("LAUNCHER_APP_PORT", 0))

# 全局状态
state = {
    "client": None,
    "logs": [],
    "lock": threading.Lock(),
    "connected": False
}

def add_log(direction, msg):
    with state["lock"]:
        state["logs"].append({"t": time.strftime("%H:%M:%S"), "dir": direction, "msg": msg})
        if len(state["logs"]) > 200: state["logs"].pop(0)

# MQTT 回调函数
def on_connect(client, userdata, flags, rc):
    state["connected"] = True
    add_log("SYS", f"✅ Connected to broker (result code: {rc})")

def on_disconnect(client, userdata, rc):
    state["connected"] = False
    add_log("SYS", f"❌ Disconnected from broker (result code: {rc})")

def on_message(client, userdata, msg):
    payload_str = msg.payload.decode('utf-8', errors='replace')
    add_log("RX", f"[{msg.topic}] {payload_str}")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/status":
            with state["lock"]:
                logs_copy = list(state["logs"])
            self._json({
                "connected": state["connected"], 
                "have_mqtt": HAVE_MQTT, 
                "logs": logs_copy
            })
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))

    def do_POST(self):
        if not HAVE_MQTT:
            self._json({"ok": False, "err": "Missing paho-mqtt. Run: pip install paho-mqtt"})
            return

        path = urlparse(self.path).path
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length).decode('utf-8'))
        except Exception:
            self._json({"ok": False, "err": "Invalid request"})
            return

        if path == "/api/connect":
            if state["client"]:
                try: state["client"].disconnect()
                except: pass
            state["client"] = mqtt.Client()
            state["client"].on_connect = on_connect
            state["client"].on_disconnect = on_disconnect
            state["client"].on_message = on_message
            try:
                state["client"].connect(body.get("host", "broker.emqx.io"), body.get("port", 1883), 60)
                state["client"].loop_start()
                self._json({"ok": True})
            except Exception as e:
                self._json({"ok": False, "err": str(e)})
                
        elif path == "/api/disconnect":
            if state["client"]:
                try: state["client"].disconnect()
                except: pass
                state["client"] = None
            state["connected"] = False
            self._json({"ok": True})
            
        elif path == "/api/subscribe":
            if state["client"] and state["connected"]:
                topic = body.get("topic", "")
                state["client"].subscribe(topic)
                add_log("SYS", f"📥 Subscribed to: {topic}")
            self._json({"ok": True})
            
        elif path == "/api/publish":
            if state["client"] and state["connected"]:
                topic = body.get("topic", "")
                payload = body.get("payload", "")
                state["client"].publish(topic, payload)
                add_log("TX", f"[{topic}] {payload}")
            self._json({"ok": True})
            
        elif path == "/api/clear":
            with state["lock"]: state["logs"].clear()
            self._json({"ok": True})

    def _json(self, obj):
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            pass  # 优雅忽略客户端断开错误

    def log_message(self, *a): pass

HTML = r"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>MQTT 调试</title>
<style>
body{background:#0b1120;color:#f8fafc;font-family:system-ui;padding:20px;display:flex;gap:20px;height:100vh;box-sizing:border-box;
     background-image:radial-gradient(at 0% 0%,rgba(99,102,241,0.25) 0px,transparent 50%),radial-gradient(at 100% 100%,rgba(236,72,153,0.2) 0px,transparent 50%)}
.panel{flex:1;background:rgba(255,255,255,0.06);backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:20px;display:flex;flex-direction:column}
h2{font-size:16px;margin-bottom:16px;color:#f87171}
.row{display:flex;gap:10px;margin-bottom:12px}
input,button{background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.1);color:#fff;padding:8px 12px;border-radius:8px;font-size:13px}
button{cursor:pointer;background:#f87171;border:none}button:hover{background:#ef4444}
.log-area{flex:1;background:rgba(0,0,0,0.3);border-radius:8px;padding:10px;overflow-y:auto;font-family:Consolas,monospace;font-size:12px}
.log-item{margin-bottom:6px;padding:6px;border-radius:4px;background:rgba(255,255,255,0.03)}
.rx{border-left:3px solid #34d399}.tx{border-left:3px solid #fbbf24}.sys{border-left:3px solid #94a3b8}
</style></head><body>
<div class="panel">
  <h2>⚙️ Broker 配置</h2>
  <div class="row"><input id="host" value="broker.emqx.io" placeholder="Broker Host" style="flex:2"><input id="port" value="1883" placeholder="Port" style="flex:1"></div>
  <div class="row"><button onclick="connect()">连接</button><button onclick="disconnect()" style="background:#64748b">断开</button></div>
  <h2> 订阅 Topic</h2>
  <div class="row"><input id="subTopic" value="test/topic" style="flex:1"><button onclick="subscribe()">订阅</button></div>
  <h2>📤 发布消息</h2>
  <div class="row"><input id="pubTopic" value="test/topic" style="flex:1"></div>
  <div class="row"><input id="payload" placeholder="Payload" style="flex:1"><button onclick="publish()">发布</button></div>
</div>
<div class="panel">
  <h2>📋 消息日志 <span id="status" style="float:right;font-size:12px;color:#94a3b8">Disconnected</span> <button onclick="clearLog()" style="float:right;font-size:12px;padding:4px 8px;margin-right:10px">清空</button></h2>
  <div class="log-area" id="logs"></div>
</div>
<script>
async function api(url, data) { const r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data||{})}); return r.json(); }
async function connect() { await api('/api/connect', {host: document.getElementById('host').value, port: parseInt(document.getElementById('port').value)}); }
async function disconnect() { await api('/api/disconnect'); }
async function subscribe() { await api('/api/subscribe', {topic: document.getElementById('subTopic').value}); }
async function publish() { await api('/api/publish', {topic: document.getElementById('pubTopic').value, payload: document.getElementById('payload').value}); }
async function clearLog() { await api('/api/clear'); }
async function poll() {
  while(true) {
    try {
      const r = await fetch('/api/status');
      const d = await r.json();
      document.getElementById('status').textContent = d.connected ? "Connected" : "Disconnected";
      if(!d.have_mqtt) {
        document.getElementById('logs').innerHTML = '<div style="color:#f87171;padding:10px">Error: paho-mqtt not installed. Run: pip install paho-mqtt</div>';
      } else {
        document.getElementById('logs').innerHTML = d.logs.map(l => `<div class="log-item ${l.dir.toLowerCase()}"><b>[${l.t}] ${l.dir}</b> ${l.msg}</div>`).join('');
      }
    } catch(e) {}
    await new Promise(r=>setTimeout(r, 1000));
  }
}
poll();
</script></body></html>"""

if __name__ == "__main__":
    print(f"[MQTT Debug] http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()