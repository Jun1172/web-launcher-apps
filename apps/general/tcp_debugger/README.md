# 🔌 TCP 调试助手（tcp-debug）

验证 Launcher 管理 TCP 长连接应用的能力，以及 TCP Server 多客户端并发处理。

## 应用行为
- 提供 Web UI，支持切换 TCP Client 和 TCP Server 模式
- Server 模式：监听指定端口，接受多个客户端连接，为每个连接分配独立接收线程
- Client 模式：连接指定 IP:Port，后台线程持续接收服务端推送数据
- 实时显示连接状态、系统事件 (SYS)、接收 (RX) 和发送 (TX) 日志

## 验证什么
| 能力 | 实际行为 |
| --- | --- |
| TCP Server 多连接 | 启动 Server 后，可用多个 Telnet/Netcat 客户端同时连接，日志分别显示来源 IP |
| 模式切换 | 从 Server 切换到 Client 时，自动断开旧连接并释放端口，无 `Address already in use` 错误 |
| 状态同步 | UI 右上角实时显示当前状态 (Idle / Server / Client) |
| 异常处理 | 客户端异常断开时，Server 端能捕获并记录 `Client disconnected` 事件 |

## 适用场景
- 自定义 TCP 协议开发与调试
- 物联网设备 TCP 透传测试
- 验证 Launcher 对复杂网络状态应用的管理

## 验证步骤
1. 在 Launcher 中点击 🔌 TCP 调试助手。
2. 选择「TCP Server」，端口 `8080`，点击「连接/监听」。状态变为 `Server`。
3. 打开两个终端，分别执行 `telnet 127.0.0.1 8080`，观察日志出现两条 `Client connected`。
4. 在 Web UI 输入文本点击「发送」，两个终端应同时收到数据。
5. 点击「断开」，切换为「TCP Client」，连接外部 TCP 服务器测试接收功能。

## 文件
- `app.json` —— 应用清单（端口 8142）
- `app.py` —— TCP 客户端/服务端逻辑 + 连接管理 + 前端 UI