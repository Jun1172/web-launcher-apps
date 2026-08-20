#!/usr/bin/env python3
"""话题发布者 - 发布聊天消息和传感器数据"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Float32
import time

class TopicPublisher(Node):
    def __init__(self):
        super().__init__('topic_publisher')
        self.pub_chatter = self.create_publisher(String, '/chatter', 10)
        self.pub_sensor = self.create_publisher(Float32, '/sensor_data', 10)
        self.counter = 0
        
        # 创建定时器，每秒发布一次
        self.timer = self.create_timer(1.0, self.publish_callback)
        self.get_logger().info('✅ 话题发布者已启动 (/chatter, /sensor_data)')
    
    def publish_callback(self):
        # 发布聊天消息
        msg_chatter = String()
        msg_chatter.data = f'Hello ROS2! Count: {self.counter}'
        self.pub_chatter.publish(msg_chatter)
        
        # 发布传感器数据（模拟温度）
        msg_sensor = Float32()
        msg_sensor.data = 20.0 + (self.counter % 10)  # 20-29度循环
        self.pub_sensor.publish(msg_sensor)
        
        self.counter += 1

def main():
    rclpy.init()
    node = TopicPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()