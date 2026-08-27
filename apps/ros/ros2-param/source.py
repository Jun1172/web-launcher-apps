"""参数数据源：内置参数节点 param_demo。

声明一组示例参数供 get/set 测试（闭环），并含一个每秒自增的 count 参数。
进程被「停止」或 launcher 关闭以 taskkill /T 整树强杀时直接终止，无需特殊清理。
"""
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter


def main():
    rclpy.init()
    node = Node("param_demo")

    node.declare_parameter("int_param", 42)
    node.declare_parameter("float_param", 3.14)
    node.declare_parameter("str_param", "hello")
    node.declare_parameter("bool_param", True)
    node.declare_parameter("int_array", [1, 2, 3, 4])
    node.declare_parameter("count", 0)

    # 每秒自增 count，演示"动态参数实时刷新"
    def tick():
        node.set_parameters([Parameter(
            "count", Parameter.Type.INTEGER,
            node.get_parameter("count").value + 1)])

    node.create_timer(1.0, tick)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()