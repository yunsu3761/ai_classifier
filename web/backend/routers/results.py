"""
Results API router — user-scoped.
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Header
from fastapi.responses import FileResponse

from ..core.config import DATASETS_DIR
from ..models.schemas import RunListResponse, RunDetail
from ..services.result_service import (
    list_runs, get_run_detail, get_taxonomy_json, 
    export_results_to_excel, export_results_to_txt, get_results_table_data
)

router = APIRouter(prefix="/api/results", tags=["Results"])


@router.get("/list", response_model=RunListResponse)
async def list_all_runs(dataset_folder: str = Query(default=""), x_user_id: str = Header(default="default")):
    """List classification runs for this user."""
    runs = list_runs(dataset_folder if dataset_folder else None, user_id=x_user_id)
    return RunListResponse(runs=runs, total=len(runs))


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(run_id: str, x_user_id: str = Header(default="default")):
    detail = get_run_detail(run_id, user_id=x_user_id)
    if not detail:
        raise HTTPException(404, f"Run not found: {run_id}")
    return detail


@router.get("/{run_id}/taxonomy")
async def get_taxonomy(run_id: str, dimension: str = Query(default=""), x_user_id: str = Header(default="default")):
    tree = get_taxonomy_json(run_id, dimension if dimension else None, user_id=x_user_id)
    if tree is None:
        raise HTTPException(404, "No taxonomy data found")
    return tree


@router.get("/{run_id}/table")
async def get_results_table(run_id: str, x_user_id: str = Header(default="default")):
    """Get flat table data for frontend datagrid."""
    data = get_results_table_data(run_id, user_id=x_user_id)
    if data is None:
        raise HTTPException(404, "No results to show")
    return data

@router.get("/{run_id}/download")
async def download_results(run_id: str, format: str = Query(default="excel"), user_id: str = Query(default=None), x_user_id: str = Header(default="default")):
    """Download results in specified format (excel or txt)."""
    # Direct browser downloads don't send X-User-Id header, so we rely on the query parameter
    actual_user_id = user_id if user_id else x_user_id
    
    if format.lower() == "txt":
        output_path = export_results_to_txt(run_id, user_id=actual_user_id)
        media_type = "text/tab-separated-values"
        filename = f"results_{run_id}.txt"
    else:
        output_path = export_results_to_excel(run_id, user_id=actual_user_id)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"results_{run_id}.xlsx"
        
    if not output_path or not output_path.exists():
        raise HTTPException(404, "No results to export")
        
    return FileResponse(
        path=str(output_path),
        filename=filename,
        media_type=media_type,
    )
