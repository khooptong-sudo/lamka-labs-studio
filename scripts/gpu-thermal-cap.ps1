# Cap the RTX 3070 at 150 W to trade ~15-20% render speed for much lower
# heat/voltage stress. Run ONCE after each boot (admin rights required):
#   powershell -ExecutionPolicy Bypass -File scripts/gpu-thermal-cap.ps1
# The setting resets at every driver reload / reboot.
$ErrorActionPreference = 'Stop'
nvidia-smi -pl 150
nvidia-smi --query-gpu=power.limit,temperature.gpu --format=csv
