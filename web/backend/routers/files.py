"""
File management API router.
"""
import os
import shutil
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, UploadFile, File, HTTPException, Query

from ..core.config import UPLOAD_DIR
from ..models.schemas import FileInfo, FileListResponse, FilePreview
from ..services.file_service import scan_directory, get_file_preview, detect_file_type

router = APIRouter(prefix="/api/files", tags=["Files"])


@router.post("/upload", response_model=FileInfo)
async def upload_file(file: UploadFile = File(...)):
    """Upload an Excel, TXT, YAML, or CSV file."""
    allowed_ext = {".xlsx", ".xls", ".txt", ".yaml", ".yml", ".csv", ".json", ".jsonl"}
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed_ext:
        raise HTTPException(400, f"Unsupported file type: {suffix}")

    # Generate unique filename
    file_id = str(uuid.uuid4())[:8]
    safe_name = f"{file_id}_{file.filename}"
    dest = UPLOAD_DIR / safe_name

    with open(dest, "wb") as f:
        content = await file.read()
        f.write(content)

    file_type = detect_file_type(dest)
    info = FileInfo(
        filename=safe_name,
        filepath=str(dest),
        file_type=file_type,
        size_bytes=dest.stat().st_size,
    )

    # Get column info for Excel
    if suffix in (".xlsx", ".xls"):
        try:
            import pandas as pd
            df = pd.read_excel(dest, nrows=0)
            info.detected_columns = [str(c).strip() for c in df.columns]
            info.row_count = len(pd.read_excel(dest))
        except Exception:
            pass

    return info


@router.get("/scan", response_model=FileListResponse)
async def scan_files(folder: str = Query(default="", description="Folder path to scan")):
    """Scan a directory for recognized files."""
    folder_path = folder if folder else None
    files = scan_directory(folder_path)
    return FileListResponse(files=files, total=len(files))


@router.get("/list", response_model=FileListResponse)
async def list_files():
    """List all uploaded files."""
    files = scan_directory(str(UPLOAD_DIR))
    return FileListResponse(files=files, total=len(files))


@router.get("/{filename}/preview", response_model=FilePreview)
async def preview_file(filename: str, max_rows: int = Query(default=20, le=100)):
    """Preview file contents."""
    filepath = UPLOAD_DIR / filename
    if not filepath.exists():
        raise HTTPException(404, f"File not found: {filename}")
    data = get_file_preview(str(filepath), max_rows)
    return FilePreview(**data)


@router.delete("/{filename}")
async def delete_file(filename: str):
    """Delete an uploaded file."""
    filepath = UPLOAD_DIR / filename
    if not filepath.exists():
        raise HTTPException(404, f"File not found: {filename}")
    os.remove(filepath)
    return {"message": f"Deleted: {filename}"}
