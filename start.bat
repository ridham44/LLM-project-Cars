@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found on PATH.
    echo Install Python 3.10+ from https://python.org and try again.
    pause
    exit /b 1
)

if not exist "backend\venv\Scripts\python.exe" (
    echo.
    echo ==================================================
    echo         FIRST TIME SETUP REQUIRED
    echo ==================================================
    echo.
    echo This appears to be the first time running
    echo Local AI Research Engine.
    echo.
    choice /C YN /M "Run setup now"
    if errorlevel 2 (
        echo.
        echo Run setup.bat whenever you're ready, then start.bat again.
        exit /b 1
    )
    call "%~dp0setup.bat"
    if errorlevel 1 exit /b 1
)

python run.py %*
