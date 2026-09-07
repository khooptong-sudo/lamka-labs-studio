# Cap the RTX 3070 at 190 W as a middle ground: ~10% render speed cost vs
# default 220 W, meaningfully lower heat/voltage stress. The failed runs that
# black-screened the PC peaked at 217 W, so 190 W keeps headroom under the
# failure envelope. Run ONCE after each boot (admin rights required):
#   powershell -ExecutionPolicy Bypass -File scripts/gpu-thermal-cap.ps1
# The setting resets at every driver reload / reboot.
$ErrorActionPreference = 'Stop'
nvidia-smi -pl 190
nvidia-smi --query-gpu=power.limit,temperature.gpu --format=csv
