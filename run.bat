@echo off
echo ===================================================
echo   Agentic Screenwriting Studio Launcher
echo ===================================================
echo Starting FastAPI Backend on port 8000...
start "Backend - FastAPI" cmd /k "cd /d %~dp0backend && python main.py"

echo Starting Next.js Frontend on port 3000...
start "Frontend - Next.js" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo All services launching!
echo Frontend: http://localhost:3000
echo Backend:  http://localhost:8000 (Swagger: http://localhost:8000/docs)
echo ===================================================
