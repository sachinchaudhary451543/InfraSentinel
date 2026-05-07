@echo off
TITLE ServerMonitor - Dashboard Server Startup
COLOR 0A
echo ========================================================
echo   ServerMonitor Dashboard - Production Server Startup
echo ========================================================
echo.

echo [1/3] Checking if Python virtual environment exists...
IF NOT EXIST "venv\Scripts\activate.bat" (
    echo Virtual environment not found. Creating one now...
    python -m venv venv
)

echo [2/3] Activating virtual environment and installing requirements...
call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
pip install waitress --quiet

echo [3/3] Starting the Dashboard Server...
echo The dashboard will be available at http://localhost:8080
echo.
echo NOTE: Do not close this window! If you close it, the dashboard will stop.
echo.
python deployment\run_waitress.py

pause
