@echo off
title Scanner Restart
cd /d "%~dp0"

echo === Stopping scanner (if running) ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter 'name=''python.exe''' | Where-Object { $_.CommandLine -like '*run_live*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

timeout /t 1 /nobreak >nul

echo === Starting scanner ===
start "Scanner Live" cmd /k "%~dp0start_scanner.bat"

echo Scanner started in new window.
timeout /t 3 /nobreak >nul
