"""FastAPI app — CORS, mount routers, lifecycle."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import API_TITLE, API_VERSION, CORS_ORIGINS
from backend.routers import analyze, compare, health
from backend.routers.articles import router as articles_router
from backend.routers.batch import router as batch_router
from backend.routers.config import router as config_router
from backend.routers.upload import router as upload_router
from backend.routers.verify import router as verify_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-30s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)

# App
app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    description="Temporal Coherence Score — fake news detection through temporal consistency analysis.",
)

# CORS — allow the React dev server (localhost:3000) by default
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router)
app.include_router(analyze.router)
app.include_router(compare.router)
app.include_router(articles_router)
app.include_router(batch_router)
app.include_router(config_router)
app.include_router(upload_router)
app.include_router(verify_router)


@app.on_event("startup")
async def _startup() -> None:
    logger.info(f"{API_TITLE} v{API_VERSION} — server started.")


@app.on_event("shutdown")
async def _shutdown() -> None:
    logger.info("Server stopped.")


# Serve React build in HuggingFace Spaces (single-port deployment).
# Local dev: frontend runs on :3000 via Vite (npm run dev) — this block is skipped entirely
# when HF_SPACES is not set, so no import of StaticFiles happens locally.
import os
from pathlib import Path

from backend.spa import safe_build_path

_FRONTEND_BUILD = Path(__file__).parent.parent / "frontend" / "build"



if _FRONTEND_BUILD.exists() and os.getenv("HF_SPACES") == "true":
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    _assets_dir = _FRONTEND_BUILD / "assets"  # Vite output (hashed JS/CSS)
    if _assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")

    @app.get("/", include_in_schema=False)
    async def _serve_root() -> FileResponse:
        return FileResponse(str(_FRONTEND_BUILD / "index.html"))

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _serve_spa(full_path: str) -> FileResponse:
        # API routes registered above take priority over this catch-all
        file_path = safe_build_path(_FRONTEND_BUILD, full_path)
        if file_path is not None:
            return FileResponse(str(file_path))
        return FileResponse(str(_FRONTEND_BUILD / "index.html"))
