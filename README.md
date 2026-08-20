# 📦 Web Launcher Apps — 业务应用仓库

一个**纯应用仓库**项目：包含通用应用 + 一组 demo 应用，通过 [web-launcher](https://github.com/Jun1172/web-launcher) 框架运行。本项目**不含** launcher 框架代码本身。

> 📚 **完整文档请查阅 Wiki**：[GitHub Wiki](https://github.com/Jun1172/web-launcher/wiki) | [Gitee Wiki](https://gitee.com/jun626/web-launcher/wikis)
> 
> Wiki 与 web-launcher 主仓库共用，涵盖 launcher 框架与应用开发的全部文档。

---

## 📌 项目定位

| 维度 | 说明 |
|------|------|
| **是什么** | 业务应用源码仓库（apps/）+ 发布工具（publish.py）+ 配置（config.json） |
| **不是什么** | 不含 launcher 框架（无 launcher.py / launcher/ 包）；运行需要先安装 web-launcher |
| **运行方式** | 把本项目的 apps/ 软链 / 复制到 web-launcher 的 apps/ 下；或直接修改 web-launcher 的 config.json 指向这里 |
| **发布方式** | 本项目自带 `publish.py`，把应用打包成 zip 推送到远端仓库 |

## 📂 目录结构

```
web-launcher-apps/
├── README.md                # 本文档
├── config.json              # 仓库配置（host/port/repo/ports/system_apps）
├── publish.py                # 发布工具（与 web-launcher/publish.py 同步）
└── apps/
    ├── README.md            # 应用开发指南（与 web-launcher 同步）
    ├── general/             # 通用应用分组（自定义 group="general"）
    │   ├── calculator/      # 🧮 计算器
    │   ├── mqtt_debugger/   # 📡 MQTT 调试工具
    │   ├── tcp_debugger/    # 🔧 TCP 调试工具
    │   └── udp_debugger/    # 📶 UDP 调试工具
    └── user/                # demo 应用分组
        ├── hello/           # 👋 最简 demo
        ├── notes/           # 🗒️ 便签
        ├── weather/         # 🌤️ 天气
        ├── game2048/        # 🎮 2048 小游戏
        ├── proc-demo/       # ⚙️ 后台进程 demo
        ├── file-demo/       # 📄 占位 stub demo
        ├── system-monitor/  # 📈 实时监控
        └── cpp-hello/       # 🦾 C++ 应用模板
```

## 🎯 内置应用

### 通用应用（`apps/general/`，分组 `general`）

| 应用 | 端口 | 说明 |
|------|------|------|
| 🧮 计算器 calculator | — | 基础计算器工具 |
| 📡 MQTT 调试 mqtt_debugger | — | MQTT 消息发布/订阅调试工具 |
| 🔧 TCP 调试 tcp_debugger | — | TCP 客户端/服务端调试工具 |
| 📶 UDP 调试 udp_debugger | — | UDP 数据收发调试工具 |

### demo 应用（`apps/user/`）

详见 [web-launcher 文档 - 内置应用](https://github.com/Jun1172/web-launcher/wiki/Getting-Started#内置应用)。

## 🚀 快速开始

### 方式 A：与 web-launcher 共置（推荐开发态）

```bash
# 1. 把本项目的 apps/* 软链到 web-launcher/apps/
# Windows（管理员权限）：
mklink /D c:\path\to\web-launcher\apps\general c:\path\to\web-launcher-apps\apps\general
# Linux：
ln -s /path/to/web-launcher-apps/apps/general /path/to/web-launcher/apps/general

# 2. 启动 web-launcher
cd ../web-launcher
python launcher.py
```

### 方式 B：复制 apps/ 到 web-launcher

```bash
# 复制通用应用分组
Copy-Item -Recurse apps/general ../web-launcher/apps/
```

## 📦 发布流程

```bash
# 列出所有可发布的应用
python publish.py --list

# 发布单个通用应用
python publish.py apps/general/calculator

# 发布整个 general 分组
python publish.py --group general

# 发布所有 user demo
python publish.py --user

# 一键发布全部
python publish.py --all
```

## 📋 app.json Schema

详见 [Wiki - Configuration](https://github.com/Jun1172/web-launcher/wiki/Configuration) 与 [apps/README.md](apps/README.md)。

通用应用清单示例：

```json
{
  "id": "calculator",
  "name": "计算器",
  "icon": "🧮",
  "color": "#3498db",
  "version": "1.0.0",
  "port": 8150,
  "cmd": ["apps/general/calculator/app.py"],
  "group": "general"
}
```

## 🛣 待办

- [ ] 确认是否保留 `apps/user/` 下与 web-launcher 重复的 demo（hello/notes/weather/game2048/proc-demo/file-demo/system-monitor/cpp-hello），避免双仓库同步漂移
- [ ] 通用应用历史版本回退测试

## 📜 License

MIT
