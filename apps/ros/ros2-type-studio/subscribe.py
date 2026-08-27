"""通用话题订阅器（rclpy），供 ros2-type-studio 的"波形/消息查看"以子进程方式调用。

行为：
- 订阅任意类型话题（SUB_TOPIC / SUB_TYPE），把每条消息通过 stdout 打两行：
    RAW\t<json>   整条消息 JSON（供"原始消息回显"）
    SUM\t<json>   含 [t, {path,type,value|values}] 数值字段摘要（供曲线）
- 自动递归扫描消息里的标量数值与一维数值数组，输出数值路径供前端选通道画图。
- 为隔离 stdout，rclpy 日志默认写 stderr（用 RCUTILS_LOGGING_USE_STDOUT=0 环境变量可强制）。

环境变量：SUB_TOPIC 话题名；SUB_TYPE 消息类型（如 std_msgs/String）。
"""
import os
import sys
import json
import importlib
import time
import rclpy
from rclpy.node import Node

_NUM = (int, float)


def resolve_type(mtype):
    """'std_msgs/String' 或 'std_msgs/msg/String' -> 消息类型类（兼容两种写法）。"""
    parts = [p for p in mtype.split("/") if p]
    if len(parts) == 3:
        pkg, interface, cls = parts
        mod = importlib.import_module(f"{pkg}.{interface.lower()}")
    else:
        pkg = parts[-2] if len(parts) >= 2 else "std_msgs"
        cls = parts[-1]
        mod = importlib.import_module(f"{pkg}.msg")
    return getattr(mod, cls)


def _to_json(v):
    """递归把 rclpy 消息（含嵌套、数组、uint8 数组）转成可 JSON 序列化对象。"""
    import array
    if v is None:
        return None
    if isinstance(v, (bool, str, _NUM)):
        return v
    if isinstance(v, (array.array, list, tuple)):
        return [_to_json(x) for x in v]
    names = None
    if hasattr(v, "__slots__") and v.__slots__:
        names = [s[1:] if s.startswith("_") else s for s in v.__slots__]
    elif hasattr(v, "_fields"):
        names = v._fields
    if names:
        out = {}
        for n in names:
            try:
                out[n] = _to_json(getattr(v, n))
            except Exception:
                out[n] = None
        return out
    try:
        return str(v)
    except Exception:
        return None


def _paths(msg, prefix, out, limit=10):
    """递归提取数值通道：标量 -> {path,type:scalar}；一维数值数组 -> {path,type:series}。"""
    import array
    if len(out) >= limit:
        return
    if isinstance(msg, (array.array, list, tuple)):
        vals = [float(x) for x in msg if isinstance(x, _NUM)]
        if vals:
            out.append({"path": prefix, "type": "series", "len": len(vals),
                        "head": vals[:200]})
        return
    if isinstance(msg, _NUM) and not isinstance(msg, bool):
        out.append({"path": prefix, "type": "scalar", "value": float(msg)})
        return
    names = getattr(msg, "__slots__", None) or getattr(msg, "_fields", None)
    if names:
        for n in names:
            public = n[1:] if n.startswith("_") else n
            if len(out) >= limit:
                break
            try:
                v = getattr(msg, public)
            except Exception:
                continue
            _paths(v, (prefix + "/" + public) if prefix else public, out, limit)


def main():
    topic = os.environ.get("SUB_TOPIC", "")
    mtype = os.environ.get("SUB_TYPE", "std_msgs/String")
    if not topic:
        print(json.dumps({"error": "SUB_TOPIC 未设置"}), file=sys.stderr)
        return

    def on_msg(msg):
        try:
            obj = _to_json(msg)
            np = []
            _paths(msg, "", np)
            print("RAW\t" + json.dumps(obj, ensure_ascii=False), flush=True)
            print("SUM\t" + json.dumps({"t": time.time(), "paths": np},
                                       ensure_ascii=False), flush=True)
        except Exception as e:
            print("ERR\t" + json.dumps({"error": str(e)}), flush=True)

    rclpy.init()
    node = Node("plot_subscriber")
    try:
        msg_cls = resolve_type(mtype)
    except Exception as e:
        print("ERR\t" + json.dumps({"error": f"类型解析失败: {mtype}: {e}"}),
              flush=True)
        rclpy.try_shutdown()
        return
    node.create_subscription(msg_cls, topic, on_msg, 10)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()