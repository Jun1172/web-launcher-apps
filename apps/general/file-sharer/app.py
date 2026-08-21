import os
import socket
import json
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler

PORT = 8150
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "shared_files")

# 确保上传目录存在
os.makedirs(UPLOAD_DIR, exist_ok=True)

def get_local_ip():
    """获取本机局域网 IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

class FileSharerHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # 将根目录指向当前脚本所在目录，以便提供 index.html
        super().__init__(*args, directory=os.path.dirname(__file__), **kwargs)

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            # 注入当前局域网 IP 到前端
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            with open(os.path.join(os.path.dirname(__file__), 'index.html'), 'r', encoding='utf-8') as f:
                html = f.read().replace('__LOCAL_IP__', get_local_ip()).replace('__PORT__', str(PORT))
                self.wfile.write(html.encode('utf-8'))
        elif self.path.startswith('/api/files'):
            # 提供已共享文件列表
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            files = os.listdir(UPLOAD_DIR)
            file_list = [{"name": f, "size": os.path.getsize(os.path.join(UPLOAD_DIR, f))} for f in files if os.path.isfile(os.path.join(UPLOAD_DIR, f))]
            self.wfile.write(json.dumps(file_list).encode('utf-8'))
        else:
            # 默认处理静态文件下载 (从 shared_files 目录)
            self.path = '/shared_files' + self.path
            super().do_GET()

    def do_POST(self):
        if self.path == '/api/upload':
            content_length = int(self.headers['Content-Length'])
            # 获取文件名 (从 header 或 query 中，这里简化为从 query 获取: /api/upload?filename=xxx)
            parsed_path = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed_path.query)
            filename = query.get('filename', ['unknown_file'])[0]
            
            # 简单安全的文件名处理
            filename = os.path.basename(filename).replace(' ', '_')
            filepath = os.path.join(UPLOAD_DIR, filename)
            
            # 写入文件
            with open(filepath, 'wb') as f:
                f.write(self.rfile.read(content_length))
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success", "filename": filename}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == '__main__':
    ip = get_local_ip()
    print(f"🚀 局域网快传已启动！")
    print(f"📱 手机访问: http://{ip}:{PORT}")
    print(f"💾 文件保存至: {UPLOAD_DIR}")
    server = HTTPServer(('0.0.0.0', PORT), FileSharerHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 服务已停止")
        server.server_close()