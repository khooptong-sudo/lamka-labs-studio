"""One card, one holder. No GPU, no network, no subprocesses."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.storyboard import Frame, Storyboard


def _recorder():
    class Recorder:
        def __init__(self):
            self.entries = 0

        async def __aenter__(self):
            self.entries += 1

        async def __aexit__(self, *exc):
            return False

    return Recorder()


async def test_slot_serializes_two_holders():
    from app import gpu

    order: list[str] = []

    async def hold(name: str):
        async with gpu.slot:
            order.append(f"{name}-in")
            await asyncio.sleep(0.01)
            order.append(f"{name}-out")

    await asyncio.gather(hold("a"), hold("b"))
    assert order in (
        ["a-in", "a-out", "b-in", "b-out"],
        ["b-in", "b-out", "a-in", "a-out"],
    )


async def test_local_frame_planning_holds_the_slot(monkeypatch, tmp_path: Path):
    import app.youtube as youtube

    rec = _recorder()
    monkeypatch.setattr(youtube, "gpu", SimpleNamespace(slot=rec))
    monkeypatch.setattr(
        "app.localllm.plan_frame",
        AsyncMock(return_value=({"archetype": "stat_card"}, False)),
    )

    board = Storyboard(meta={"title": "T", "description": "D"})
    board.frames = [Frame(index=1, title="S1", voiceover="v", scene="s")]
    await youtube._generate_frame_compositions_local(board, tmp_path)
    assert rec.entries == 1


async def test_cinematic_comfyui_path_holds_the_slot_but_gemini_does_not(
    tmp_path, monkeypatch
):
    import app.scene3d.backend as backend

    rec = _recorder()
    monkeypatch.setattr(backend, "gpu", SimpleNamespace(slot=rec))
    monkeypatch.setattr(backend, "_generate_cinematic_image", AsyncMock())

    def board():
        b = Storyboard(meta={"title": "T", "description": "D"})
        b.frames = [Frame(index=1, title="S1", voiceover="v", scene="s", duration=5.0)]
        return b

    monkeypatch.setenv("GEMINI_API_KEY", "k")
    await backend.build_cinematic_frames(board(), tmp_path, provider="gemini")
    assert rec.entries == 0

    monkeypatch.setenv("COMFYUI_BASE_URL", "http://127.0.0.1:8188")
    monkeypatch.setenv("COMFYUI_CHECKPOINT_NAME", "test.safetensors")
    await backend.build_cinematic_frames(board(), tmp_path, provider="comfyui")
    assert rec.entries == 1
