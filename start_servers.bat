@echo off
echo Starting Agentic Screenwriting Studio...

cd /d "%~dp0"

echo Setting up and starting Backend...
start "Backend" cmd /k "cd backend & (if not exist venv python -m venv venv) & call venv\Scripts\activate.bat & pip install -r requirements.txt & python main.py"

echo Setting up and starting Frontend...
start "Frontend" cmd /k "cd frontend & (if not exist node_modules npm install) & npm run dev"

echo.
echo Both servers are starting up in separate windows!
echo Backend API will be available at http://localhost:8000
echo Frontend will be available at http://localhost:3000
echo.
pause
