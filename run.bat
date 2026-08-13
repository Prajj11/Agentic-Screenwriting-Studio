@echo off
title Agentic Screenwriting Studio
echo ==========================================
echo   Agentic Screenwriting Studio
echo ==========================================
echo.

:: Start backend
echo Starting backend server...
cd /d "%~dp0backend"
start "Backend" cmd /k "python main.py"

:: Wait for backend to be ready
echo Waiting for backend to start...
ping 127.0.0.1 -n 4 >nul

:: Start frontend
echo Starting frontend...
cd /d "%~dp0frontend"
start "Frontend" cmd /k "npm run dev"

echo.
echo ==========================================
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:3000
echo ==========================================
echo.
echo Both servers are starting in separate windows.
echo Close this window when done, or press any key to exit.
pause >nul
