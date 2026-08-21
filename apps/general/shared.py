import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def serve_page(page_path):
    page = Path(page_path).read_text(encoding="utf-8")
    env_port = os.environ.get("LAUNCHER_APP_PORT")
    port = int(env_port) if env_port and env_port.isdigit() else 0
    if not port:
        config = Path(page_path).with_name("app.json")
        try:
            port = int(json.loads(config.read_text(encoding="utf-8")).get("port", 0))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            port = 0

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(page.encode("utf-8"))

        def log_message(self, *_):
            pass

    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
