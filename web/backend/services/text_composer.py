"""
Priority-based text composition service.
Combines patent text fields in priority order to create optimized reference text.
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from ..models.schemas import ColumnMapping


def compose_patent_text(row: pd.Series, mapping: ColumnMapping) -> Dict[str, str]:
    """
    Compose a patent document's text from multiple fields based on priority.

    Returns:
        {"Patent_ID": "...", "Title": "...", "Abstract": "..."}

    The "Abstract" field is a composite of all available text fields
    ordered by priority, designed to be compatible with the existing
    construct_dataset() function in main2.py.
    """
    def get_field(col_name: Optional[str]) -> str:
        if col_name and col_name in row.index:
            val = row[col_name]
            if pd.notna(val):
                return str(val).strip()
        return ""

    # Patent ID
    patent_id = get_field(mapping.patent_id_col) or "UNKNOWN"

    # Title (발명의 명칭)
    title = get_field(mapping.title_col) or "Untitled"

    # Build abstract from priority fields
    sections = []

    # Primary text fields
    abstract_text = get_field(mapping.abstract_col)
    if abstract_text:
        sections.append(f"[요약] {abstract_text}")

    claims_text = get_field(mapping.claims_col)
    if claims_text:
        sections.append(f"[대표청구항] {claims_text}")

    indep_claims = get_field(mapping.independent_claims_col)
    if indep_claims:
        sections.append(f"[독립청구항] {indep_claims}")

    # AI & analysis summaries
    ai_summary = get_field(mapping.ai_summary_col)
    if ai_summary:
        sections.append(f"[AI요약] {ai_summary}")

    tech_field = get_field(mapping.tech_field_summary_col)
    if tech_field:
        sections.append(f"[기술분야] {tech_field}")

    problem = get_field(mapping.problem_summary_col)
    if problem:
        sections.append(f"[해결과제] {problem}")

    solution = get_field(mapping.solution_summary_col)
    if solution:
        sections.append(f"[해결수단] {solution}")

    feature = get_field(mapping.feature_summary_col)
    if feature:
        sections.append(f"[특징] {feature}")

    effect = get_field(mapping.effect_summary_col)
    if effect:
        sections.append(f"[효과] {effect}")

    # Classification codes as metadata tags
    cpc_main = get_field(mapping.cpc_main_col)
    ipc_main = get_field(mapping.ipc_main_col)
    if cpc_main or ipc_main:
        code_parts = []
        if cpc_main:
            code_parts.append(f"CPC: {cpc_main}")
        if ipc_main:
            code_parts.append(f"IPC: {ipc_main}")
        sections.append(f"[분류코드] {'; '.join(code_parts)}")

    abstract = "\n".join(sections) if sections else title

    return {
        "Patent_ID": patent_id,
        "Title": title,
        "Abstract": abstract,
    }


def convert_patent_excel_to_txt(
    df: pd.DataFrame,
    mapping: ColumnMapping,
    output_dir: Path,
    output_filename: str = "internal.txt",
) -> dict:
    """
    Convert a patent dataset DataFrame to internal.txt (JSON Lines format).

    Returns:
        {"path": str, "count": int, "message": str}
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_filename
    count = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for _, row in df.iterrows():
            doc = compose_patent_text(row, mapping)
            if doc["Title"] != "Untitled" or doc["Abstract"] != doc["Title"]:
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
                count += 1

    return {
        "path": str(output_path),
        "count": count,
        "message": f"Successfully converted {count} patent documents",
    }


def convert_tech_definition_to_txt(
    df: pd.DataFrame,
    output_dir: Path,
    output_filename: str = "tech_definitions.txt",
) -> dict:
    """
    Convert a technology definition DataFrame to a text file.

    Returns:
        {"path": str, "count": int, "message": str}
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_filename
    count = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for _, row in df.iterrows():
            parts = []
            for col in df.columns:
                val = row[col]
                if pd.notna(val) and str(val).strip():
                    parts.append(f"{col}: {str(val).strip()}")
            if parts:
                doc = {"text": " | ".join(parts)}
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
                count += 1

    return {
        "path": str(output_path),
        "count": count,
        "message": f"Successfully converted {count} tech definitions",
    }
