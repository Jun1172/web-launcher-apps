"""动作数据源：内置动作服务器。

注册动作 demo_fib（type: example_interfaces/action/Fibonacci），
计算斐波那契数列并周期性发布 feedback，可在「动作教程」里 send_goal 测试（闭环）。
"""
import time
import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer, GoalResponse, CancelResponse
from example_interfaces.action import Fibonacci


def main():
    rclpy.init()
    node = Node("action_demo_server")

    def goal_cb(goal_handle):
        return GoalResponse.ACCEPT

    def cancel_cb(goal_handle):
        return CancelResponse.ACCEPT

    def execute_cb(goal_handle):
        request = goal_handle.request
        order = max(0, request.order)
        node.get_logger().info(f"received goal order={order}")
        seq = [0, 1]
        for i in range(1, order):
            seq.append(seq[-2] + seq[-1])
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                return Fibonacci.Result(sequence=seq)
            fb = Fibonacci.Feedback()
            fb.sequence = list(seq)
            goal_handle.publish_feedback(fb)
            time.sleep(0.5)
        goal_handle.succeed()
        res = Fibonacci.Result()
        res.sequence = list(seq)
        node.get_logger().info(f"goal done sequence={res.sequence}")
        return res

    ActionServer(node, Fibonacci, "demo_fib", execute_callback=execute_cb,
                 goal_callback=goal_cb, cancel_callback=cancel_cb)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()