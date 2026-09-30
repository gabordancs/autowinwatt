@echo off
title WinWatt AI-free mapping - until complete
echo A legutobbi befejezetlen kampany folytatasa idokorlat nelkul.
echo A Windows munkamenet maradjon feloldva. Leallitas: Ctrl+C.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-WinWattMapping.ps1" -ResumeLatest -UntilComplete %*
set EXIT_CODE=%ERRORLEVEL%
echo.
echo A mapping kilepesi kodja: %EXIT_CODE%
pause
exit /b %EXIT_CODE%
