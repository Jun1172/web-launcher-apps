import sys, time, subprocess
sys.path.insert(0, r"C:\Users\jun\Desktop\exe\web-launcher\apps\ros")
import shared_ros2 as r
sys.path.insert(0, r"C:\Users\jun\Desktop\exe\web-launcher\apps\ros\ros2-param")
import app

# 确保无残留
app.stop_source()
print("node list before:", r.run_cli(["node", "list"], timeout=30)[0])

app.start_source()
t = time.time()
while time.time() - t < 12:
    out, err, rc = r.run_cli(["topic", "list"], timeout=30, )  # keep daemon warm
    out, err, rc = r.run_cli(["node", "list"], timeout=30)
    nodes = [n for n in out.splitlines() if "param_demo" in n]
    if nodes:
        n = nodes[0]
        stdout, stderr, rcc = r.run_cli(["param", "list", n], timeout=20)
        print("node=%s list_rc=%r stdout=%r stderr=%r" % (n, rcc, stdout, stderr))
    else:
        print("not discovered")
    time.sleep(0.5)
app.stop_source()
print("DONE")