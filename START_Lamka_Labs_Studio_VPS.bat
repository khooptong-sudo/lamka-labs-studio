@echo off
setlocal

rem One-click launcher for Lamka Labs Studio using the VPS worker.
rem This only starts the GUI; the worker runs remotely at 160.250.204.73:8002.

set "ROOT=%~dp0"
set "NEXT_PUBLIC_WORKER_URL=http://160.250.204.73:8002"

start "Lamka Labs Studio (VPS)" /min /D "%ROOT%gui" cmd.exe /d /c "set NEXT_PUBLIC_WORKER_URL=%NEXT_PUBLIC_WORKER_URL% && npm.cmd run dev"
timeout /t 5 /nobreak >nul

rem Standalone window: app mode has no tabs or address bar, so the Studio
rem feels like its own program. Falls back to the default browser.
set "STUDIO_URL=http://localhost:3000/x"
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" goto :studio_chrome
set "STUDIO_EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if exist "%STUDIO_EDGE%" goto :studio_edge
start "" "%STUDIO_URL%"
exit /b 0
:studio_chrome
start "" "%ProgramFiles%\Google\Chrome\Application\chrome.exe" --app=%STUDIO_URL% --user-data-dir="%ROOT%.studio-chrome-profile"
exit /b 0
:studio_edge
start "" "%STUDIO_EDGE%" --app=%STUDIO_URL% --user-data-dir="%ROOT%.studio-edge-profile"
exit /b 0
