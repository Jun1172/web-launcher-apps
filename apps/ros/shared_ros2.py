"""shared_ros2 - ROS 2 环境探测共享模块

供 apps/ros/ 下各应用统一使用，解决 launcher 启动的应用进程不在 ROS2 激活环境、
ros2 命令不在 PATH 里的问题。跨平台（Windows / Linux / macOS）、不固化具体路径：

定位 ros2 的优先级：
1. 当前进程 PATH 里能直接找到 ros2（例如 Ubuntu 上 source 过 ROS2，
   或已在 pixi/conda 激活环境下）→ 直接用 "ros2 ..."；
2. 否则尝试通过 pixi 运行（pixi 位置取自环境变量 PIXI_EXE 或 PATH 中的 pixi；
   ROS2 项目目录取自环境变量 ROS2_WS，或自动向上查找 pixi.toml）；
3. 都不可用时回退裸 "ros2 ..."（让子进程自然报错，便于定位问题）。

用法：
    import shared_ros2 as ros2env
    cmd, cwd = ros2env.command("topic list")
    subprocess.run(cmd, shell=True, cwd=cwd, ...)
"""
import os
import sys
import signal
import subprocess
import shutil
import threading
from pathlib import Path


def _pixi_exe():
    """返回 pixi 可执行文件路径；找不到返回 None。"""
    env = (os.environ.get("PIXI_EXE") or "").strip()
    if env and Path(env).exists():
        return env
    return shutil.which("pixi")


def _project_root():
    """返回 ROS2 pixi 项目目录；找不到返回 None。

    探测来源（按优先级）：
    1. 环境变量 ROS2_WS（部署时设置，跨机器路径差异时无需改代码）；
    2. 环境变量 PIXI_PROJECT_ROOT（pixi 激活环境会设置，started 于激活 shell 时生效）；
    3. 从 shared_ros2.py 所在目录向上查找 pixi.toml / pyproject.toml。
    """
    for key in ("ROS2_WS", "PIXI_PROJECT_ROOT"):
        env = (os.environ.get(key) or "").strip()
        if env and os.path.isdir(env):
            return env
    mf = (os.environ.get("PIXI_PROJECT_MANIFEST") or "").strip()
    if mf:
        base = os.path.dirname(os.path.abspath(mf))
        if os.path.isdir(base):
            return base
    p = Path(__file__).resolve().parent
    for d in (p, *p.parents):
        if (d / "pixi.toml").exists() or (d / "pyproject.toml").exists():
            return str(d)
    return None


def command(subcommand):
    """根据环境把 ros2 子命令解析为 (可执行命令行, cwd)。"""
    if shutil.which("ros2"):
        return f"ros2 {subcommand}", None
    pixi = _pixi_exe()
    project = _project_root()
    if pixi and project:
        return f'"{pixi}" run -- ros2 {subcommand}', project
    return f"ros2 {subcommand}", None


def available():
    """能否从当前环境解析到 ros2（PATH 里直接有，或可通过 pixi 项目运行）。

    供应用在列表查询为空时提示"未检测到 ROS2 环境"，避免把"环境未就绪"误当成"没有可用项"。
    """
    if shutil.which("ros2"):
        return True
    return bool(_pixi_exe() and _project_root())


def python_command():
    """解析在 ROS2 环境里运行 python 的方式，返回 (命令行, cwd)。

    与 command() 同优先级：若已在激活环境（PATH 里有 ros2）直接用本进程 python；
    否则通过 pixi 项目环境运行，保证 rclpy 等 ROS2 Python 包可 import。
    """
    if shutil.which("ros2"):
        return sys.executable, None
    pixi = _pixi_exe()
    project = _project_root()
    if pixi and project:
        return f'"{pixi}" run -e default -- python', project
    return sys.executable, None


def source_popen_kwargs():
    """启动内置数据源（source.py / client.py）的 Popen 附加参数。

    返回 dict，仅含跨平台安全项：POSIX 下用 start_new_session 让该进程成为新
    进程组组长，便于 kill_proc_tree() 用 killpg 把整棵（含 ROS 节点）一锅端；
    Windows 下该参数被忽略（无副作用），清理改走 taskkill /T。
    """
    kw = {}
    if os.name != "nt":
        kw["start_new_session"] = True
    return kw


