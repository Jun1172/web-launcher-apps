# 🚀 动作执行器 (ros2-action-client)
发送 ROS2 Action 目标并实时监控反馈。
## 验证步骤
1. 启动动作服务器：`ros2 run action_tutorials_cpp fibonacci_action_server`
2. 选择 `/fibonacci` 动作，输入 `{"order": 5}`
3. 点击发送，观察日志中的实时反馈和最终结果。