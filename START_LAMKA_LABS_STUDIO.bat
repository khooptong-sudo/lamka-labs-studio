@echo off
setlocal

rem One-click launcher for Lamka Labs Studio.
rem It uses the existing Docker database, venv, and GUI folders; no cloud services are deployed.
set "ROOT=%~dp0"

docker info >nul 2>nul
if not errorlevel 1 goto docker_ready

echo Starting Docker Desktop for the local Content database...
start "Docker Desktop" /min "C:\Program Files\Docker\Docker\Docker Desktop.exe"
set /a docker_attempts=0

:wait_for_docker
timeout /t 3 /nobreak >nul
docker info >nul 2>nul
if not errorlevel 1 goto docker_ready
set /a docker_attempts+=1
if %docker_attempts% LSS 20 goto wait_for_docker

echo Docker Desktop did not become ready. Start it, wait for the tray icon to settle, then click this file again.
pause
exit /b 1

:docker_ready
echo Starting the local Content database...
docker compose -f "%ROOT%docker-compose.yml" up -d db
if errorlevel 1 (
  echo Could not start the local Content database.
  pause
  exit /b 1
)

rem Local zero-credit cinematic keyframes. The worker inherits these 8 GB-safe
rem defaults; the 1080x1920 final composition performs the cinematic 2.5D crop.
set "COMFY_ROOT=%ROOT%ComfyUI_windows_portable"
set "COMFYUI_BASE_URL=http://127.0.0.1:8188"
set "COMFYUI_CHECKPOINT_NAME=sd_xl_base_1.0_0.9vae.safetensors"
set "COMFYUI_IMAGE_WIDTH=576"
set "COMFYUI_IMAGE_HEIGHT=896"
set "COMFYUI_STEPS=15"
set "COMFYUI_CFG=6.0"
set "COMFYUI_TIMEOUT_SECONDS=300"

if exist "%COMFY_ROOT%\python_embeded\python.exe" (
  powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8188/system_stats' -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
  if not errorlevel 1 goto comfy_ready
  start "ComfyUI Local" /min /D "%COMFY_ROOT%" "%COMFY_ROOT%\python_embeded\python.exe" -s ComfyUI\main.py --disable-auto-launch --windows-standalone-build --port 8188
  timeout /t 5 /nobreak >nul
) else (
    echo ComfyUI portable is not installed yet. Gemini remains available until local setup finishes.
)

:comfy_ready
start "Lamka Labs Worker" /min /D "%ROOT%worker" "%ROOT%.venv\Scripts\python.exe" "run_worker.py"
timeout /t 8 /nobreak >nul

start "Lamka Labs Studio" /min /D "%ROOT%gui" cmd.exe /d /c "npm.cmd run dev"
timeout /t 5 /nobreak >nul

rem Standalone window: app mode has no tabs or address bar, so the Studio
rem feels like its own program. Falls back to the default browser.
set "STUDIO_URL=http://localhost:3000/films"
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
