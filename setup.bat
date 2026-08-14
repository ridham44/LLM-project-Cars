@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ==================================================
echo   LOCAL AI RESEARCH ENGINE - FIRST-TIME SETUP
echo ==================================================
echo.

set MISSING=0

echo Checking required tools...
where python >nul 2>nul
if errorlevel 1 (
    echo   [MISSING] Python - install Python 3.10+ from https://python.org
    set MISSING=1
) else (
    echo   [OK] Python
)

where node >nul 2>nul
if errorlevel 1 (
    echo   [MISSING] Node.js - install from https://nodejs.org
    set MISSING=1
) else (
    echo   [OK] Node.js
)

where npm >nul 2>nul
if errorlevel 1 (
    echo   [MISSING] npm - usually installed together with Node.js
    set MISSING=1
) else (
    echo   [OK] npm
)

where ollama >nul 2>nul
if errorlevel 1 (
    echo   [MISSING] Ollama - install from https://ollama.ai
    echo             (setup will continue - install it before you run start.bat)
) else (
    echo   [OK] Ollama
)

if "%MISSING%"=="1" (
    echo.
    echo Please install the missing tools above, then re-run setup.bat.
    pause
    exit /b 1
)

echo.
echo Setting up backend...
if not exist "backend\venv\Scripts\python.exe" (
    echo   Creating virtual environment...
    python -m venv backend\venv
)
echo   Installing Python dependencies - this can take a few minutes...
"backend\venv\Scripts\python.exe" -m pip install --upgrade pip >nul
"backend\venv\Scripts\pip.exe" install -r backend\requirements.txt
if errorlevel 1 (
    echo   [FAILED] Backend dependency install failed. See output above.
    pause
    exit /b 1
)

REM spaCy's English pipeline is published as a GitHub release asset, not on
REM PyPI, so requirements.txt cannot pull it. Without it the NLP layer falls
REM back to vocabulary-only entity extraction - it still works, just blunter.
echo   Downloading spaCy English model...
"backend\venv\Scripts\python.exe" -m spacy download en_core_web_sm
if errorlevel 1 (
    echo   [WARN] spaCy model download failed - entity extraction will use the
    echo          built-in vocabulary only. Retry later with:
    echo          backend\venv\Scripts\python.exe -m spacy download en_core_web_sm
)
echo   [OK] Backend environment ready

echo.
echo Setting up frontend...
if not exist "frontend\node_modules" (
    echo   Installing frontend dependencies...
    call npm install --prefix frontend
    if errorlevel 1 (
        echo   [FAILED] Frontend dependency install failed. See output above.
        pause
        exit /b 1
    )
) else (
    echo   [OK] Frontend dependencies already installed
)

if not exist "node_modules" (
    echo   Installing dev-runner dependencies...
    call npm install
)

echo.
if not exist ".env" (
    if exist ".env.example" (
        copy /Y ".env.example" ".env" >nul
        echo   Created .env from .env.example
    )
) else (
    echo   .env already exists - leaving it as-is
)

if not exist "logs" mkdir logs

echo.
echo Verifying Ollama and required models...
python run.py --check-models

echo.
echo ==================================================
echo   SETUP COMPLETE
echo ==================================================
echo.
echo Run start.bat to launch the application.
echo.
pause
