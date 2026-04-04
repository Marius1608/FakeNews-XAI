"""FastAPI app — CORS, mount routers, lifecycle."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import API_TITLE, API_VERSION, CORS_ORIGINS
from backend.routers import analyze, compare, health

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

# CORS — permite frontend React (localhost:3000)
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


@app.on_event("startup")
async def _startup() -> None:
    logger.info(f"{API_TITLE} v{API_VERSION} — server pornit.")


@app.on_event("shutdown")
async def _shutdown() -> None:
    logger.info("Server oprit.")