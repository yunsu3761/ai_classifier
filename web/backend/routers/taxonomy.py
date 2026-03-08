"""
Taxonomy management API router.
"""
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Query

from ..core.config import CONFIGS_DIR, DATASETS_DIR, UPLOAD_DIR
from ..models.schemas import TaxonomyConfig, DimensionInfo, TaxonomyGenerateRequest, TaxonomyResponse
from ..services.taxonomy_service import get_taxonomy_service

router = APIRouter(prefix="/api/taxonomy", tags=["Taxonomy"])


@router.post("/upload-yaml")
async def upload_yaml(file: UploadFile = File(...)):
    """Upload and load a YAML dimension config."""
    content = await file.read()
    yaml_str = content.decode("utf-8")

    svc = get_taxonomy_service()
    dims = svc.load_yaml(yaml_str)

    # Also save to configs dir
    save_path = CONFIGS_DIR / (file.filename or "uploaded_config.yaml")
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(yaml_str)

    return {
        "success": True,
        "dimensions": list(dims.keys()),
        "dimension_count": len(dims),
        "saved_path": str(save_path),
    }


@router.get("/dimensions", response_model=List[DimensionInfo])
async def get_dimensions():
    """Get all current dimensions."""
    svc = get_taxonomy_service()
    result = []
    for name, config in svc.dimensions.items():
        result.append(DimensionInfo(
            name=name,
            definition=config.get("definition", ""),
            node_definition=config.get("node_definition", ""),
        ))
    return result


@router.put("/dimensions")
async def update_dimensions(config: TaxonomyConfig):
    """Update dimension configuration."""
    svc = get_taxonomy_service()
    for name, dim_config in config.dimensions.items():
        svc.update_dimension(
            name=name,
            definition=dim_config.get("definition", ""),
            node_definition=dim_config.get("node_definition", ""),
        )
    if config.topic:
        svc.set_topic(config.topic)
    return {"success": True, "dimensions": svc.get_dimensions_list()}


@router.delete("/dimensions/{name}")
async def delete_dimension(name: str):
    """Remove a dimension."""
    svc = get_taxonomy_service()
    svc.remove_dimension(name)
    return {"success": True, "remaining": svc.get_dimensions_list()}


@router.post("/generate-yaml", response_model=TaxonomyResponse)
async def generate_yaml(request: TaxonomyGenerateRequest):
    """Generate YAML config from a Dimension Excel file."""
    filepath = _find_upload(request.file_id)
    if not filepath:
        raise HTTPException(404, f"File not found: {request.file_id}")

    try:
        import pandas as pd
        df = pd.read_excel(filepath)
        df.columns = [str(c).strip() for c in df.columns]

        svc = get_taxonomy_service()
        yaml_content = svc.generate_yaml_from_excel(df)

        # Save
        save_path = CONFIGS_DIR / "generated_config.yaml"
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(yaml_content)

        # Also load into service
        svc.load_yaml(yaml_content)

        return TaxonomyResponse(
            success=True,
            yaml_content=yaml_content,
            files_generated=[str(save_path)],
            message=f"Generated YAML with {len(svc.dimensions)} dimensions",
        )
    except Exception as e:
        return TaxonomyResponse(success=False, message=str(e))


@router.post("/generate-taxo-txt", response_model=TaxonomyResponse)
async def generate_taxo_txt(request: TaxonomyGenerateRequest):
    """Generate initial_taxo_*.txt files from hierarchical Excel data."""
    filepath = _find_upload(request.file_id)
    if not filepath:
        raise HTTPException(404, f"File not found: {request.file_id}")

    try:
        import pandas as pd
        df = pd.read_excel(filepath)
        df.columns = [str(c).strip() for c in df.columns]

        level_cols = [c for c in ["Level1", "Level2", "Level3", "Level4"] if c in df.columns]
        if not level_cols:
            return TaxonomyResponse(success=False, message="No Level columns found in Excel")

        output_dir = DATASETS_DIR / request.output_folder.lower().replace(" ", "_")
        topic = request.topic or request.output_folder

        svc = get_taxonomy_service()
        files = svc.generate_initial_taxo_files(df, level_cols, output_dir, topic)

        return TaxonomyResponse(
            success=True,
            files_generated=list(files.keys()),
            message=f"Generated {len(files)} taxonomy files",
        )
    except Exception as e:
        return TaxonomyResponse(success=False, message=str(e))


@router.get("/yaml")
async def get_yaml():
    """Get current taxonomy config as YAML."""
    svc = get_taxonomy_service()
    return {"yaml": svc.to_yaml_string()}


def _find_upload(file_id: str) -> Path | None:
    if not UPLOAD_DIR.exists():
        return None
    for f in UPLOAD_DIR.iterdir():
        if f.is_file() and f.name.startswith(file_id):
            return f
    direct = UPLOAD_DIR / file_id
    return direct if direct.exists() else None
