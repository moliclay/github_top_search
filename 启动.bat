@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo Please install Python 3.10+ or add it to PATH.
    pause
    exit /b 1
)
python scheduler.py start
if errorlevel 1 (
    echo.
    echo [ERROR] Start failed. See logs\app.log.
)
echo.
pause
