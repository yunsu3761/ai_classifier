"""
File management API router — with Windows-safe deletion.
"""
import os
import gc
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Header
from typing import Optional

from ..core.config import UPLOAD_DIR, CONVERTED_DIR
from ..models.schemas import FileInfo, FileListResponse, FilePreview
from ..services.file_service import scan_directory, get_file_preview, detect_file_type

router = APIRouter(prefix="/api/files", tags=["Files"])


def _get_user_upload_dir(user_id: str) -> Path:
    d = UPLOAD_DIR / user_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_user_converted_dir(user_id: str) -> Path:
    d = CONVERTED_DIR / user_id
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.post("/upload", response_model=FileInfo)
async def upload_file(file: UploadFile = File(...), x_user_id: str = Header(default="default")):
    """Upload an Excel, TXT, YAML, or CSV file."""
    allowed_ext = {".xlsx", ".xls", ".txt", ".yaml", ".yml", ".csv", ".json", ".jsonl"}
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed_ext:
        raise HTTPException(400, f"Unsupported file type: {suffix}")

    upload_dir = _get_user_upload_dir(x_user_id)
    file_id = str(uuid.uuid4())[:8]
    safe_name = f"{file_id}_{file.filename}"
    dest = upload_dir / safe_name

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

    if suffix in (".xlsx", ".xls"):
        try:
            import pandas as pd
            df = pd.read_excel(dest, nrows=0)
            info.detected_columns = [str(c).strip() for c in df.columns]
            info.row_count = len(pd.read_excel(dest, usecols=[0]))
        except Exception:
            pass

    return info


@router.get("/list", response_model=FileListResponse)
async def list_files(x_user_id: str = Header(default="default")):
    """List uploaded files for this user."""
    upload_dir = _get_user_upload_dir(x_user_id)
    files = scan_directory(str(upload_dir))
    return FileListResponse(files=files, total=len(files))


@router.get("/converted", response_model=FileListResponse)
async def list_converted(x_user_id: str = Header(default="default")):
    """List converted files for this user."""
    converted_dir = _get_user_converted_dir(x_user_id)
    files = scan_directory(str(converted_dir))
    return FileListResponse(files=files, total=len(files))


@router.get("/{filename}/preview", response_model=FilePreview)
async def preview_file(filename: str, max_rows: int = Query(default=20, le=100), x_user_id: str = Header(default="default")):
    """Preview file contents."""
    filepath = _find_user_file(filename, x_user_id)
    if not filepath:
        raise HTTPException(404, f"File not found: {filename}")
    data = get_file_preview(str(filepath), max_rows)
    return FilePreview(**data)


@router.delete("/{filename}")
async def delete_file(filename: str, x_user_id: str = Header(default="default")):
    """Delete an uploaded or converted file (Windows-safe)."""
    filepath = _find_user_file(filename, x_user_id)
    if not filepath:
        raise HTTPException(404, f"File not found: {filename}")

    # Windows-safe deletion: force garbage collection to release file handles
    gc.collect()
    try:
        os.remove(str(filepath))
        return {"message": f"Deleted: {filename}"}
    except PermissionError:
        # Try rename-then-delete trick for Windows locked files
        try:
            tmp = filepath.with_suffix('.deleting')
            os.rename(str(filepath), str(tmp))
            os.remove(str(tmp))
            return {"message": f"Deleted: {filename}"}
        except Exception as e:
            raise HTTPException(500, f"Cannot delete (file may be in use): {e}")
    except Exception as e:
        raise HTTPException(500, f"Delete error: {e}")


def _find_user_file(filename: str, user_id: str) -> Optional[Path]:
    """Find a file in user's upload or converted directory."""
    for base_dir in [_get_user_upload_dir(user_id), _get_user_converted_dir(user_id)]:
        p = base_dir / filename
        if p.exists():
            return p
    return None
