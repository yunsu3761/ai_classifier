"""
Result persistence and retrieval service.
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

import pandas as pd

from ..core.config import DATASETS_DIR, SAVE_OUTPUT_DIR
from ..models.schemas import RunSummary, RunDetail, RunStatus


def list_runs(dataset_folder: Optional[str] = None) -> List[RunSummary]:
    """List all classification runs, optionally filtered by dataset folder."""
    runs = []

    search_dirs = []
    if dataset_folder:
        search_dirs.append(DATASETS_DIR / dataset_folder.lower().replace(" ", "_"))
    else:
        # Search all dataset folders
        if DATASETS_DIR.exists():
            for d in DATASETS_DIR.iterdir():
                if d.is_dir():
                    search_dirs.append(d)

    for dir_path in search_dirs:
        if not dir_path.exists():
            continue
        for f in dir_path.glob("run_*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    meta = json.load(fp)
                runs.append(RunSummary(
                    run_id=meta.get("run_id", f.stem.replace("run_", "")),
                    status=RunStatus.COMPLETED,
                    created_at=meta.get("timestamp", ""),
                    topic=meta.get("parameters", {}).get("topic", ""),
                    dataset_folder=meta.get("parameters", {}).get("dataset_folder", ""),
                    model=meta.get("parameters", {}).get("model", ""),
                    total_documents=meta.get("total_documents", 0),
                    dimensions=meta.get("parameters", {}).get("dimensions", []),
                    parameters=meta.get("parameters", {}),
                ))
            except Exception:
                continue

    runs.sort(key=lambda r: r.created_at, reverse=True)
    return runs


def get_run_detail(run_id: str) -> Optional[RunDetail]:
    """Get detailed results for a specific run."""
    # Search for run metadata
    for dir_path in DATASETS_DIR.iterdir():
        if not dir_path.is_dir():
            continue
        meta_file = dir_path / f"run_{run_id}.json"
        if meta_file.exists():
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)

            summary = RunSummary(
                run_id=run_id,
                status=RunStatus.COMPLETED,
                created_at=meta.get("timestamp", ""),
                topic=meta.get("parameters", {}).get("topic", ""),
                dataset_folder=meta.get("parameters", {}).get("dataset_folder", ""),
                model=meta.get("parameters", {}).get("model", ""),
                total_documents=meta.get("total_documents", 0),
                dimensions=meta.get("parameters", {}).get("dimensions", []),
                parameters=meta.get("parameters", {}),
            )

            # Load taxonomy trees
            taxonomy_tree = {}
            dims = meta.get("parameters", {}).get("dimensions", [])
            for dim in dims:
                taxo_file = dir_path / f"final_taxo_{dim}.json"
                if taxo_file.exists():
                    with open(taxo_file, "r", encoding="utf-8") as f:
                        taxonomy_tree[dim] = json.load(f)

            return RunDetail(
                summary=summary,
                taxonomy_tree=taxonomy_tree,
            )

    return None


def get_taxonomy_json(run_id: str, dimension: Optional[str] = None) -> Optional[dict]:
    """Get taxonomy tree JSON for a specific run."""
    detail = get_run_detail(run_id)
    if not detail or not detail.taxonomy_tree:
        return None

    if dimension:
        return detail.taxonomy_tree.get(dimension)
    return detail.taxonomy_tree


def export_results_to_excel(run_id: str) -> Optional[Path]:
    """Export classification results to Excel file."""
    detail = get_run_detail(run_id)
    if not detail:
        return None

    rows = []
    if detail.taxonomy_tree:
        for dim, tree in detail.taxonomy_tree.items():
            _flatten_tree(tree, dim, rows)

    if not rows:
        return None

    df = pd.DataFrame(rows)
    output_dir = SAVE_OUTPUT_DIR / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"results_{run_id}.xlsx"
    df.to_excel(output_path, index=False)
    return output_path


def _flatten_tree(node: dict, dimension: str, rows: list, path: str = ""):
    """Recursively flatten a taxonomy tree into rows."""
    label = node.get("label", "")
    current_path = f"{path} > {label}" if path else label

    # Add papers
    paper_ids = node.get("paper_ids", [])
    example_papers = node.get("example_papers", [])

    if paper_ids:
        for pid in paper_ids:
            rows.append({
                "dimension": dimension,
                "taxonomy_path": current_path,
                "node_label": label,
                "level": node.get("level", 0),
                "description": node.get("description", ""),
                "source": node.get("source", ""),
                "paper_id": pid,
            })
    elif not node.get("children"):
        # Leaf node with no papers
        rows.append({
            "dimension": dimension,
            "taxonomy_path": current_path,
            "node_label": label,
            "level": node.get("level", 0),
            "description": node.get("description", ""),
            "source": node.get("source", ""),
            "paper_id": "",
        })

    # Process children
    children = node.get("children", [])
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                _flatten_tree(child, dimension, rows, current_path)
    elif isinstance(children, dict):
        for child_label, child_data in children.items():
            _flatten_tree(child_data, dimension, rows, current_path)
