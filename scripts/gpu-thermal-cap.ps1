# RTX 3070 power-cap history (the card drops off the bus under load; black screen,
# "GPU is lost", force restart):
#   220 W default  -> black-screened during local generation (2026-08/09)
#   190 W cap      -> still black-screened (gpu_log.csv caught a 218 W transient, 75 C)
#   180 W cap      -> STILL black-screened on 2026-09-07 evening. gpu_log2.csv shows the
#                     cap HOLDING (sustained 175-177 W, clocks trimming) at only 65 C with
#                     VRAM <= 7.4/8 GB when the card dropped off the bus mid-LTX-sampling.
# Conclusion: "cap held, still died" = hardware (VRM / PSU rail / VRAM), not thermals or
# sustained power. Software mitigation is CLOSED. Local GPU generation shelved until the
# 4090/5080; motion video runs via Veo/Kling on the VPS meanwhile.
# Run ONCE after each boot (admin rights required):
#   powershell -ExecutionPolicy Bypass -File scripts/gpu-thermal-cap.ps1
# The setting resets at every driver reload / reboot.
$ErrorActionPreference = 'Stop'
nvidia-smi -pl 180
nvidia-smi --query-gpu=power.limit,temperature.gpu --format=csv
