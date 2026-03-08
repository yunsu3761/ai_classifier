"""
Result persistence — user-scoped.
"""
import json
from pathlib import Path
from typing import List, Optional

import pandas as pd

from ..core.config import DATASETS_DIR, SAVE_OUTPUT_DIR
from ..models.schemas import RunSummary, RunDetail, RunStatus


def list_runs(dataset_folder: Optional[str] = None, user_id: str = "default") -> List[RunSummary]:
    runs = []
    base = DATASETS_DIR / user_id
    if not base.exists():
        return runs

    search_dirs = []
    if dataset_folder:
        search_dirs.append(base / dataset_folder.lower().replace(" ", "_"))
    else:
        for d in base.iterdir():
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


def get_run_detail(run_id: str, user_id: str = "default") -> Optional[RunDetail]:
    base = DATASETS_DIR / user_id
    if not base.exists():
        return None

    for dir_path in base.iterdir():
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

            taxonomy_tree = {}
            dims = meta.get("parameters", {}).get("dimensions", [])
            for dim in dims:
                taxo_file = dir_path / f"final_taxo_{dim}.json"
                if taxo_file.exists():
                    with open(taxo_file, "r", encoding="utf-8") as f:
                        taxonomy_tree[dim] = json.load(f)

            return RunDetail(summary=summary, taxonomy_tree=taxonomy_tree)
    return None


def get_taxonomy_json(run_id: str, dimension: Optional[str] = None, user_id: str = "default"):
    detail = get_run_detail(run_id, user_id)
    if not detail or not detail.taxonomy_tree:
        return None
    return detail.taxonomy_tree.get(dimension) if dimension else detail.taxonomy_tree


def export_results_to_excel(run_id: str, user_id: str = "default") -> Optional[Path]:
    detail = get_run_detail(run_id, user_id)
    if not detail:
        return None

    rows = []
    if detail.taxonomy_tree:
        for dim, tree in detail.taxonomy_tree.items():
            _flatten_tree(tree, dim, rows)

    if not rows:
        return None

    df = pd.DataFrame(rows)
    output_dir = SAVE_OUTPUT_DIR / user_id / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"results_{run_id}.xlsx"
    df.to_excel(output_path, index=False)
    return output_path


def _write_node_to_txt(node: dict, dimension: str, lines: list, indent_level: int = 0):
    indent = " " * (indent_level * 5)
    
    label = node.get("label", node.get("name", ""))
    lines.append(f"{indent}Label: {label}")
    lines.append(f"{indent}Dimension: {dimension}")
    
    desc = node.get("description", "")
    lines.append(f"{indent}Description: {desc}")
    
    level = node.get("level", 0)
    lines.append(f"{indent}Level: {level}")
    
    source = node.get("source", "Initial")
    lines.append(f"{indent}Source: {source}")
    
    paper_ids = node.get("paper_ids", node.get("papers", []))
    lines.append(f"{indent}# of Papers: {len(paper_ids)}")
    
    example_papers = node.get("example_papers", [])
    if example_papers:
        # truncate to 3 examples to mimic taxonomy.py display()
        ep_subset = example_papers[:3]
        try:
            formatted_ep = "[" + ", ".join([f"({ep[0]}, '{ep[1]}')" for ep in ep_subset]) + "]"
        except Exception:
            formatted_ep = str(ep_subset)
        lines.append(f"{indent}Example Papers: {formatted_ep}")
    
    children = node.get("children", [])
    if children:
        lines.append(f"{indent}" + "-" * 40)
        lines.append(f"{indent}Children:")
        child_list = children if isinstance(children, list) else list(children.values())
        for child in child_list:
            if isinstance(child, dict):
                _write_node_to_txt(child, dimension, lines, indent_level + 1)
                
    lines.append(f"{indent}" + "-" * 40)


def export_results_to_txt(run_id: str, user_id: str = "default") -> Optional[Path]:
    detail = get_run_detail(run_id, user_id)
    if not detail or not detail.taxonomy_tree:
        return None

    lines = []
    for dim, tree in detail.taxonomy_tree.items():
        _write_node_to_txt(tree, dim, lines, 0)
        lines.append("-" * 40)
        lines.append("")

    output_dir = SAVE_OUTPUT_DIR / user_id / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"results_{run_id}.txt"
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        
    return output_path


def get_results_table_data(run_id: str, user_id: str = "default") -> Optional[List[dict]]:
    detail = get_run_detail(run_id, user_id)
    if not detail:
        return None

    rows = []
    if detail.taxonomy_tree:
        for dim, tree in detail.taxonomy_tree.items():
            _flatten_tree(tree, dim, rows)
            
    return rows


def _flatten_tree(node: dict, dimension: str, rows: list, path: str = ""):
    label = node.get("label", "")
    current_path = f"{path} > {label}" if path else label
    paper_ids = node.get("paper_ids", [])

    if paper_ids:
        for pid in paper_ids:
            rows.append({"dimension": dimension, "taxonomy_path": current_path, "node_label": label,
                         "level": node.get("level", 0), "description": node.get("description", ""),
                         "paper_id": pid})
    elif not node.get("children"):
        rows.append({"dimension": dimension, "taxonomy_path": current_path, "node_label": label,
                     "level": node.get("level", 0), "description": node.get("description", ""), "paper_id": ""})

    children = node.get("children", [])
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                _flatten_tree(child, dimension, rows, current_path)
    elif isinstance(children, dict):
        for child_data in children.values():
            _flatten_tree(child_data, dimension, rows, current_path)
