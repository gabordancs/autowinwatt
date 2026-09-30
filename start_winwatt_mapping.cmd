@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-WinWattMapping.ps1" %*
set EXIT_CODE=%ERRORLEVEL%
echo.
echo A mapping kilepesi kodja: %EXIT_CODE%
pause
exit /b %EXIT_CODE%
