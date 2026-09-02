@echo off
echo ========================================================
echo   Starting Agentic Screenwriting Studio
echo ========================================================
echo.

:: Start Backend
echo Starting Backend (FastAPI on http://localhost:8000)...
start "Screenwriting Studio Backend" cmd /k "cd /d %~dp0backend && venv\Scripts\activate && python main.py"

:: Start Frontend
echo Starting Frontend (Next.js on http://localhost:3000)...
start "Screenwriting Studio Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo All services launched!
echo - Backend:  http://localhost:8000 (Swagger docs: http://localhost:8000/docs)
echo - Frontend: http://localhost:3000
echo ========================================================
