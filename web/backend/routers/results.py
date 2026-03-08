"""
Results retrieval and export API router.
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from ..models.schemas import RunListResponse, RunDetail
from ..services.result_service import list_runs, get_run_detail, get_taxonomy_json, export_results_to_excel

router = APIRouter(prefix="/api/results", tags=["Results"])


@router.get("/list", response_model=RunListResponse)
async def list_all_runs(dataset_folder: str = Query(default="", description="Filter by dataset folder")):
    """List all classification runs."""
    runs = list_runs(dataset_folder if dataset_folder else None)
    return RunListResponse(runs=runs, total=len(runs))


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(run_id: str):
    """Get detailed results for a classification run."""
    detail = get_run_detail(run_id)
    if not detail:
        raise HTTPException(404, f"Run not found: {run_id}")
    return detail


@router.get("/{run_id}/taxonomy")
async def get_taxonomy(run_id: str, dimension: str = Query(default="", description="Specific dimension")):
    """Get taxonomy tree for a run."""
    tree = get_taxonomy_json(run_id, dimension if dimension else None)
    if tree is None:
        raise HTTPException(404, "No taxonomy data found")
    return tree


@router.get("/{run_id}/download")
async def download_results(run_id: str):
    """Download classification results as Excel."""
    output_path = export_results_to_excel(run_id)
    if not output_path or not output_path.exists():
        raise HTTPException(404, "No results to export")

    return FileResponse(
        path=str(output_path),
        filename=f"results_{run_id}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
