#!/usr/bin/env python3
"""参数节点 - 提供可调节的参数"""
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter

class ParamNode(Node):
    def __init__(self):
        super().__init__('param_node')
        
        # 声明参数
        self.declare_parameter('robot_name', 'MyRobot')
        self.declare_parameter('max_speed', 1.5)
        self.declare_parameter('enabled', True)
        self.declare_parameter('colors', ['red', 'green', 'blue'])
        
        # 参数回调
        self.add_on_set_parameters_callback(self.param_callback)
        
        self.get_logger().info('✅ 参数节点已启动')
        self.get_logger().info('可用参数: robot_name, max_speed, enabled, colors')
    
    def param_callback(self, params):
        for param in params:
            self.get_logger().info(f'参数修改: {param.name} = {param.value}')
        return [rclpy.parameter.Parameter.Type.NOT_SET] * len(params)

def main():
    rclpy.init()
    node = ParamNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()