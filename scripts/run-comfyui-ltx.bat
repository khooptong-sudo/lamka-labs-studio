@echo off
rem ComfyUI launcher tuned for the RTX 3070 8GB LTX-Video path.
rem --use-split-cross-attention keeps attention blocks under the VRAM ceiling;
rem without it the LTX sampler transiently OOMs on WDDM and the GPU drops off
rem the bus ("GPU is lost" in nvidia-smi, black screen) instead of failing clean.
cd /d "%~dp0..\ComfyUI_windows_portable"
.\python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build --use-split-cross-attention
pause
