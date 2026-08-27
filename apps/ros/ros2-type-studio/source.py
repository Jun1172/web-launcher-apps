"""类型模板库发布器（rclpy）：按模板/自定义 JSON 发布任意类型消息。

相比话题教程的 source.py，这里把 `$i` 占位替换增强为**递归**：嵌套字段
（如 Twist 的 linear/x）里的 "$i" 也会随每次发布递增，便于做波形演示。

环境变量：
  PUB_TOPIC    话题名
  PUB_TYPE     消息类型，如 geometry_msgs/Twist
  PUB_RATE     发布频率 Hz
  PUB_PAYLOAD  目标负载 JSON（可为任意嵌套结构）
  PUB_COUNT    发布次数，0=无限
"""
import os
import json
import importlib
import rclpy
from rclpy.node import Node


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


def _replace_counter(obj, i):
    """递归把字符串里的 '$i' 替换为当前计数 i。"""
    if isinstance(obj, str):
        return obj.replace("$i", str(i)) if "$i" in obj else obj
    if isinstance(obj, list):
        return [_replace_counter(x, i) for x in obj]
    if isinstance(obj, dict):
        return {k: _replace_counter(v, i) for k, v in obj.items()}
    return obj


def _coerce(cur, v):
    """让赋值尽量适配目标字段类型：数值/布尔字段收到字符串时尝试转换。"""
    if isinstance(cur, bool):
        try:
            return v if isinstance(v, bool) else str(v).lower() in ("true", "1", "t")
        except Exception:
            return v
    if isinstance(cur, (int, float)):
        try:
            return float(v) if isinstance(cur, float) else int(v)
        except Exception:
            try:
                return float(v)
            except Exception:
                return v
    return v


def _set(msg, data):
    """按 JSON 递归给消息字段赋值（支持嵌套，忽略无法赋值的字段）。"""
    for k, v in data.items():
        try:
            cur = getattr(msg, k)
            if isinstance(v, dict):
                _set(cur, v)
            else:
                setattr(msg, k, _coerce(cur, v))
        except Exception:
            pass


def main():
    rclpy.init()
    node = Node("type_studio_publisher")
    topic = os.environ.get("PUB_TOPIC", "/type_demo")
    mtype = os.environ.get("PUB_TYPE", "std_msgs/String")
    try:
        rate = float(os.environ.get("PUB_RATE", "1"))
    except ValueError:
        rate = 1.0
    try:
        count = int(os.environ.get("PUB_COUNT", "0"))
    except ValueError:
        count = 0
    try:
        payload = json.loads(os.environ.get("PUB_PAYLOAD", "{}"))
    except json.JSONDecodeError:
        payload = {}

    msg_cls = resolve_type(mtype)
    pub = node.create_publisher(msg_cls, topic, 10)
    counter = [0]

    def tick():
        msg = msg_cls()
        _set(msg, _replace_counter(dict(payload), counter[0]))
        pub.publish(msg)
        counter[0] += 1

    interval = (1.0 / rate) if rate > 0 else 1.0
    node.create_timer(interval, tick)

    def check_done():
        if count > 0 and counter[0] >= count:
            node.get_logger().info("reach PUB_COUNT, shutting down")
            raise SystemExit(0)
    if count > 0:
        node.create_timer(0.5, check_done)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except SystemExit:
        pass


if __name__ == "__main__":
    main()