"""
Pydantic request/response schemas for the TaxoAdapt API.
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
from enum import Enum
from datetime import datetime


# ─── Enums ───────────────────────────────────────────────

class FileType(str, Enum):
    TECH_DEFINITION = "tech_definition"
    PATENT_DATASET = "patent_dataset"
    TXT_FILE = "txt_file"
    YAML_CONFIG = "yaml_config"
    UNKNOWN = "unknown"


class ClassificationMode(str, Enum):
    TAXONOMY_ONLY = "taxonomy_only"
    WITH_SUBCATEGORY = "with_subcategory"
    WITH_RECOMMENDATIONS = "with_recommendations"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ─── File Management ─────────────────────────────────────

class FileInfo(BaseModel):
    filename: str
    filepath: str
    file_type: FileType
    size_bytes: int
    detected_columns: List[str] = []
    row_count: int = 0
    last_modified: Optional[str] = None


class FileListResponse(BaseModel):
    files: List[FileInfo]
    total: int


class FileScanRequest(BaseModel):
    folder_path: Optional[str] = None  # None → use default upload dir


class FilePreview(BaseModel):
    columns: List[str]
    rows: List[Dict[str, Any]]
    total_rows: int


# ─── Preprocessing ───────────────────────────────────────

class ColumnMapping(BaseModel):
    """Detected column mappings from patent dataset Excel."""
    title_col: Optional[str] = None
    abstract_col: Optional[str] = None
    claims_col: Optional[str] = None
    independent_claims_col: Optional[str] = None
    ai_summary_col: Optional[str] = None
    tech_field_summary_col: Optional[str] = None
    problem_summary_col: Optional[str] = None
    solution_summary_col: Optional[str] = None
    feature_summary_col: Optional[str] = None
    effect_summary_col: Optional[str] = None
    cpc_main_col: Optional[str] = None
    cpc_all_col: Optional[str] = None
    ipc_main_col: Optional[str] = None
    ipc_all_col: Optional[str] = None
    patent_id_col: Optional[str] = None
    applicant_col: Optional[str] = None
    filing_date_col: Optional[str] = None
    country_col: Optional[str] = None


class PreprocessRequest(BaseModel):
    file_id: str
    dataset_folder: str = "web_custom_data"
    column_mapping: Optional[ColumnMapping] = None  # None → auto-detect


class PreprocessResponse(BaseModel):
    success: bool
    internal_txt_path: str = ""
    total_documents: int = 0
    message: str = ""
    column_mapping: Optional[ColumnMapping] = None


# ─── Taxonomy ────────────────────────────────────────────

class DimensionInfo(BaseModel):
    name: str
    definition: str
    node_definition: str


class TaxonomyConfig(BaseModel):
    dimensions: Dict[str, Dict[str, str]]  # {dim_name: {definition, node_definition}}
    topic: str = ""


class TaxonomyGenerateRequest(BaseModel):
    file_id: str
    output_folder: str = "web_custom_data"
    topic: Optional[str] = None
    use_gpt: bool = False
    api_key: Optional[str] = None


class TaxonomyResponse(BaseModel):
    success: bool
    files_generated: List[str] = []
    yaml_content: Optional[str] = None
    message: str = ""


# ─── Classification ──────────────────────────────────────

class ClassifyRequest(BaseModel):
    # Model parameters
    model: str = "gpt-5-2025-08-07"
    temperature: float = 1.0
    top_p: float = 1.0
    max_tokens: int = 16384

    # Classification settings
    max_depth: int = 2
    max_density: int = 40
    init_levels: int = 1
    test_samples: int = 0  # 0 = all

    # Options
    classification_mode: ClassificationMode = ClassificationMode.TAXONOMY_ONLY
    dataset_folder: str = "web_custom_data"
    topic: str = "technology"
    selected_dimensions: List[str] = []
    resume: bool = False

    # API key (optional override)
    api_key: Optional[str] = None


class ClassifyProgress(BaseModel):
    run_id: str
    status: RunStatus
    progress_pct: float = 0.0
    current_step: str = ""
    current_dimension: str = ""
    logs: List[str] = []
    error: Optional[str] = None


class ClassificationResult(BaseModel):
    patent_id: str
    title: str
    predicted_levels: Dict[str, str] = {}  # {level1: ..., level2: ..., ...}
    confidence: float = 0.0
    evidence_text: str = ""
    matched_keywords: List[str] = []
    recommended_technologies: List[str] = []
    dimension: str = ""


# ─── Results ─────────────────────────────────────────────

class RunSummary(BaseModel):
    run_id: str
    status: RunStatus
    created_at: str
    topic: str = ""
    dataset_folder: str = ""
    model: str = ""
    total_documents: int = 0
    dimensions: List[str] = []
    parameters: Dict[str, Any] = {}


class RunDetail(BaseModel):
    summary: RunSummary
    results: List[ClassificationResult] = []
    taxonomy_tree: Optional[Dict[str, Any]] = None


class RunListResponse(BaseModel):
    runs: List[RunSummary]
    total: int
