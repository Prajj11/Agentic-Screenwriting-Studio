@echo off
title Talevora - Stopper
color 0C

echo ========================================================
echo   🛑 STOPPING TALEVORA
echo ========================================================
echo.

echo [*] Terminating Backend on port 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
    echo     Stopped PID %%a on port 8000
)

echo [*] Terminating Frontend on port 3000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
    echo     Stopped PID %%a on port 3000
)

echo.
echo [OK] All studio services stopped.
echo ========================================================
timeout /t 3 >nul
