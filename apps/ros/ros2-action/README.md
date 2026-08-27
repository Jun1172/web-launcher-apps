# 动作教程

动作列表查询 + send_goal + 内置动作服务器（闭环测试）。

- `app.py` — Web 界面与命令入口
- `source.py` — 内置动作服务器 `demo_fib`（Fibonacci，实时反馈）
- `client.py` — 动作客户端，向动作发送目标并流式回传 feedback/result