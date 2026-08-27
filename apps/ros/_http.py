import sys, threading, time, json, urllib.request
os_env = None
sys.path.insert(0, r"C:\Users\jun\Desktop\exe\web-launcher\apps\ros")
import shared_ros2 as r
sys.path.insert(0, r"C:\Users\jun\Desktop\exe\web-launcher\apps\ros\ros2-param")
import app

# 避开 app.json 端口，用临时端口跑真实 HTTP 服务
import os
os.environ["LAUNCHER_APP_PORT"] = "18205"
import importlib
importlib.reload(app)
from http.server import ThreadingHTTPServer

PORT = 18205
srv = ThreadingHTTPServer(("127.0.0.1", PORT), app.H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

def call(path):
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (PORT, path), timeout=40) as resp:
        return json.loads(resp.read().decode("utf-8"))

print("env =", call("/api/env"))
print("nodes before =", call("/api/nodes"))

# 模拟前端点"启动参数节点"
print("toggle =", call("/api/psrc/toggle"))
time.sleep(5)
print("status =", call("/api/psrc/status"))
print("nodes after =", call("/api/nodes"))

# 模拟前端选 param_demo 加载参数
nodes = call("/api/nodes")
pd = [n for n in nodes if "param_demo" in n]
print("param_demo nodes =", pd)
if pd:
    n = pd[0]
    print("/api/params?node=%s ->" % n, call("/api/params?node=" + urllib.request.quote(n)))
    print("/api/get int_param ->", call("/api/get?node=%s&param=int_param" % urllib.request.quote(n)))

app.stop_source()
srv.shutdown()
print("DONE")