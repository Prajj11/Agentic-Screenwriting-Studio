@echo off
title Agentic Screenwriting Studio Launcher

echo ===================================================
echo   🎬 Agentic Screenwriting Studio Launcher
echo ===================================================
echo.

:: 1. Check for backend\.env file
if not exist "%~dp0backend\.env" (
    if exist "%~dp0backend\.env.example" (
        echo [!] backend\.env not found. Copying from backend\.env.example...
        copy "%~dp0backend\.env.example" "%~dp0backend\.env" >nul
        echo [V] Created backend\.env
    ) else (
        echo [!] Warning: backend\.env.example not found.
    )
)

:: 2. Determine Python activation command
set "ACTIVATE_CMD="
if exist "%~dp0.venv\Scripts\activate.bat" (
    set "ACTIVATE_CMD=call "%~dp0.venv\Scripts\activate.bat" && "
    echo [V] Virtual environment found (.venv)
) else (
    if exist "%~dp0venv\Scripts\activate.bat" (
        set "ACTIVATE_CMD=call "%~dp0venv\Scripts\activate.bat" && "
        echo [V] Virtual environment found (venv)
    ) else (
        if exist "%~dp0backend\.venv\Scripts\activate.bat" (
            set "ACTIVATE_CMD=call "%~dp0backend\.venv\Scripts\activate.bat" && "
            echo [V] Virtual environment found (backend\.venv)
        )
    )
)

:: 3. Check frontend node_modules
if not exist "%~dp0frontend\node_modules" (
    echo [!] Frontend dependencies missing. Installing node_modules...
    cd /d "%~dp0frontend"
    call npm install
    cd /d "%~dp0"
)

echo.
echo Starting FastAPI Backend on port 8000...
start "Backend - FastAPI" cmd /k "cd /d "%~dp0backend" && %ACTIVATE_CMD%python main.py"

echo Starting Next.js Frontend on port 3000...
start "Frontend - Next.js" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo ===================================================
echo   🚀 All services launching!
echo   Frontend: http://localhost:3000
echo   Backend:  http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo ===================================================
echo.
pause
