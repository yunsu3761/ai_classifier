"""
Classification execution API router.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..models.schemas import ClassifyRequest, ClassifyProgress, RunStatus
from ..services.classify_service import start_classification
from ..core.events import get_tracker, sse_generator

router = APIRouter(prefix="/api/classify", tags=["Classification"])


@router.post("/run")
async def run_classification(request: ClassifyRequest):
    """Start a classification run. Returns a run_id for tracking progress."""
    if not request.selected_dimensions:
        raise HTTPException(400, "At least one dimension must be selected")

    run_id = start_classification(request)
    return {
        "run_id": run_id,
        "status": "running",
        "message": "Classification started. Use /api/classify/progress/{run_id} for updates.",
    }


@router.get("/progress/{run_id}")
async def get_progress(run_id: str):
    """Get current progress of a classification run (polling)."""
    tracker = get_tracker(run_id)
    return ClassifyProgress(**tracker.to_dict())


@router.get("/progress/{run_id}/stream")
async def stream_progress(run_id: str):
    """Stream real-time progress via SSE."""
    return StreamingResponse(
        sse_generator(run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/cancel/{run_id}")
async def cancel_classification(run_id: str):
    """Cancel a running classification."""
    tracker = get_tracker(run_id)
    if tracker.status == "running":
        tracker.update(status="cancelled", current_step="Cancelled by user")
        return {"message": "Cancellation requested"}
    return {"message": f"Run is not active (status: {tracker.status})"}
