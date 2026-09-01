"""ip-scanner —— 局域网存活 IP 扫描"""
import json, os, subprocess, platform
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor

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

def get_hostname(ip):
    if platform.system().lower() == 'windows':
        try:
            res = subprocess.run(['nbtstat', '-A', ip], capture_output=True, text=True, encoding='gbk', errors='ignore', timeout=2)
            for line in res.stdout.splitlines():
                if '<00>  UNIQUE' in line:
                    return line.split()[0].strip()
        except: pass
    else:
        try:
            res = subprocess.run(['host', ip], capture_output=True, text=True, timeout=2)
            if 'domain name pointer' in res.stdout:
                return res.stdout.split()[-1].rstrip('.')
        except: pass
    return ""

def ping_ip(ip):
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    cmd = ['ping', param, '1', ip]
    if platform.system().lower() == 'windows':
        cmd.extend(['-w', '1000'])
    else:
        cmd.extend(['-W', '1'])
    try:
        encoding = 'gbk' if platform.system().lower() == 'windows' else 'utf-8'
        res = subprocess.run(cmd, capture_output=True, text=True, encoding=encoding, errors='ignore')
        if res.returncode == 0:
            return {"ip": ip, "hostname": get_hostname(ip)}
    except: pass
    return None

def scan_subnet(subnet):
    ips = [f"{subnet}.{i}" for i in range(1, 255)]
    with ThreadPoolExecutor(max_workers=50) as executor:
        results = executor.map(ping_ip, ips)
    return [r for r in results if r]

HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body{margin:0;height:100vh;display:flex;justify-content:center;align-items:center;background:#f5f3ff;font-family:system-ui}
.box{width:550px;background:#fff;border-radius:16px;box-shadow:0 10px 30px rgba(0,0,0,.1);padding:20px}
h3{margin:0 0 15px;color:#5b21b6}
input{padding:10px;border:1px solid #ddd6fe;border-radius:8px;width:calc(100% - 90px);box-sizing:border-box}
button{padding:10px;background:#8b5cf6;color:#fff;border:none;border-radius:8px;cursor:pointer;font-weight:bold}
table{width:100%;border-collapse:collapse;margin-top:15px;font-size:14px}
th,td{padding:8px;text-align:left;border-bottom:1px solid #ede9fe}
th{background:#f5f3ff; color: #5b21b6;}
</style>
</head>
<body>
<div class="box">
  <h3>🌐 局域网 IP 扫描</h3>
  <input id="subnet" value="192.168.1" placeholder="输入网段，如 192.168.1">
  <button onclick="scan()">扫描</button>
  <table>
    <thead><tr><th>IP 地址</th><th>设备名称</th></tr></thead>
    <tbody id="list"><tr><td colspan="2">等待扫描...</td></tr></tbody>
  </table>
</div>
<script>
async function scan(){
  list.innerHTML='<tr><td colspan="2">扫描中，请稍候...</td></tr>';
  const res=await fetch('/api/scan?subnet='+encodeURIComponent(subnet.value));
  const data=await res.json();
  list.innerHTML=data.length?data.map(r=>`<tr><td>${r.ip}</td><td>${r.hostname || '未知设备'}</td></tr>`).join(''):'<tr><td colspan="2">未发现存活主机</td></tr>';
}
</script>
</body>
</html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/scan':
            qs = parse_qs(parsed.query)
            subnet = qs.get('subnet', ['192.168.1'])[0]
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(scan_subnet(subnet), ensure_ascii=False).encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
    def log_message(self, *a): pass

if __name__ == "__main__":
    print(f"[IP Scanner] 启动成功，监听端口: {PORT}")
    ThreadingHTTPServer((os.environ.get("APP_HOST", "127.0.0.1"), PORT), H).serve_forever()