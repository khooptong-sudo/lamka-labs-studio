# Refresh the Cloudflare quick-tunnel URL and patch the VPS worker.
# Quick tunnels are ephemeral - run this whenever cloudflared restarts or the VPS shows "Setup needed".
# Requires: cloudflared on PATH, VPS SSH key in ssh-agent or root@160.250.204.73 BatchMode.

$ErrorActionPreference = "Stop"

# 1. Ensure ComfyUI is up
try { Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8188/system_stats" -TimeoutSec 3 | Out-Null } catch {
  Write-Error "ComfyUI not reachable on 127.0.0.1:8188 - start it first (START_LAMKA_LABS_STUDIO.bat or ComfyUI portable)."
}

# 2. Kill old tunnels and start a new one detached via Start-Process (survives this shell; wscript redirects came up empty)
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Remove-Item -Force $env:TEMP\cf-comfy.log,$env:TEMP\cf-comfy.err -ErrorAction SilentlyContinue
$exe = 'C:\Program Files (x86)\cloudflared\cloudflared.exe'
Start-Process -FilePath $exe -ArgumentList 'tunnel','--url','http://127.0.0.1:8188' -RedirectStandardOutput "$env:TEMP\cf-comfy.log" -RedirectStandardError "$env:TEMP\cf-comfy.err" -WindowStyle Hidden
Write-Host "Waiting for tunnel URL..."
$url = $null
for ($i=0; $i -lt 20; $i++) {
  Start-Sleep -Seconds 2
  $line = Get-Content "$env:TEMP\cf-comfy.log","$env:TEMP\cf-comfy.err" -ErrorAction SilentlyContinue | Select-String "https://.*trycloudflare.com" | Select-Object -Last 1
  if ($line) {
    if ($line.Line -match 'https://[a-z0-9-]+\.trycloudflare\.com') { $url = $matches[0]; break }
  }
}
if (-not $url) { Write-Error "Could not obtain tunnel URL - check $env:TEMP\cf-comfy.err"; Get-Content "$env:TEMP\cf-comfy.err" | Select-Object -Last 20 | Write-Host; exit 1 }
Write-Host "Tunnel: $url"

# 3. Patch VPS env and restart worker
Write-Host "Patching VPS /opt/fce/.env ..."
# Use ssh to replace or append COMFYUI_BASE_URL
ssh -n -o BatchMode=yes root@160.250.204.73 @"
set -e
if grep -q '^COMFYUI_BASE_URL=' /opt/fce/.env; then
  sed -i 's|^COMFYUI_BASE_URL=.*|COMFYUI_BASE_URL=$url|' /opt/fce/.env
else
  echo 'COMFYUI_BASE_URL=$url' >> /opt/fce/.env
fi
grep -q '^COMFYUI_CHECKPOINT_NAME=' /opt/fce/.env || echo 'COMFYUI_CHECKPOINT_NAME=sd_xl_base_1.0_0.9vae.safetensors' >> /opt/fce/.env
grep -q '^COMFYUI_IMAGE_WIDTH=' /opt/fce/.env || echo 'COMFYUI_IMAGE_WIDTH=576' >> /opt/fce/.env
grep -q '^COMFYUI_IMAGE_HEIGHT=' /opt/fce/.env || echo 'COMFYUI_IMAGE_HEIGHT=896' >> /opt/fce/.env
grep -q '^COMFYUI_STEPS=' /opt/fce/.env || echo 'COMFYUI_STEPS=15' >> /opt/fce/.env
grep -q '^COMFYUI_CFG=' /opt/fce/.env || echo 'COMFYUI_CFG=6.0' >> /opt/fce/.env
grep -q '^COMFYUI_TIMEOUT_SECONDS=' /opt/fce/.env || echo 'COMFYUI_TIMEOUT_SECONDS=900' >> /opt/fce/.env
cat /opt/fce/.env | grep COMFYUI
systemctl restart fce-worker
sleep 8
systemctl is-active fce-worker
curl -s http://127.0.0.1:8002/youtube/image-providers
"@
Write-Host "Done. VPS ComfyUI should now show 'Ready' (select it in Studio and refresh)."
