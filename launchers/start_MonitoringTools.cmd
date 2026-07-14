@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\Web3Tools\launchers\launch_monitoring_tools.ps1" -Force
echo.
echo Exit code: %ERRORLEVEL%
pause
