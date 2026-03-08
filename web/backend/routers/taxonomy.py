"""
Taxonomy management API router — user-scoped.
"""
from pathlib import Path
from typing import List

from fastapi import APIRouter, UploadFile, File, HTTPException, Header

from ..core.config import CONFIGS_DIR, DATASETS_DIR, UPLOAD_DIR
from ..models.schemas import TaxonomyConfig, DimensionInfo, TaxonomyGenerateRequest, TaxonomyResponse
from ..services.taxonomy_service import TaxonomyService

router = APIRouter(prefix="/api/taxonomy", tags=["Taxonomy"])

# Per-user taxonomy services
_user_services: dict[str, TaxonomyService] = {}


def _get_svc(user_id: str) -> TaxonomyService:
    if user_id not in _user_services:
        _user_services[user_id] = TaxonomyService()
    return _user_services[user_id]


@router.post("/upload-yaml")
async def upload_yaml(file: UploadFile = File(...), x_user_id: str = Header(default="default")):
    """Upload YAML config (loaded into user's session, NOT auto-applied)."""
    content = await file.read()
    yaml_str = content.decode("utf-8")

    svc = _get_svc(x_user_id)
    dims = svc.load_yaml(yaml_str)

    # Save to user's config dir
    user_config_dir = CONFIGS_DIR / x_user_id
    user_config_dir.mkdir(parents=True, exist_ok=True)
    save_path = user_config_dir / (file.filename or "uploaded_config.yaml")
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(yaml_str)

    return {
        "success": True,
        "dimensions": list(dims.keys()),
        "dimension_count": len(dims),
        "saved_path": str(save_path),
        "applied": False,  # User must click "Apply" to use
    }


@router.post("/apply")
async def apply_config(x_user_id: str = Header(default="default"), dataset_folder: str = "web_custom_data"):
    """Apply loaded YAML config: generate initial_taxo files in user's dataset dir."""
    svc = _get_svc(x_user_id)
    if not svc.dimensions:
        raise HTTPException(400, "No YAML config loaded. Upload a YAML file first.")

    data_dir = DATASETS_DIR / x_user_id / dataset_folder.lower().replace(" ", "_")
    data_dir.mkdir(parents=True, exist_ok=True)

    generated = []
    for dim_name, dim_config in svc.dimensions.items():
        taxo_file = data_dir / f"initial_taxo_{dim_name}.txt"
        definition = dim_config.get('definition', dim_name)
        # Format required by parse_initial_taxonomy_txt in main2.py
        lines = [
            f"Label: {dim_name}",
            f"Dimension: {dim_name}",
            f"Description: {definition.strip()}",
            "---"
        ]
        content = "\n".join(lines) + "\n"
        with open(taxo_file, "w", encoding="utf-8") as f:
            f.write(content)
        generated.append(f"initial_taxo_{dim_name}.txt")

    # Save YAML copy
    svc.save_yaml(data_dir / "applied_config.yaml")

    return {
        "success": True,
        "applied": True,
        "files_generated": generated,
        "data_dir": str(data_dir),
        "message": f"Applied config: {len(generated)} taxonomy files generated",
    }


@router.get("/dimensions", response_model=List[DimensionInfo])
async def get_dimensions(x_user_id: str = Header(default="default")):
    svc = _get_svc(x_user_id)
    return [
        DimensionInfo(name=n, definition=c.get("definition", ""), node_definition=c.get("node_definition", ""))
        for n, c in svc.dimensions.items()
    ]


@router.put("/dimensions")
async def update_dimensions(config: TaxonomyConfig, x_user_id: str = Header(default="default")):
    svc = _get_svc(x_user_id)
    for name, dim_config in config.dimensions.items():
        svc.update_dimension(name, dim_config.get("definition", ""), dim_config.get("node_definition", ""))
    if config.topic:
        svc.set_topic(config.topic)
    return {"success": True, "dimensions": svc.get_dimensions_list()}


@router.delete("/dimensions/{name}")
async def delete_dimension(name: str, x_user_id: str = Header(default="default")):
    svc = _get_svc(x_user_id)
    svc.remove_dimension(name)
    return {"success": True, "remaining": svc.get_dimensions_list()}


@router.post("/generate-yaml", response_model=TaxonomyResponse)
async def generate_yaml(request: TaxonomyGenerateRequest, x_user_id: str = Header(default="default")):
    filepath = _find_upload(request.file_id, x_user_id)
    if not filepath:
        raise HTTPException(404, f"File not found: {request.file_id}")

    try:
        import pandas as pd
        df = pd.read_excel(filepath)
        df.columns = [str(c).strip() for c in df.columns]

        svc = _get_svc(x_user_id)
        yaml_content = svc.generate_yaml_from_excel(df)

        user_config_dir = CONFIGS_DIR / x_user_id
        user_config_dir.mkdir(parents=True, exist_ok=True)
        save_path = user_config_dir / "generated_config.yaml"
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(yaml_content)

        svc.load_yaml(yaml_content)
        return TaxonomyResponse(success=True, yaml_content=yaml_content, files_generated=[str(save_path)],
                                message=f"Generated YAML with {len(svc.dimensions)} dimensions")
    except Exception as e:
        return TaxonomyResponse(success=False, message=str(e))


@router.post("/generate-taxo-txt", response_model=TaxonomyResponse)
async def generate_taxo_txt(request: TaxonomyGenerateRequest, x_user_id: str = Header(default="default")):
    filepath = _find_upload(request.file_id, x_user_id)
    if not filepath:
        raise HTTPException(404, f"File not found: {request.file_id}")

    try:
        import pandas as pd
        df = pd.read_excel(filepath)
        df.columns = [str(c).strip() for c in df.columns]

        level_cols = [c for c in ["Level1", "Level2", "Level3", "Level4"] if c in df.columns]
        if not level_cols:
            return TaxonomyResponse(success=False, message="No Level columns found in Excel")

        output_dir = DATASETS_DIR / x_user_id / request.output_folder.lower().replace(" ", "_")

        svc = _get_svc(x_user_id)
        files = svc.generate_initial_taxo_files(df, level_cols, output_dir, request.topic or request.output_folder)
        return TaxonomyResponse(success=True, files_generated=list(files.keys()),
                                message=f"Generated {len(files)} taxonomy files")
    except Exception as e:
        return TaxonomyResponse(success=False, message=str(e))


@router.get("/status")
async def config_status(x_user_id: str = Header(default="default"), dataset_folder: str = "web_custom_data"):
    """Check if config has been applied (initial_taxo files exist)."""
    svc = _get_svc(x_user_id)
    data_dir = DATASETS_DIR / x_user_id / dataset_folder.lower().replace(" ", "_")

    loaded = len(svc.dimensions) > 0
    applied_files = []
    if data_dir.exists():
        applied_files = [f.name for f in data_dir.glob("initial_taxo_*.txt")]

    return {
        "loaded": loaded,
        "loaded_dimensions": list(svc.dimensions.keys()) if loaded else [],
        "applied": len(applied_files) > 0,
        "applied_files": applied_files,
    }


def _find_upload(file_id: str, user_id: str) -> Path | None:
    for base in [UPLOAD_DIR / user_id]:
        if not base.exists():
            continue
        for f in base.iterdir():
            if f.is_file() and f.name.startswith(file_id):
                return f
    return None
