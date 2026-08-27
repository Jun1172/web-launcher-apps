"""动作客户端：向内置动作服务器发送目标并流式回传 JSON 事件。

环境变量传参（避免 shell 引号问题）：
  ACTION_NAME  动作名            默认 demo_fib
  ACTION_TYPE  动作类型          默认 example_interfaces/action/Fibonacci
  GOAL_JSON    目标负载 JSON     默认 {"order": 8}

stdout 按行输出 JSON 事件：
  {"type":"sending","goal":{}}
  {"type":"feedback","data":"..."}
  {"type":"accepted","id":"..."}
  {"type":"result","status":"SUCCEEDED","data":"..."}
  {"type":"rejected"/"aborted"/"cancelled"/"error","msg":"..."}
"""
import os
import json
import importlib
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.executors import SingleThreadedExecutor


def resolve_action_type(atype):
    cls = atype.rpartition("/")[2]
    pkg = atype.rsplit("/", 1)[0].replace("/", ".")
    mod = importlib.import_module(pkg)
    return getattr(mod, cls)


def main():
    aname = os.environ.get("ACTION_NAME", "demo_fib")
    atype = os.environ.get("ACTION_TYPE", "example_interfaces/action/Fibonacci")
    try:
        goal_data = json.loads(os.environ.get("GOAL_JSON", '{"order": 8}'))
    except json.JSONDecodeError:
        goal_data = {"order": 8}

    rclpy.init()
    node = Node("action_demo_client")
    ActionType = resolve_action_type(atype)
    client = ActionClient(node, ActionType, aname)

    if not client.wait_for_server(timeout_sec=8.0):
        print(json.dumps({"type": "error", "msg": "未找到动作服务器"}), flush=True)
        return

    goal = ActionType.Goal()
    for k, v in goal_data.items():
        try:
            setattr(goal, k, v)
        except Exception:
            pass
    print(json.dumps({"type": "sending", "goal": goal_data}), flush=True)

    done = [False]

    def fb_cb(fb_msg):
        print(json.dumps({"type": "feedback", "data": str(fb_msg.feedback)},
                         ensure_ascii=False), flush=True)

    def result_cb(future):
        res = future.result()
        print(json.dumps({
            "type": "result",
            "status": str(getattr(res, "status", "")),
            "data": str(getattr(res, "result", "")),
        }, ensure_ascii=False), flush=True)
        done[0] = True

    def goal_response_cb(future):
        gfh = future.result()
        if not gfh.accepted:
            print(json.dumps({"type": "rejected", "msg": "goal rejected"}),
                  flush=True)
            done[0] = True
            return
        print(json.dumps({"type": "accepted", "id": str(gfh.goal_id)}),
              flush=True)
        res_future = gfh.get_result_async()
        res_future.add_done_callback(result_cb)

    send_future = client.send_goal_async(goal, feedback_callback=fb_cb)
    send_future.add_done_callback(goal_response_cb)

    executor = SingleThreadedExecutor()
    executor.add_node(node)
    try:
        while rclpy.ok() and not done[0]:
            executor.spin_once(timeout_sec=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()