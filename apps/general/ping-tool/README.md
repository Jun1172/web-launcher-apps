# 📡 Ping 工具 (ping-tool)

![界面预览](images/screenshot.png)
验证 Launcher 处理系统命令输出编码的能力。
## 应用行为
调用系统 `ping` 命令，自动适配 Windows (GBK) 和 Linux/Mac (UTF-8) 编码，确保中文正常显示。
## 验证步骤
1. 在 Launcher 中点击「Ping 工具」。
2. 输入 `127.0.0.1` 或局域网 IP，点击 Ping。
3. 观察输出结果中的中文（如“来自...的回复”）是否乱码。