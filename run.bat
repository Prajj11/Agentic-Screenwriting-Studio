@echo off
setlocal enabledelayedexpansion
title Talevora Launcher
color 0B

echo ========================================================
echo   🎬 TALEVORA - AGENTIC SCREENWRITING STUDIO
echo ========================================================
echo.

:: 1. Check for backend .env file
if not exist "%~dp0backend\.env" (
    if exist "%~dp0backend\.env.example" (
        echo [!] Warning: backend\.env not found. Copying from .env.example...
        copy "%~dp0backend\.env.example" "%~dp0backend\.env" >nul
        echo [OK] Created backend\.env. Please verify your GCP_PROJECT_ID inside.
    ) else (
        echo [!] Warning: backend\.env is missing.
    )
)

:: 2. Determine Python executable
set "PY_CMD=python"
if exist "%~dp0backend\venv\Scripts\python.exe" (
    set "PY_CMD=%~dp0backend\venv\Scripts\python.exe"
    echo [i] Using virtual environment Python: backend\venv
) else (
    echo [i] Using system Python
)

:: 3. Launch Backend Server (Port 8000)
echo.
echo [*] Starting Backend Server (FastAPI on http://localhost:8000)...
start "Screenwriting Studio [Backend :8000]" cmd /k "cd /d "%~dp0backend" && if exist "venv\Scripts\activate.bat" (call venv\Scripts\activate.bat) && python main.py"

:: 4. Launch Frontend Dev Server (Port 3000)
echo [*] Starting Frontend UI (Next.js on http://localhost:3000)...
start "Screenwriting Studio [Frontend :3000]" cmd /k "cd /d "%~dp0frontend" && npm run dev"

:: 5. Wait for servers to spin up
echo.
echo [*] Waiting for services to initialize...
timeout /t 5 /nobreak >nul

:: 6. Launch Studio UI in default browser
echo [*] Opening Agentic Screenwriting Studio in your browser...
start http://localhost:3000

echo.
echo ========================================================
echo   ALL SERVICES RUNNING!
echo ========================================================
echo   - Studio UI:     http://localhost:3000
echo   - Backend API:   http://localhost:8000
echo   - API Docs:      http://localhost:8000/docs
echo.
echo   To stop the studio, close the two server terminal windows
echo   or double-click stop.bat
echo ========================================================
echo.
pause
