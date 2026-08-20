#!/usr/bin/env python3
"""服务服务器 - 提供数学计算服务"""
import rclpy
from rclpy.node import Node
from std_srvs.srv import Empty
from example_interfaces.srv import AddTwoInts

class ServiceServer(Node):
    def __init__(self):
        super().__init__('service_server')
        
        # 加法服务
        self.srv_add = self.create_service(AddTwoInts, '/add_two_ints', self.add_callback)
        
        # 简单服务
        self.srv_empty = self.create_service(Empty, '/check_status', self.empty_callback)
        
        self.get_logger().info('✅ 服务服务器已启动 (/add_two_ints, /check_status)')
    
    def add_callback(self, request, response):
        a, b = request.a, request.b
        response.sum = a + b
        self.get_logger().info(f'计算: {a} + {b} = {response.sum}')
        return response
    
    def empty_callback(self, request, response):
        self.get_logger().info('状态检查请求')
        return response

def main():
    rclpy.init()
    node = ServiceServer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()