"""Shared LLM surface for the whole worker.

P2a builds it for story scoring; P2b's drafter and both compliance-gate layers
consume it unchanged. `youtube.py`'s two hand-rolled provider paths are a
documented retrofit, scheduled for the end of P2b. See the Follow-up debt
section of the P2a design doc.
"""

from app.llm.router import complete_json

__all__ = ["complete_json"]
