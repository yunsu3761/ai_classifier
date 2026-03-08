"""
Preprocessing API router — Excel → txt conversion, column mapping.
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..core.config import UPLOAD_DIR, DATASETS_DIR
from ..models.schemas import PreprocessRequest, PreprocessResponse, ColumnMapping
from ..services.excel_parser import auto_detect_columns, parse_patent_excel, parse_tech_definition_excel
from ..services.text_composer import convert_patent_excel_to_txt, convert_tech_definition_to_txt

router = APIRouter(prefix="/api/preprocess", tags=["Preprocessing"])


@router.post("/columns", response_model=ColumnMapping)
async def detect_columns(file_id: str):
    """Auto-detect column mappings from a patent dataset Excel file."""
    # Find the file
    filepath = _find_file(file_id)
    if not filepath:
        raise HTTPException(404, f"File not found: {file_id}")

    import pandas as pd
    df = pd.read_excel(filepath, nrows=5)
    df.columns = [str(c).strip() for c in df.columns]
    mapping = auto_detect_columns(df)
    return mapping


@router.post("/convert", response_model=PreprocessResponse)
async def convert_to_txt(request: PreprocessRequest):
    """Convert Excel file to internal.txt format."""
    filepath = _find_file(request.file_id)
    if not filepath:
        raise HTTPException(404, f"File not found: {request.file_id}")

    output_dir = DATASETS_DIR / request.dataset_folder.lower().replace(" ", "_")
    suffix = filepath.suffix.lower()

    if suffix not in (".xlsx", ".xls"):
        raise HTTPException(400, "Only Excel files can be converted")

    try:
        import pandas as pd
        df = pd.read_excel(filepath)
        df.columns = [str(c).strip() for c in df.columns]

        # Auto-detect or use provided mapping
        if request.column_mapping:
            mapping = request.column_mapping
        else:
            mapping = auto_detect_columns(df)

        # Check if it's a patent dataset or tech definition
        if mapping.patent_id_col or mapping.title_col:
            result = convert_patent_excel_to_txt(df, mapping, output_dir)
        else:
            result = convert_tech_definition_to_txt(df, output_dir)

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
async def preprocess_status(dataset_folder: str = "web_custom_data"):
    """Check preprocessing status for a dataset folder."""
    data_dir = DATASETS_DIR / dataset_folder.lower().replace(" ", "_")
    internal_path = data_dir / "internal.txt"

    if not internal_path.exists():
        return {"has_data": False, "document_count": 0}

    count = sum(1 for line in open(internal_path, "r", encoding="utf-8") if line.strip())
    return {
        "has_data": count > 0,
        "document_count": count,
        "internal_txt_path": str(internal_path),
        "last_modified": internal_path.stat().st_mtime,
    }


def _find_file(file_id: str) -> Path | None:
    """Find a file by its ID (prefix) in the upload directory."""
    if not UPLOAD_DIR.exists():
        return None

    for f in UPLOAD_DIR.iterdir():
        if f.is_file() and f.name.startswith(file_id):
            return f

    # Also check if file_id is a full filename
    direct = UPLOAD_DIR / file_id
    if direct.exists():
        return direct

    return None
