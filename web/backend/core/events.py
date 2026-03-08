"""
SSE (Server-Sent Events) utilities for real-time progress streaming.
Includes concurrency limiter for classification runs.
"""
import asyncio
import json
import threading
from typing import AsyncGenerator, Optional

from .config import MAX_CONCURRENT_RUNS


class ProgressTracker:
    """Thread-safe progress tracker that can be read via SSE."""

    def __init__(self, run_id: str, user_id: str = "default"):
        self.run_id = run_id
        self.user_id = user_id
        self.status = "pending"
        self.progress_pct = 0.0
        self.current_step = ""
        self.current_dimension = ""
        self.logs: list[str] = []
        self.error: Optional[str] = None
        self.estimated_seconds: float = 0.0
        self.elapsed_seconds: float = 0.0
        self._subscribers: list[asyncio.Queue] = []
        self._cancel_event = threading.Event()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def request_cancel(self):
        self._cancel_event.set()
        self.update(status="cancelled", current_step="Cancelled by user")

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
            "user_id": self.user_id,
            "status": self.status,
            "progress_pct": self.progress_pct,
            "current_step": self.current_step,
            "current_dimension": self.current_dimension,
            "logs": self.logs[-50:],
            "error": self.error,
            "estimated_seconds": self.estimated_seconds,
            "elapsed_seconds": self.elapsed_seconds,
        }


# Global registry
_trackers: dict[str, ProgressTracker] = {}
_run_semaphore = threading.Semaphore(MAX_CONCURRENT_RUNS)
_active_runs_lock = threading.Lock()
_active_runs: dict[str, str] = {}  # run_id -> user_id


def get_tracker(run_id: str) -> ProgressTracker:
    if run_id not in _trackers:
        _trackers[run_id] = ProgressTracker(run_id)
    return _trackers[run_id]


def create_tracker(run_id: str, user_id: str) -> ProgressTracker:
    tracker = ProgressTracker(run_id, user_id)
    _trackers[run_id] = tracker
    return tracker


def remove_tracker(run_id: str):
    _trackers.pop(run_id, None)


def try_acquire_run_slot(run_id: str, user_id: str) -> bool:
    """Try to acquire a slot. Returns False if at capacity."""
    acquired = _run_semaphore.acquire(blocking=False)
    if acquired:
        with _active_runs_lock:
            _active_runs[run_id] = user_id
    return acquired


def release_run_slot(run_id: str):
    with _active_runs_lock:
        if run_id in _active_runs:
            del _active_runs[run_id]
            _run_semaphore.release()


def clear_all_run_slots():
    """Emergency reset for stuck slots."""
    with _active_runs_lock:
        to_release = len(_active_runs)
        _active_runs.clear()
        for _ in range(to_release):
            _run_semaphore.release()
        return to_release


def get_active_run_count() -> int:
    with _active_runs_lock:
        return len(_active_runs)


def get_queue_info() -> dict:
    with _active_runs_lock:
        return {
            "active_runs": len(_active_runs),
            "max_concurrent": MAX_CONCURRENT_RUNS,
            "available_slots": MAX_CONCURRENT_RUNS - len(_active_runs),
        }


def get_user_runs(user_id: str) -> list[ProgressTracker]:
    return [t for t in _trackers.values() if t.user_id == user_id]


async def sse_generator(run_id: str) -> AsyncGenerator[str, None]:
    """Async generator that yields SSE-formatted events."""
    tracker = get_tracker(run_id)
    queue = tracker.subscribe()
    try:
        yield f"data: {json.dumps(tracker.to_dict())}\n\n"
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(data)}\n\n"
                if data.get("status") in ("completed", "failed", "cancelled"):
                    break
            except asyncio.TimeoutError:
                yield f": keepalive\n\n"
    finally:
        tracker.unsubscribe(queue)
