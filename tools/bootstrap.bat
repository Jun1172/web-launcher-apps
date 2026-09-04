@echo off
REM =====================================================================
REM  WebLauncher-Apps（本仓库）一键重建脚本
REM  用途：误删本仓库 wheels/ 后，重新下载应用依赖 wheels。
REM
REM  注意：
REM    - 本仓库 **不含** 内嵌 runtime（runtime 属于 web-launcher 仓库）。
REM    - 因此这里只重建 wheels/，runtime 请到 ../web-launcher 跑它的 bootstrap.bat。
REM    - wheels 的 Python 版本会自动探测同级 web-launcher/runtime；
REM      找不到时回退 3.11，需与 web-launcher 的 runtime 保持一致。
REM
REM  前置条件：
REM    1. 机器能联网（需从 PyPI 下载依赖 wheels）
REM    2. 命令行里有 python（任意版本，仅用于跑本脚本）
REM =====================================================================
setlocal
cd /d "%~dp0"

echo ============================================
echo 重建本仓库应用依赖 wheels (wheels/^<平台^>)
echo ============================================
python make_wheels.py
if errorlevel 1 (
    echo.
    echo [错误] wheels 下载失败，请检查：
    echo   - 网络是否可访问 PyPI
    echo   - 各依赖是否有对应平台的预编译 wheel
    pause
    exit /b 1
)

echo.
echo ============================================
echo 完成！本仓库的 wheels/ 已重建。
echo （runtime 属于 web-launcher 仓库，请到它那里重建）
echo ============================================
pause
endlocal
