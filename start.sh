#!/usr/bin/env bash
# Linux/macOS launcher. Windows should use start.bat.
set -e
cd "$(dirname "${BASH_SOURCE[0]}")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 was not found on PATH. Install Python 3.10+ and try again."
    exit 1
fi

if [ ! -x "backend/venv/bin/python" ]; then
    echo ""
    echo "=================================================="
    echo "        FIRST TIME SETUP REQUIRED"
    echo "=================================================="
    echo ""
    echo "This appears to be the first time running Local AI Research Engine."
    read -r -p "Run setup now? [y/N] " answer
    case "$answer" in
        [yY]*)
            python3 -m venv backend/venv
            backend/venv/bin/pip install --upgrade pip
            backend/venv/bin/pip install -r backend/requirements.txt
            if [ ! -d "frontend/node_modules" ]; then
                npm install --prefix frontend
            fi
            [ -f ".env" ] || { [ -f ".env.example" ] && cp .env.example .env; }
            mkdir -p logs
            ;;
        *)
            echo "Run setup manually, then start.sh again."
            exit 1
            ;;
    esac
fi

python3 run.py "$@"
