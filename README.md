# WebLauncher Apps

这是 WebLauncher 的业务应用源码仓库。Launcher 运行时、桌面 UI、runtime 和 Repo 客户端位于另一个仓库：

```text
C:\Users\jun\Desktop\xieyi\web-launcher
```

本仓库只维护应用源码、应用资源和应用发布工具。

## 目录结构

```text
web-launcher-apps/
├── apps/
│   ├── game/       # 小游戏
│   ├── general/    # 通用工具
│   └── ros/        # ROS2 工具
├── tools/          # wheels 重建、工具箱等开发工具
├── publish.py      # 应用发布器
├── config.json     # Repo 发布配置
└── README.md
```

当前应用数量和字段以各目录中的 `app.json` 为准，发布器会递归扫描所有 `app.json`，不依赖固定分组数量。

## 应用分组

| 分组 | 内容 | 运行要求 |
|---|---|---|
| `game` | breakout、snake、tetris、sokoban 等小游戏 | Python 标准库或浏览器 |
| `general` | JSON、网络、TCP/UDP、MQTT、文件和进程工具 | 按应用声明的 deps 决定 |
| `ros` | ROS2 action、graph、monitor、param、service、topic 工具 | 目标机需配置 ROS2 |

`apps/general/shared.py` 和 `apps/ros/shared_ros2.py` 是应用间共享模块。发布单个 App 时，发布器会分析 Python import，并把当前 App 实际引用的本地公共模块一起打进包，避免安装后出现 `ModuleNotFoundError`。

## 创建应用

```text
apps/<group>/<id>/
├── app.json
├── icon.svg       # 可选，也支持 PNG / WEBP / JPG
├── app.py
├── index.html     # 如果是前端应用
├── images/        # 可选资源
└── README.md
```

## app.json 示例

```json
{
  "id": "my-tool",
  "name": "我的工具",
  "version": "1.0.0",
  "icon": "🧰",
  "icon_file": "icon.svg",
  "color": "#3b82f6",
  "cmd": ["apps/general/my-tool/app.py"],
  "port": 8140,
  "group": "general",
  "deps": [],
  "dock": false
}
```

## 图标规则

Launcher 扫描应用目录时按以下顺序查找：

```text
1. app.json 的 icon_file
2. icon.png
3. icon.svg
4. icon.webp
5. icon.jpg / icon.jpeg
```

找到并成功加载图片时优先显示图片。图片不存在、路径无效或加载失败时，回退到 `icon` Emoji；如果 Emoji 也没有，则显示默认图标 `📦`。

图片会随 App 发布包自动上传，不需要单独操作：

```powershell
python publish.py apps/game/breakout
```

## 本地接入 Launcher 测试

开发时可以把应用分组复制或软链到 Launcher 的 `apps/` 目录。

Windows：

```powershell
mklink /D <launcher目录>\apps\game <本仓库目录>\apps\game
```

Linux/macOS：

```bash
ln -s <本仓库目录>/apps/game <launcher目录>/apps/game
```

不要用整个 `apps/` 覆盖 Launcher 的 `apps/`，否则可能覆盖系统应用。

启动 Launcher：

```powershell
cd C:\Users\jun\Desktop\xieyi\web-launcher
python launcher.py
```

## 发布应用

```powershell
# 列出应用
python publish.py --list

# 发布单个 App
python publish.py apps/general/json-tool

# 发布指定分组
python publish.py --group game
python publish.py --group general
python publish.py --group ros

# 发布全部 App
python publish.py --all

# 只打包不上传
python publish.py apps/game/breakout --dry-run
```

应用发布器会：

- 递归读取 `app.json`
- 打包 App 代码和资源
- 自动收集本地公共 Python 模块
- 保留 App 图片图标
- 根据 `standalone` 打包独立 runtime
- 上传 App 包并更新 Repo `index.json`

依赖 wheels 和 Launcher/runtime 的统一发布由主仓库执行：

```powershell
cd C:\Users\jun\Desktop\xieyi\web-launcher
python publish.py --launcher --build --auto-version --changelog "更新说明"
```

## 应用开发约定

- HTTP 应用必须读取 `LAUNCHER_APP_PORT`，不能硬编码端口。
- HTTP 服务应读取 `APP_HOST`，以支持本机和手机/局域网访问。
- `deps` 只声明第三方 Python 包，例如 `numpy`、`scipy`、`psutil`。
- 自有公共模块不要假设安装机存在仓库兄弟目录，发布器会把实际 import 的本地模块复制进当前 App 包。
- ROS2 应用需要在配置好 ROS2 的终端中运行和测试。
- C/C++ 应用需要针对目标平台生成对应二进制，并在 App README 中写清构建方式。

## License

MIT
