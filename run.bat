@echo off
echo Starting Agentic Screenwriting Studio...

echo Starting Backend...
start "Backend" cmd /k "cd backend && call .\venv\Scripts\activate && python main.py"

echo Starting Frontend...
start "Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo Both servers are starting up in separate windows!
echo Backend API will be available at http://localhost:8000
echo Frontend will be available at http://localhost:3000
echo.
pause
