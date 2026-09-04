@echo off
REM =====================================================================
REM  WebLauncher 统一工具箱 —— apps 仓库入口
REM
REM  工具箱本体在 web-launcher 仓库（web-launcher\tools\toolbox.py），
REM  这里只是一个便捷入口，双击它就打开同一个工具箱窗口。
REM  工具箱会同时管理 web-launcher 与本仓库（web-launcher-apps）的脚本。
REM
REM  前置：两个仓库须放在同一目录下（exe\web-launcher 与 exe\web-launcher-apps）。
REM  可选参数：toolbox.bat --http  强制浏览器模式；--port 8799  指定端口
REM =====================================================================
setlocal
set "TB=%~dp0..\web-launcher\tools\toolbox.py"

if not exist "%TB%" (
    echo [错误] 找不到 %TB%
    echo        请确认 web-launcher 仓库与本仓库是同级目录。
    pause
    exit /b 1
)

pythonw "%TB%" %*
if errorlevel 1 (
    echo [错误] 工具箱启动失败（可能本机没有 pythonw，可改用 python 运行 %TB%）。
    pause
)
endlocal
