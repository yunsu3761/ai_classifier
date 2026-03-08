"""
File scanning and type detection service.
"""
import os
from pathlib import Path
from typing import List, Optional

from ..core.config import UPLOAD_DIR, DATASETS_DIR
from ..models.schemas import FileInfo, FileType


# Known column patterns for file type detection
PATENT_DATASET_INDICATORS = [
    "발명의 명칭", "요약", "대표청구항", "출원번호", "AI 요약",
    "Original CPC Main", "Original IPC Main", "기술분야 요약",
]

TECH_DEFINITION_INDICATORS = [
    "Level1", "Level1_Dimension_Name", "Level1_Dimension_Definitions",
    "Topic", "기술명", "정의", "예시", "설명",
]


def detect_file_type(filepath: Path) -> FileType:
    """Detect the type of a file based on extension and content."""
    suffix = filepath.suffix.lower()

    if suffix in (".yaml", ".yml"):
        return FileType.YAML_CONFIG
    elif suffix == ".txt":
        return FileType.TXT_FILE
    elif suffix in (".xlsx", ".xls"):
        return _detect_excel_type(filepath)
    return FileType.UNKNOWN


def _detect_excel_type(filepath: Path) -> FileType:
    """Detect whether an Excel file is a patent dataset or tech definition."""
    try:
        import pandas as pd
        df = pd.read_excel(filepath, nrows=0)
        columns = [str(c).strip() for c in df.columns]

        patent_score = sum(1 for ind in PATENT_DATASET_INDICATORS if any(ind in c for c in columns))
        tech_score = sum(1 for ind in TECH_DEFINITION_INDICATORS if any(ind in c for c in columns))

        if patent_score >= 3:
            return FileType.PATENT_DATASET
        elif tech_score >= 2:
            return FileType.TECH_DEFINITION
        return FileType.UNKNOWN
    except Exception:
        return FileType.UNKNOWN


def scan_directory(folder_path: Optional[str] = None) -> List[FileInfo]:
    """Scan a directory and return info about all recognized files."""
    target_dir = Path(folder_path) if folder_path else UPLOAD_DIR
    if not target_dir.exists():
        return []

    results: List[FileInfo] = []
    extensions = {".xlsx", ".xls", ".txt", ".yaml", ".yml", ".csv"}

    for entry in target_dir.iterdir():
        if entry.is_file() and entry.suffix.lower() in extensions:
            file_type = detect_file_type(entry)
            info = FileInfo(
                filename=entry.name,
                filepath=str(entry),
                file_type=file_type,
                size_bytes=entry.stat().st_size,
                last_modified=str(entry.stat().st_mtime),
            )

            # Get column info for Excel files
            if entry.suffix.lower() in (".xlsx", ".xls"):
                try:
                    import pandas as pd
                    df = pd.read_excel(entry, nrows=5)
                    info.detected_columns = [str(c).strip() for c in df.columns]
                    info.row_count = len(pd.read_excel(entry))
                except Exception:
                    pass

            results.append(info)

    return results


def get_file_preview(filepath: str, max_rows: int = 20) -> dict:
    """Return a preview of file contents."""
    p = Path(filepath)
    if not p.exists():
        return {"columns": [], "rows": [], "total_rows": 0}

    suffix = p.suffix.lower()

    if suffix in (".xlsx", ".xls"):
        import pandas as pd
        df = pd.read_excel(p)
        df.columns = [str(c).strip() for c in df.columns]
        preview_df = df.head(max_rows)
        return {
            "columns": list(df.columns),
            "rows": preview_df.fillna("").to_dict(orient="records"),
            "total_rows": len(df),
        }
    elif suffix == ".txt":
        lines = []
        with open(p, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= max_rows:
                    break
                lines.append(line.strip())
        total = sum(1 for _ in open(p, "r", encoding="utf-8"))
        return {
            "columns": ["line"],
            "rows": [{"line": l} for l in lines],
            "total_rows": total,
        }

    return {"columns": [], "rows": [], "total_rows": 0}
