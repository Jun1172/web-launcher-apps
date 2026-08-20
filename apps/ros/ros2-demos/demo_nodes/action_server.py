#!/usr/bin/env python3
"""动作服务器 - 斐波那契数列生成"""
import rclpy
from rclpy.action import ActionServer, GoalResponse, CancelResponse
from rclpy.node import Node
from example_interfaces.action import Fibonacci

class ActionServerNode(Node):
    def __init__(self):
        super().__init__('action_server')
        self._action_server = ActionServer(
            self,
            Fibonacci,
            'fibonacci',
            execute_callback=self.execute_callback,
            goal_callback=self.goal_callback,
            cancel_callback=self.cancel_callback
        )
        self.get_logger().info('✅ 动作服务器已启动 (/fibonacci)')
    
    def goal_callback(self, goal_request):
        """接受或拒绝目标"""
        if goal_request.order <= 0:
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT
    
    def cancel_callback(self, goal_handle):
        """接受取消请求"""
        self.get_logger().info('收到取消请求')
        return CancelResponse.ACCEPT
    
    async def execute_callback(self, goal_handle):
        """执行动作"""
        self.get_logger().info('执行斐波那契动作...')
        
        # 生成斐波那契数列
        sequence = [0, 1]
        for i in range(1, goal_handle.request.order):
            sequence.append(sequence[-1] + sequence[-2])
            
            # 发布反馈
            feedback_msg = Fibonacci.Feedback()
            feedback_msg.partial_sequence = sequence
            goal_handle.publish_feedback(feedback_msg)
            self.get_logger().info(f'进度: {i}/{goal_handle.request.order}')
            
            # 模拟耗时
            await rclpy.sleep_for(self, rclpy.duration.Duration(seconds=0.5))
        
        # 设置结果
        goal_handle.succeed()
        result = Fibonacci.Result()
        result.sequence = sequence
        self.get_logger().info(f'完成! 序列: {sequence}')
        return result

def main():
    rclpy.init()
    node = ActionServerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()