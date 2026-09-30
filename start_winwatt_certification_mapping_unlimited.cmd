@echo off
title WinWatt ET and building-services mapping
echo ET tanusitasi XML es gepeszeti rendszerek helyi, AI-mentes feltarkepzese.
echo A Windows munkamenet maradjon feloldva. Leallitas: Ctrl+C.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-WinWattMapping.ps1" -UntilComplete -Scope certification %*
set EXIT_CODE=%ERRORLEVEL%
echo.
echo A mapping kilepesi kodja: %EXIT_CODE%
pause
exit /b %EXIT_CODE%
