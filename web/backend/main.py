"""
TaxoAdapt Web API — FastAPI Entry Point

Run with:
    cd c:\\Users\\POSCORTECH\\Documents\\GitHub\\ai_classifier
    uvicorn web.backend.main:app --reload --port 8000
"""
import sys
from pathlib import Path

# Add project root to Python path so existing modules can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import CORS_ORIGINS, API_HOST, API_PORT
from .routers import files, preprocess, taxonomy, classify, results

# ─── App ─────────────────────────────────────────────────

app = FastAPI(
    title="TaxoAdapt API",
    description="Patent Technology Classification System — React+Vite Migration",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS ────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ─────────────────────────────────────────────

app.include_router(files.router)
app.include_router(preprocess.router)
app.include_router(taxonomy.router)
app.include_router(classify.router)
app.include_router(results.router)

# ─── Health Check ────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "ok", "service": "TaxoAdapt API", "version": "1.0.0"}


@app.get("/health")
async def health():
    from .core.config import OPENAI_API_KEY
    return {
        "status": "healthy",
        "api_key_configured": bool(OPENAI_API_KEY),
        "project_root": str(PROJECT_ROOT),
    }


# ─── CLI Runner ──────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.backend.main:app", host=API_HOST, port=API_PORT, reload=True)
