"""话题数据源：通用发布器（rclpy）。

以环境变量传参，避免 shell 引号转义问题：
  PUB_TOPIC    话题名          默认 /demo_talker
  PUB_TYPE     消息类型        默认 std_msgs/String
  PUB_RATE     发布频率 Hz     默认 1
  PUB_PAYLOAD  目标负载 JSON   字符串中出现的 $i 会随每次发布替换为递增整数
  PUB_COUNT    发布次数        默认 0 = 无限循环；>0 发布指定次数后自动退出
"""
import os
import json
import importlib
import rclpy
from rclpy.node import Node


def resolve_type(mtype):
    """'std_msgs/String' -> std_msgs.msg.String 类型类。"""
    pkg, _, cls = mtype.rpartition("/")
    mod = importlib.import_module(pkg.replace("/", ".") + ".msg")
    return getattr(mod, cls)


def _set(msg, data):
    """按 JSON 递归给消息字段赋值（支持嵌套，忽略无法赋值的字段）。"""
    for k, v in data.items():
        try:
            if isinstance(v, dict):
                _set(getattr(msg, k), v)
            else:
                setattr(msg, k, v)
        except Exception:
            pass


def main():
    rclpy.init()
    node = Node("topic_demo_publisher")
    topic = os.environ.get("PUB_TOPIC", "/demo_talker")
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
        data = dict(payload)
        # 支持 $i 整数占位替换
        for k, v in data.items():
            if isinstance(v, str) and "$i" in v:
                data[k] = v.replace("$i", str(counter[0]))
        msg = msg_cls()
        _set(msg, data)
        pub.publish(msg)
        counter[0] += 1
        node.get_logger().info(f"[{topic}] {data}")

    interval = (1.0 / rate) if rate > 0 else 1.0
    node.create_timer(interval, tick)

    # 按次数限制：结束 spin 需额外定时器/回调，简单起见到次数后关闭节点
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