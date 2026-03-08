"""
Excel column auto-mapping and parsing service for patent datasets.
"""
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from ..models.schemas import ColumnMapping


# ─── Column Pattern Matchers ─────────────────────────────

COLUMN_PATTERNS: Dict[str, List[str]] = {
    "title_col": ["발명의 명칭", "발명의명칭", "title", "발명 명칭"],
    "abstract_col": ["요약", "abstract", "요약(번역문)"],
    "claims_col": ["대표청구항", "대표 청구항", "representative claim"],
    "independent_claims_col": ["독립청구항", "독립 청구항", "independent claim"],
    "ai_summary_col": ["AI 요약", "AI요약", "ai_summary", "ai summary"],
    "tech_field_summary_col": ["기술분야 요약", "기술분야요약", "technical field summary"],
    "problem_summary_col": ["해결과제 요약", "해결과제요약", "problem summary"],
    "solution_summary_col": ["해결수단 요약", "해결수단요약", "solution summary"],
    "feature_summary_col": ["특징 요약", "특징요약", "feature summary"],
    "effect_summary_col": ["효과 요약", "효과요약", "effect summary"],
    "cpc_main_col": ["Original CPC Main", "CPC Main", "cpc_main"],
    "cpc_all_col": ["Original CPC All", "CPC All", "cpc_all"],
    "ipc_main_col": ["Original IPC Main", "IPC Main", "ipc_main"],
    "ipc_all_col": ["Original IPC All", "IPC All", "ipc_all"],
    "patent_id_col": ["출원번호", "patent_ids", "patent_id", "application_number"],
    "applicant_col": ["출원인", "applicant", "출원인(원어)"],
    "filing_date_col": ["출원일", "filing_date", "출원일자"],
    "country_col": ["국가코드", "country_code", "country"],
}


def auto_detect_columns(df: pd.DataFrame) -> ColumnMapping:
    """Automatically detect column mappings from a DataFrame."""
    columns = [str(c).strip() for c in df.columns]
    mapping = {}

    for field_name, patterns in COLUMN_PATTERNS.items():
        for pattern in patterns:
            for col in columns:
                if pattern.lower() in col.lower():
                    mapping[field_name] = col
                    break
            if field_name in mapping:
                break

    return ColumnMapping(**mapping)


def parse_patent_excel(
    filepath: Path,
    column_mapping: Optional[ColumnMapping] = None,
) -> Tuple[pd.DataFrame, ColumnMapping]:
    """Parse a patent dataset Excel file and return normalized DataFrame."""
    df = pd.read_excel(filepath)
    df.columns = [str(c).strip() for c in df.columns]

    if column_mapping is None:
        column_mapping = auto_detect_columns(df)

    return df, column_mapping


def parse_tech_definition_excel(filepath: Path) -> pd.DataFrame:
    """Parse a technology definition Excel file."""
    df = pd.read_excel(filepath)
    df.columns = [str(c).strip() for c in df.columns]
    return df
