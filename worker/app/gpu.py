"""The whole RTX 3070 behind one semaphore.

One worker process owns the card, so an in-process lock is the complete
solution — no distributed coordination. Acquire ONLY around work that touches
the GPU (local Ollama planning, ComfyUI builds, the HyperFrames render).
Cloud and CPU stages stay outside so jobs overlap on everything else.
"""

from __future__ import annotations

import asyncio

slot: asyncio.Semaphore = asyncio.Semaphore(1)
