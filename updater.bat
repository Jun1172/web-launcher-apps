@echo off
setlocal
set "TARGET=C:\Users\20468\Desktop\web\web-launcher-apps\launcher.exe"
set "NEW=C:\Users\20468\Desktop\web\web-launcher-apps\launcher.new"

rem 等待当前进程退出（轮询检查）
:wait_loop
tasklist /FI "IMAGENAME eq launcher.exe" 2>NUL | find /I "launcher.exe" >NUL
if %ERRORLEVEL%==0 (
    timeout /t 1 /nobreak >NUL
    goto wait_loop
)

rem 等待文件系统释放
timeout /t 2 /nobreak >NUL

rem 替换旧版本
if exist "%TARGET%" del /f "%TARGET%"
move /Y "%NEW%" "%TARGET%"

rem 清理 updater 自身
del /f "%~f0"

rem 重启
start "" "%TARGET%"
