@echo off
TITLE ServerMonitor - Agent Startup
COLOR 0B
echo ========================================================
echo         ServerMonitor Agent - Startup Script
echo ========================================================
echo.

:: IMPORTANT: Change these values before running!
set DASHBOARD_IP=127.0.0.1
set DASHBOARD_PORT=8080
set AGENT_API_KEY=YOUR_SECRET_KEY_HERE

echo [1/2] Connecting to Dashboard at http://%DASHBOARD_IP%:%DASHBOARD_PORT%
echo.

echo [2/2] Starting the background agent...
echo NOTE: Do not close this window! If you close it, this computer will show as "Offline".
echo.
python agent.py --url http://%DASHBOARD_IP%:%DASHBOARD_PORT% --key %AGENT_API_KEY%

pause