def kill_proc_tree(pid):
    """终止某进程及其整棵子孙进程（跨平台、尽量彻底）。

    应用通过 source_popen_kwargs() 启动的子进程是其进程组/会话组长：
    - Windows: taskkill /F /T 一次性删掉 cmd/exe → python → ROS 节点整棵树。
      （直接 terminate() 只会关掉最外层 cmd.exe，真正的节点会变成孤儿残留。）
    - POSIX:   对整个进程组发 SIGKILL（pid 即组长），连同其 ROS 节点一并清理。
    """
    if not pid:
        return
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           capture_output=True, timeout=6)
        except Exception:
            pass
        return
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass


def kill_script(fragment):
    """终止所有命令行里包含 fragment 的进程（跨平台）。

    用途：某应用内置节点（如 param_demo）可能因之前的崩溃/泄漏残留在 DDS 图里，
    与新建的同名节点冲突，导致新节点起不来或被查到的是死节点（表现"0 参数"）。
    启动前用本函数清掉同名残留，保证每次只有一个健康节点。
    fragment 建议带上目录路径，避免误杀其它应用（如 "ros2-param\\source.py"）。
    """
    if not fragment:
        return
    if os.name == "nt":
        ps_cmd = ("Get-CimInstance Win32_Process | "
                  "Where-Object { $_.CommandLine -like '*%s*' } | "
                  "ForEach-Object { Stop-Process -Id $_.ProcessId -Force "
                  "-ErrorAction SilentlyContinue }" % fragment)
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd],
                           capture_output=True, timeout=20)
        except Exception:
            pass
        return
    try:
        out = subprocess.run(["pgrep", "-f", fragment],
                             capture_output=True, text=True, timeout=8).stdout
    except Exception:
        out = ""
    for pid in out.split():
        try:
            os.kill(int(pid), signal.SIGKILL)
        except Exception:
            pass


# 串行化 ros2 CLI 调用的全局锁。
# 每次 `pixi run -- ros2 ...` / `ros2 ...` 都要数秒才能完成；若前端并发发起
# 多个查询（节点列表 + 逐个参数 get + 周期刷新），会同时 fork 出大量 ros2 子进程，
# 拖垮系统并让 HTTP 请求线程越积越多，最终表现为前端"请求异常，请稍后重试"。
# 上锁后同一时刻只有一个 ros2 子进程在跑，其余请求只排队等待，服务器保持可响应。
_ROS2_LOCK = threading.Lock()


def run_cli(args, cwd=None, timeout=25):
    """串行执行一次 ros2/CLI 命令，返回 (stdout, stderr, returncode)。

    用 Popen + communicate 实现，超时触发时整树强杀，而不是依赖
    `subprocess.run(timeout=)`：在 Windows 上它超时后只会 kill 外层
    cmd.exe，孙进程（pixi/python）仍持有 stdout/stderr 管道，导致再次
    读管道永久卡死，且孙进程变成后台残留。这里统一在超时时用
    kill_proc_tree 连根拔掉，并释放全局锁，避免请求堆积卡死。
    """
    cmd, proj = command(" ".join(args))
    cwd = cwd if cwd is not None else proj
    kw = dict(shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
              text=True, encoding="utf-8", errors="replace",
              stdin=subprocess.DEVNULL)
    if os.name != "nt":
        kw["start_new_session"] = True
    with _ROS2_LOCK:
        p = subprocess.Popen(cmd, **kw)
        try:
            out, err = p.communicate(timeout=timeout)
            return out, err, p.returncode
        except subprocess.TimeoutExpired:
            # 超时：整树强杀（Windows taskkill /T，POSIX killpg），避免残留
            kill_proc_tree(p.pid)
            try:
                out, err = p.communicate(timeout=5)
                return (out or ""), (err or "") + "\n[ros2 命令超时，已强制清理]",
                p.returncode or -1
            except Exception:
                return "", "[ros2 命令超时，已强制清理]", -1
        except Exception as e:
            try:
                kill_proc_tree(p.pid)
            except Exception:
                pass
            return "", f"ros2 命令执行异常: {e}", -1