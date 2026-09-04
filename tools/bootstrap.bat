@echo off
setlocal
REM ---------------------------------------------------------------
REM  web-launcher-apps one-shot rebuild: regenerates this repo's wheels/.
REM  This repo has NO embedded runtime (runtime belongs to web-launcher),
REM  so this only rebuilds wheels. For runtime, run web-launcher's
REM  tools\bootstrap.bat instead. Needs network + a "python" on PATH.
REM ---------------------------------------------------------------
cd /d "%~dp0"

echo ============================================
echo Rebuild this repo's app dependency wheels (wheels/^<platform^>)
echo ============================================
python make_wheels.py
if errorlevel 1 (
    echo.
    echo [ERROR] wheels download failed. Check PyPI access and prebuilt wheels.
    pause
    exit /b 1
)

echo.
echo ============================================
echo Done. This repo's wheels/ rebuilt.
echo (runtime belongs to web-launcher; rebuild it over there)
echo ============================================
pause
endlocal
