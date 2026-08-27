import sys, time
sys.path.insert(0, r"C:\Users\jun\Desktop\exe\web-launcher\apps\ros")
import shared_ros2 as r
sys.path.insert(0, r"C:\Users\jun\Desktop\exe\web-launcher\apps\ros\ros2-param")
import app

app.start_source()
time.sleep(8)
out, err, rc = r.run_cli(["node", "list"], timeout=30)
names = [n for n in out.splitlines() if "param_demo" in n]
print("nodes =", names)
if names:
    n = names[0]
    print("stale-or-node =", n)
    o, e, c = r.run_cli(["param", "list", n], timeout=30)
    print("param list rc=%r out=[%r] err=[%r]" % (c, o, e))
    o2, e2, c2 = r.run_cli(["param", "get", n, "int_param"], timeout=30)
    print("param get rc=%r out=[%r] err=[%r]" % (c2, o2, e2))
app.stop_source()
print("DONE")