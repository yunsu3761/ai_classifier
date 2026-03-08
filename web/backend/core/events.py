"""
SSE (Server-Sent Events) utilities for real-time progress streaming.
"""
import asyncio
import json
from typing import AsyncGenerator


class ProgressTracker:
    """Thread-safe progress tracker that can be read via SSE."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.status = "pending"
        self.progress_pct = 0.0
        self.current_step = ""
        self.current_dimension = ""
        self.logs: list[str] = []
        self.error: str | None = None
        self._subscribers: list[asyncio.Queue] = []

    def update(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
        if "log" in kwargs:
            self.logs.append(kwargs["log"])
        self._notify()

    def add_log(self, message: str):
        self.logs.append(message)
        self._notify()

    def _notify(self):
        data = self.to_dict()
        for q in self._subscribers:
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                pass

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._subscribers:
            self._subscribers.remove(q)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "progress_pct": self.progress_pct,
            "current_step": self.current_step,
            "current_dimension": self.current_dimension,
            "logs": self.logs[-50:],  # Last 50 lines
            "error": self.error,
        }


# Global registry of active progress trackers
_trackers: dict[str, ProgressTracker] = {}


def get_tracker(run_id: str) -> ProgressTracker:
    if run_id not in _trackers:
        _trackers[run_id] = ProgressTracker(run_id)
    return _trackers[run_id]


def remove_tracker(run_id: str):
    _trackers.pop(run_id, None)


async def sse_generator(run_id: str) -> AsyncGenerator[str, None]:
    """Async generator that yields SSE-formatted events."""
    tracker = get_tracker(run_id)
    queue = tracker.subscribe()
    try:
        # Send initial state
        yield f"data: {json.dumps(tracker.to_dict())}\n\n"
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(data)}\n\n"
                if data.get("status") in ("completed", "failed", "cancelled"):
                    break
            except asyncio.TimeoutError:
                # Keep-alive
                yield f": keepalive\n\n"
    finally:
        tracker.unsubscribe(queue)
