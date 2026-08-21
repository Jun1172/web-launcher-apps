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

def get_frames():
    """从 /tf 和 /tf_static 提取所有坐标系名。
    注意: 不能用 --no-arr，否则 transforms 数组被折叠，frame_id/child_frame_id 全部隐藏。
    """
    frames = set()
    for topic in ['/tf', '/tf_static']:
        try:
            res = subprocess.run(
                f"ros2 topic echo {topic} --once",
                shell=True, capture_output=True, text=True, timeout=3
            )
            # child_frame_id 必须先匹配 (它包含 frame_id 子串)
            for m in re.finditer(r'child_frame_id:\s*(\S+)', res.stdout):
                frames.add(m.group(1).strip("'\""))
            # 负向先行断言: 排除 child_frame_id
            for m in re.finditer(r'(?<!child_)frame_id:\s*(\S+)', res.stdout):
                frames.add(m.group(1).strip("'\""))
        except Exception:
            pass
    return sorted(frames)

def get_tf_echo(parent, child):
    try:
        cmd = f"ros2 run tf2_ros tf2_echo {parent} {child}"
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            out, _ = proc.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
        out = (out or "").strip()
        # Translation / Rotation 各自单独一行，必须在整个输出里搜索
        trans = re.search(r'Translation:\s*\[^\]]*\]', out)
        rot = re.search(r'Rotation: in Quaternion \[^\]]*\]', out)
        return {
            "raw": out[-800:],
            "translation": trans.group(0) if trans else "",
            "quaternion": rot.group(0) if rot else ""
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
async function loadFrames(){
  const res=await fetch('/api/frames');
  const data=await res.json();
  const opts=data.map(f=>`<option value="${f}">${f}</option>`).join('');
  document.getElementById('parent').innerHTML=opts||'<option>无数据</option>';
  document.getElementById('child').innerHTML=opts||'<option>无数据</option>';
}
async function update(){
  const p=document.getElementById('parent').value;
  const c=document.getElementById('child').value;
  if(!p||!c)return;
  const res=await fetch(`/api/echo?parent=${encodeURIComponent(p)}&child=${encodeURIComponent(c)}`);
  const data=await res.json();
  document.getElementById('trans').textContent=data.translation||'计算中...';
  document.getElementById('quat').textContent=data.quaternion||'计算中...';
  document.getElementById('raw').textContent=data.raw||'无数据';
}
loadFrames();
setInterval(loadFrames, 5000);
setInterval(update, 1000);
</script>
</body>
</html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/frames':
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