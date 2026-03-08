"""
Classification execution API router with concurrency info.
"""
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import StreamingResponse

from ..models.schemas import ClassifyRequest, ClassifyProgress
from ..services.classify_service import start_classification, estimate_time
from ..core.events import get_tracker, sse_generator, get_queue_info, clear_all_run_slots
from ..core.config import DATASETS_DIR

router = APIRouter(prefix="/api/classify", tags=["Classification"])


@router.post("/run")
async def run_classification(request: ClassifyRequest, x_user_id: str = Header(default="default")):
    """Start a classification run (respects concurrency limit)."""
    if not request.selected_dimensions:
        raise HTTPException(400, "At least one dimension must be selected")

    result = start_classification(request, user_id=x_user_id)

    if result.get("status") == "rejected":
        raise HTTPException(429, result["message"])

    return result


@router.get("/progress/{run_id}")
async def get_progress(run_id: str):
    """Get current progress (polling)."""
    tracker = get_tracker(run_id)
    return ClassifyProgress(**tracker.to_dict())


@router.get("/progress/{run_id}/stream")
async def stream_progress(run_id: str):
    """Stream real-time progress via SSE."""
    return StreamingResponse(
        sse_generator(run_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/cancel/{run_id}")
async def cancel_classification(run_id: str):
    """Cancel a running classification."""
    tracker = get_tracker(run_id)
    if tracker.status == "running":
        tracker.request_cancel()
        return {"message": "Cancel requested. Will stop at next checkpoint."}
    return {"message": f"Run is not active (status: {tracker.status})"}


@router.get("/queue")
async def queue_status():
    """Get current run queue status."""
    return get_queue_info()


@router.post("/queue/clear")
async def clear_queue():
    """Emergency reset: clear all active run slots if they become stuck."""
    released = clear_all_run_slots()
    return {"message": f"Cleared {released} stuck run slots.", "success": True}


@router.get("/estimate")
async def estimate_run_time(
    doc_count: int = 0,
    dim_count: int = 1,
    max_depth: int = 2,
    test_samples: int = 0,
    dataset_folder: str = "web_custom_data",
    x_user_id: str = Header(default="default"),
):
    """Estimate classification time. test_samples > 0 limits doc count."""
    # Get actual doc count from internal.txt
    total_docs = 0
    data_dir = DATASETS_DIR / x_user_id / dataset_folder.lower().replace(" ", "_")
    internal_path = data_dir / "internal.txt"
    if internal_path.exists():
        total_docs = sum(1 for line in open(internal_path, "r", encoding="utf-8") if line.strip())

    if doc_count == 0:
        doc_count = total_docs

    # Apply test_samples limit
    effective_docs = doc_count
    if test_samples > 0 and test_samples < doc_count:
        effective_docs = test_samples

    est = estimate_time(effective_docs, dim_count, max_depth)
    return {
        "total_documents": total_docs,
        "effective_documents": effective_docs,
        "test_samples": test_samples,
        "dimension_count": dim_count,
        "estimated_seconds": est,
        "estimated_display": f"{int(est // 3600)}h {int((est % 3600) // 60)}m" if est > 3600 else f"{int(est // 60)}m {int(est % 60)}s",
        "queue_info": get_queue_info(),
    }
