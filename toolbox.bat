@echo off
setlocal
REM ---------------------------------------------------------------
REM  WebLauncher unified toolbox -- apps-repo entry.
REM  The toolbox itself lives in the web-launcher repo
REM  (web-launcher\tools\toolbox.py). This is just a convenience
REM  launcher that opens the SAME window, which manages scripts in
REM  BOTH repos. Requires the two repos to sit side by side
REM  (exe\web-launcher and exe\web-launcher-apps).
REM  Options:  toolbox.bat --http   force browser mode; --port N
REM ---------------------------------------------------------------
set "TB=%~dp0..\web-launcher\tools\toolbox.py"

if not exist "%TB%" (
    echo [ERROR] Not found: %TB%
    echo         Make sure the web-launcher repo is a sibling of this repo.
    pause
    exit /b 1
)

pythonw "%TB%" %*
if errorlevel 1 (
    echo [ERROR] Toolbox failed to start (no pythonw?). Try: python "%TB%"
    pause
)
endlocal
