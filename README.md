# 📦 Web Launcher Apps — 业务应用仓库

一个**纯应用仓库**项目：包含业务应用 + 一组 demo 应用，通过 [web-launcher](../web-launcher/) 框架运行。本项目**不含** launcher 框架代码本身。

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
    ├── etws/                # 业务应用分组（自定义 group="etws"）
    │   └── ad-analysis/     # 📈 [C01] AD 数据解析（端口 8115）
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

### 业务应用（`apps/etws/`，分组 `etws`）

| 应用 | 端口 | 说明 |
|------|------|------|
| 📈 [C01]AD数据解析 ad-analysis | 8115 | ADC/IQ 曲线数据分析工具：导入 BIN 文件、多通道解析、Canvas 波形绘制、缩放/框选、CSV 导出 |

### demo 应用（`apps/user/`）

详见 [web-launcher/README.md#内置应用](../web-launcher/README.md#-内置应用)。

## 🚀 快速开始

### 方式 A：与 web-launcher 共置（推荐开发态）

```bash
# 1. 把本项目的 apps/* 软链到 web-launcher/apps/
# Windows（管理员权限）：
mklink /D c:\Users\jun\Desktop\exe\web-launcher\apps\etws c:\Users\jun\Desktop\exe\web-launcher-apps\apps\etws
# Linux：
ln -s /path/to/web-launcher-apps/apps/etws /path/to/web-launcher/apps/etws

# 2. 启动 web-launcher
cd ../web-launcher
python launcher.py
```

### 方式 B：复制 apps/ 到 web-launcher

```bash
# 复制业务应用分组
Copy-Item -Recurse apps/etws ../web-launcher/apps/
```

## 📦 发布流程

```bash
# 列出所有可发布的应用
python publish.py --list

# 发布单个业务应用
python publish.py apps/etws/ad-analysis

# 发布整个 etws 分组
python publish.py --group etws

# 发布所有 user demo
python publish.py --user

# 一键发布全部
python publish.py --all
```

## 📋 app.json Schema

详见 [web-launcher/README.md#app-json-schema](../web-launcher/README.md#-appjson-schema) 与 [apps/README.md](apps/README.md)。

业务应用 ad-analysis 的清单示例：

```json
{
  "id": "ad-analysis",
  "name": "[C01]AD数据解析",
  "icon": "📈",
  "color": "#9b59b6",
  "version": "1.0.0",
  "port": 8115,
  "cmd": ["apps/etws/ad-analysis/app.py"],
  "group": "etws"
}
```

## 🛣 待办

- [ ] 确认是否保留 `apps/user/` 下与 web-launcher 重复的 demo（hello/notes/weather/game2048/proc-demo/file-demo/system-monitor/cpp-hello），避免双仓库同步漂移
- [ ] 业务应用历史版本回退测试

## 📜 License

MIT
