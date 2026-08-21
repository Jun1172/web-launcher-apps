"""ros2-tf-viewer —— 坐标变换可视化"""
import json, os, subprocess, re
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

import threading

_tf_error = ""
_rclpy_ok = False

# === 优先用 rclpy + tf2_ros 直接读 TF buffer (零延迟，无需解析子进程输出) ===
try:
    import rclpy
    from rclpy.node import Node
    from tf2_ros import TransformListener, Buffer
    try:
        rclpy.init()
        _tf_node = rclpy.create_node("web_tf_viewer")
        _tf_buffer = Buffer()
        _tf_listener = TransformListener(_tf_buffer, _tf_node)
        threading.Thread(target=lambda: rclpy.spin(_tf_node), daemon=True).start()
        _rclpy_ok = True
    except Exception as _e:
        _tf_error = f"rclpy/tf2 init failed: {_e}"

except (ImportError, Exception):
    _tf_error = "rclpy or tf2_ros not available, using subprocess fallback"


def get_frames():
    """获取所有坐标系名。rclpy 直读 TF buffer；回退用 ros2 topic echo。"""
    if _rclpy_ok:
        try:
            import time as _t
            _t.sleep(0.3)  # 给 listener 时间接收 /tf
            yaml_str = _tf_buffer.all_frames_as_yaml()
            frames = set()
            for line in yaml_str.split("\n"):
                line = line.strip()
                if line.endswith(":"):
                    frames.add(line[:-1].strip())
                elif line.startswith("- "):
                    frames.add(line[2:].strip())
            return sorted(frames)
        except Exception:
            return []

    # 回退: ros2 topic echo
    frames = set()
    for topic in ["/tf", "/tf_static"]:
        try:
            res = subprocess.run(
                f"ros2 topic echo {topic} --once",
                shell=True, capture_output=True, text=True, timeout=5,
            )
            for m in re.finditer(r"child_frame_id:\s*(\S+)", res.stdout):
                frames.add(m.group(1).strip("'\""))
            for m in re.finditer(r"(?<!child_)frame_id:\s*(\S+)", res.stdout):
                frames.add(m.group(1).strip("'\""))
        except Exception:
            pass
    return sorted(frames)


def get_tf_echo(parent, child):
    """获取 parent->child 变换。rclpy lookup_transform；回退用 tf2_echo 子进程。"""
    if _rclpy_ok:
        try:
            from rclpy.time import Time
            trans = _tf_buffer.lookup_transform(parent, child, Time())
            t = trans.transform.translation
            r = trans.transform.rotation
            return {
                "raw": f"Translation: [{t.x}, {t.y}, {t.z}]\n"
                       f"Rotation: in Quaternion [{r.x}, {r.y}, {r.z}, {r.w}]",
                "translation": f"[{t.x}, {t.y}, {t.z}]",
                "quaternion": f"[{r.x}, {r.y}, {r.z}, {r.w}]",
            }
        except Exception as e:
            return {"raw": str(e), "translation": "", "quaternion": ""}

    # 回退: tf2_echo 子进程
    try:
        cmd = f"ros2 run tf2_ros tf2_echo {parent} {child}"
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            out, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
        out = (out or "").strip()
        trans = re.search(r"Translation:\s*\[^\]]*\]", out)
        rot = re.search(r"Rotation: in Quaternion \[^\]]*\]", out)
        return {
            "raw": out[-800:],
            "translation": trans.group(0) if trans else "",
            "quaternion": rot.group(0) if rot else "",
        }
    except Exception as e:
        return {"raw": str(e), "translation": "", "quaternion": ""}

HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body{margin:0;background:#ecfeff;font-family:system-ui}
.container{max-width:700px;margin:20px auto;padding:20px}
h2{color:#164e63}
.card{background:#fff;border-radius:12px;padding:20px;box-shadow:0 4px 6px rgba(0,0,0,0.1);margin-bottom:20px}
label{display:block;margin-bottom:5px;color:#155e75;font-weight:bold}
select{width:100%;padding:8px;border:1px solid #a5f3fc;border-radius:6px;margin-bottom:15px;box-sizing:border-box}
.data{background:#f0f9ff;padding:15px;border-radius:6px;font-family:monospace;font-size:14px}
.data div{margin-bottom:8px}
.label{color:#0369a1;font-weight:bold;display:inline-block;width:100px}
.tip{background:#fffbeb;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:13px;line-height:1.7;color:#78350f}
.tip code{background:#fef3c7;padding:2px 6px;border-radius:4px;font-family:monospace;color:#92400e}
.tip a{color:#2563eb;text-decoration:none}
.tip a:hover{text-decoration:underline}
</style>
</head>
<body>
<div class="container">
  <h2>📐 TF 坐标变换查看器</h2>
  <div class="tip"><strong>💡 使用提示：</strong>没有坐标系数据？请打开 <a href="http://127.0.0.1:8200/" target="_blank">ROS2 演示节点</a> 启动「TF 发布器」，它会自动发布坐标变换供本页面读取。</div>
  <div class="card">
    <label>父坐标系 (Parent Frame)</label>
    <select id="parent"><option>加载中...</option></select>
    <label>子坐标系 (Child Frame)</label>
    <select id="child"><option>加载中...</option></select>
    <button onclick="update()" style="padding:10px 20px;background:#06b6d4;color:#fff;border:none;border-radius:6px;cursor:pointer;font-weight:bold">刷新</button>
  </div>
  <div id="diag" style="padding:8px 12px;background:#f0f9ff;border-radius:6px;font-size:12px;color:#155e75;margin-bottom:12px"></div>
  <div class="card">
    <h3>实时变换数据</h3>
    <div class="data" id="data">
      <div><span class="label">Translation:</span> <span id="trans">-</span></div>
      <div><span class="label">Quaternion:</span> <span id="quat">-</span></div>
      <div style="margin-top:15px;border-top:1px solid #e0f2fe;padding-top:10px"><span class="label">Raw:</span> <span id="raw">-</span></div>
    </div>
  </div>
</div>
<script>
var updating=false;
function loadFrames(){
  fetch('/api/frames').then(function(r){return r.json()}).then(function(data){
    var opts='';
    for(var i=0;i<data.length;i++){
      opts+='<option value="'+data[i]+'">'+data[i]+'</option>';
    }
    document.getElementById('parent').innerHTML=opts||'<option>无数据</option>';
    document.getElementById('child').innerHTML=opts||'<option>无数据</option>';
  }).catch(function(e){console.log('loadFrames error:',e)});
}
function update(){
  if(updating)return;
  var p=document.getElementById('parent').value;
  var c=document.getElementById('child').value;
  if(!p||!c||p==='无数据'||c==='无数据')return;
  updating=true;
  fetch('/api/echo?parent='+encodeURIComponent(p)+'&child='+encodeURIComponent(c))
    .then(function(r){return r.json()})
    .then(function(data){
      document.getElementById('trans').textContent=data.translation||'计算中...';
      document.getElementById('quat').textContent=data.quaternion||'计算中...';
      document.getElementById('raw').textContent=data.raw||'无数据';
      updating=false;
    })
    .catch(function(e){console.log('update error:',e);updating=false});
}
function loadDiag(){
  fetch('/api/tf_status').then(function(r){return r.json()}).then(function(d){
    var el=document.getElementById('diag');
    if(d.rclpy){
      el.innerHTML='<span style="color:#10b981">\u2713 rclpy + tf2_ros \u76f4\u8fde\u5df2\u5c31\u7eea</span>';
    }else if(d.error){
      el.innerHTML='<span style="color:#f59e0b">\u26a0 '+d.error+'</span>';
    }
  }).catch(function(){});
}
loadFrames();
loadDiag();
setInterval(loadFrames,3000);
setInterval(update,1000);
setInterval(loadDiag,3000);
</script>
</body>
</html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/tf_status':
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(
                {"rclpy": _rclpy_ok, "error": _tf_error},
                ensure_ascii=False
            ).encode("utf-8"))
        elif parsed.path == '/api/frames':
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(get_frames()).encode())
        elif parsed.path.startswith('/api/echo'):
            qs = parse_qs(parsed.query)
            p = qs.get('parent', [''])[0]
            c = qs.get('child', [''])[0]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(get_tf_echo(p, c)).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
    def log_message(self, *a): pass

if __name__ == "__main__":
    print(f"[ROS2 TF Viewer] 启动成功，监听端口: {PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()