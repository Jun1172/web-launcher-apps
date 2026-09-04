# 🌐 局域网扫描 (ip-scanner)

![界面预览](images/screenshot.png)
验证 Launcher 承载多线程并发网络扫描应用的能力。
## 应用行为
使用多线程并发 Ping 扫描 C 类网段，并通过 `nbtstat` (Windows) 或 `host` (Linux) 解析存活 IP 的设备名称。
## 验证步骤
1. 在 Launcher 中点击「局域网扫描」。
2. 输入当前所在网段（如 `192.168.1`），点击扫描。
3. 观察列表是否同时显示 IP 地址与对应的设备名称（如 `DESKTOP-XXX`）。