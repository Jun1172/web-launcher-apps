"""服务数据源：内置服务端节点。

启动后注册三个示例服务，可直接在「服务教程」里调用测试（闭环）：
  /demo_add_two_ints   example_interfaces/srv/AddTwoInts   {a,b} -> sum
  /demo_setbool        std_srvs/srv/SetBool                {data} -> success+message
  /demo_trigger        std_srvs/srv/Trigger                无 -> success+message
"""
import rclpy
from rclpy.node import Node
from std_srvs.srv import SetBool, Trigger
from example_interfaces.srv import AddTwoInts


def main():
    rclpy.init()
    node = Node("service_demo_server")

    def h_add(req, resp):
        resp.sum = req.a + req.b
        node.get_logger().info(f"demo_add_two_ints: {req.a} + {req.b} = {resp.sum}")
        return resp
    node.create_service(AddTwoInts, "demo_add_two_ints", h_add)

    def h_setbool(req, resp):
        resp.success = True
        resp.message = f"data -> {req.data}"
        node.get_logger().info(f"demo_setbool: {req.data}")
        return resp
    node.create_service(SetBool, "demo_setbool", h_setbool)

    def h_trigger(req, resp):
        resp.success = True
        resp.message = "trigger fired"
        node.get_logger().info("demo_trigger: fired")
        return resp
    node.create_service(Trigger, "demo_trigger", h_trigger)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()