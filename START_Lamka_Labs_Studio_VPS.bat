@echo off
setlocal

rem One-click launcher for Lamka Labs Studio using the VPS worker.
rem This only starts the GUI; the worker runs remotely at 160.250.204.73:8002.

set "ROOT=%~dp0"
set "NEXT_PUBLIC_WORKER_URL=http://160.250.204.73:8002"

start "Lamka Labs Studio (VPS)" /min /D "%ROOT%gui" cmd.exe /d /c "set NEXT_PUBLIC_WORKER_URL=%NEXT_PUBLIC_WORKER_URL% && npm.cmd run dev"
timeout /t 5 /nobreak >nul

start "" "http://localhost:3000/x"
exit /b 0
