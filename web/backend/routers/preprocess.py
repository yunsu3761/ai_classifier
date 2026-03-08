"""
Preprocessing API router — Excel to txt, user-scoped.
"""
import gc
from pathlib import Path

from fastapi import APIRouter, HTTPException, Header

from ..core.config import UPLOAD_DIR, CONVERTED_DIR, DATASETS_DIR
from ..models.schemas import PreprocessRequest, PreprocessResponse, ColumnMapping
from ..services.excel_parser import auto_detect_columns
from ..services.text_composer import convert_patent_excel_to_txt, convert_tech_definition_to_txt

router = APIRouter(prefix="/api/preprocess", tags=["Preprocessing"])


@router.post("/columns", response_model=ColumnMapping)
async def detect_columns(file_id: str, x_user_id: str = Header(default="default")):
    """Auto-detect column mappings from Excel."""
    filepath = _find_file(file_id, x_user_id)
    if not filepath:
        raise HTTPException(404, f"File not found: {file_id}")

    import pandas as pd
    df = pd.read_excel(filepath, nrows=5)
    df.columns = [str(c).strip() for c in df.columns]
    return auto_detect_columns(df)


@router.post("/convert", response_model=PreprocessResponse)
async def convert_to_txt(request: PreprocessRequest, x_user_id: str = Header(default="default")):
    """Convert Excel to internal.txt (user-scoped output)."""
    filepath = _find_file(request.file_id, x_user_id)
    if not filepath:
        raise HTTPException(404, f"File not found: {request.file_id}")

    # User-scoped output directory
    output_dir = DATASETS_DIR / x_user_id / request.dataset_folder.lower().replace(" ", "_")

    if filepath.suffix.lower() not in (".xlsx", ".xls"):
        raise HTTPException(400, "Only Excel files can be converted")

    try:
        import pandas as pd
        df = pd.read_excel(filepath)
        df.columns = [str(c).strip() for c in df.columns]

        mapping = request.column_mapping if request.column_mapping else auto_detect_columns(df)

        if mapping.patent_id_col or mapping.title_col:
            result = convert_patent_excel_to_txt(df, mapping, output_dir)
        else:
            result = convert_tech_definition_to_txt(df, output_dir)

        # Also save a copy in user's converted dir for future reuse
        converted_dir = CONVERTED_DIR / x_user_id
        converted_dir.mkdir(parents=True, exist_ok=True)
        import shutil
        converted_path = converted_dir / f"internal_{request.file_id[:8]}.txt"
        shutil.copy2(result["path"], str(converted_path))

        # Free memory
        del df
        gc.collect()

        return PreprocessResponse(
            success=True,
            internal_txt_path=result["path"],
            total_documents=result["count"],
            message=result["message"],
            column_mapping=mapping,
        )
    except Exception as e:
        return PreprocessResponse(success=False, message=str(e))


@router.get("/status")
async def preprocess_status(dataset_folder: str = "web_custom_data", x_user_id: str = Header(default="default")):
    """Check preprocessing status for a user's dataset folder."""
    data_dir = DATASETS_DIR / x_user_id / dataset_folder.lower().replace(" ", "_")
    internal_path = data_dir / "internal.txt"

    if not internal_path.exists():
        return {"has_data": False, "document_count": 0, "path": ""}

    count = sum(1 for line in open(internal_path, "r", encoding="utf-8") if line.strip())
    return {
        "has_data": count > 0,
        "document_count": count,
        "internal_txt_path": str(internal_path),
        "last_modified": internal_path.stat().st_mtime,
    }


def _find_file(file_id: str, user_id: str) -> Path | None:
    """Find a file by ID prefix in user's directories."""
    for base in [UPLOAD_DIR / user_id, CONVERTED_DIR / user_id]:
        if not base.exists():
            continue
        for f in base.iterdir():
            if f.is_file() and (f.name.startswith(file_id) or f.name == file_id):
                return f
    return None
