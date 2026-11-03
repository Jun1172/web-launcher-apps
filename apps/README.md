# 应用开发指南

应用放在 `apps/<group>/<id>/`，每个应用至少包含 `app.json` 和启动代码。Launcher 会递归扫描所有 `app.json`，`group` 决定应用分组。

## 目录示例

```text
apps/game/my-game/
├── app.json
├── icon.svg          # 可选，也支持 PNG / WEBP / JPG
├── app.py
├── index.html        # 可选
├── images/           # 可选资源
└── README.md
```

## app.json 常用字段

| 字段 | 必填 | 说明 |
|---|---:|---|
| `id` | 是 | 应用唯一 ID |
| `name` | 是 | 显示名称 |
| `version` | 是 | 应用版本 |
| `cmd` | 否 | 启动命令；无 cmd 时是占位应用 |
| `port` | 否 | HTTP/TCP 应用的建议端口 |
| `group` | 否 | 分组，例如 `game`、`general`、`ros` |
| `icon` | 否 | 图片失败时的 Emoji 回退 |
| `icon_file` | 否 | App 目录内的图片图标 |
| `color` | 否 | 应用主色 |
| `deps` | 否 | 第三方 Python 依赖 |
| `standalone` | 否 | 是否将 Python runtime 打进 App 包 |
| `protect` | 否 | 是否编译为 pyc 发布 |
| `dock` | 否 | 是否默认进入 Dock |
| `exclude` | 否 | 额外排除的发布目录或文件名 |

## 图标规则

Launcher 按以下顺序查找图片：

```text
1. app.json 的 icon_file
2. icon.png
3. icon.svg
4. icon.webp
5. icon.jpg / icon.jpeg
```

图片成功加载时优先使用图片；图片不存在、路径无效或加载失败时回退到 `icon` Emoji；两者都没有时显示 `📦`。

推荐图标尺寸：64×64、128×128 或 256×256。图标文件会随 App 一起发布：

```powershell
python publish.py apps/game/my-game
```

不需要单独上传图标。

## HTTP 应用约定

应用必须读取 Launcher 注入的端口：

```python
import os
from http.server import ThreadingHTTPServer

port = int(os.environ.get("LAUNCHER_APP_PORT", "8120"))
host = os.environ.get("APP_HOST", "127.0.0.1")
ThreadingHTTPServer((host, port), Handler).serve_forever()
```

不要把端口或监听地址硬编码为固定值。这样应用才能支持端口冲突处理和手机/局域网访问。

## 本地公共模块

如果应用引用仓库内公共代码，例如：

```python
from general.shared import serve_page
```

发布器会分析 import，并把实际引用的本地模块复制进当前 App 包。安装后的 App 不应依赖安装机上存在兄弟目录。

ROS 应用可以使用 `apps/ros/shared_ros2.py` 中的共享能力；目标设备必须提前配置 ROS2 环境。

## 本地测试

```powershell
cd C:\Users\jun\Desktop\xieyi\web-launcher
python launcher.py
```

打开：

```text
http://127.0.0.1:8000/
```

## 发布应用

```powershell
# 查看应用
python publish.py --list

# 发布单个应用
python publish.py apps/general/json-tool

# 发布指定分组
python publish.py --group game
python publish.py --group general
python publish.py --group ros

# 发布全部应用
python publish.py --all

# 只打包不上传
python publish.py apps/game/my-game --dry-run
```

应用仓库只发布 App。Launcher、runtime 和 wheels 由主仓库发布：

```powershell
cd C:\Users\jun\Desktop\xieyi\web-launcher
python publish.py --launcher --build --auto-version --changelog "更新说明"
```

## 分组

- `game`：小游戏
- `general`：通用工具
- `ros`：ROS2 应用

实际应用清单以各分组目录中的 `app.json` 为准。

## License

MIT
