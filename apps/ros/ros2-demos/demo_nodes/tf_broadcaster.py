#!/usr/bin/env python3
"""TF 发布器 - 发布机器人坐标系变换"""
import rclpy
from rclpy.node import Node
import tf2_ros
import math
from geometry_msgs.msg import TransformStamped

class TFBroadcaster(Node):
    def __init__(self):
        super().__init__('tf_broadcaster')
        
        self.tf_broadcaster = tf2_ros.TransformBroadcaster(self)
        self.timer = self.create_timer(0.1, self.broadcast_tf)
        
        self.get_logger().info('✅ TF 发布器已启动 (world -> base_link -> laser)')
    
    def broadcast_tf(self):
        t = self.get_clock().now().to_msg()
        
        # world -> base_link (机器人移动)
        t1 = TransformStamped()
        t1.header.stamp = t
        t1.header.frame_id = 'world'
        t1.child_frame_id = 'base_link'
        t1.transform.translation.x = math.sin(self.get_clock().now().nanoseconds / 1e9 * 0.5) * 2.0
        t1.transform.translation.y = math.cos(self.get_clock().now().nanoseconds / 1e9 * 0.5) * 2.0
        t1.transform.translation.z = 0.0
        t1.transform.rotation.w = 1.0
        self.tf_broadcaster.sendTransform(t1)
        
        # base_link -> laser (激光雷达偏移)
        t2 = TransformStamped()
        t2.header.stamp = t
        t2.header.frame_id = 'base_link'
        t2.child_frame_id = 'laser'
        t2.transform.translation.x = 0.5
        t2.transform.translation.y = 0.0
        t2.transform.translation.z = 0.1
        t2.transform.rotation.w = 1.0
        self.tf_broadcaster.sendTransform(t2)

def main():
    rclpy.init()
    node = TFBroadcaster()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()