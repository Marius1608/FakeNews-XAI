"""
Centralized configuration — all tuneable values come from .env
"""

from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()


# Project paths
PROJECT_ROOT = Path(__file__).parent.parent

DATA_DIR = PROJECT_ROOT / "data"
DATASETS_DIR = DATA_DIR / "datasets"
REFERENCE_KG_DIR = DATA_DIR / "reference_kg"
CACHE_DIR = DATA_DIR / "cache"


# spaCy models
SPACY_MODELS_LIST = [m.strip() for m in os.getenv("SPACY_MODELS", "en_core_web_trf").split(",")]
SPACY_DEFAULT = os.getenv("SPACY_DEFAULT_MODEL", "en_core_web_trf")

# Backward-compatible alias used by Pipeline A
SPACY_MODEL = SPACY_DEFAULT


# Qwen / LLM models
QWEN_MODEL_ID = os.getenv("QWEN_MODEL_ID", "Qwen/Qwen3-1.7B")

LLM_MODELS_LIST = [QWEN_MODEL_ID]
LLM_DEFAULT = QWEN_MODEL_ID


# Combined model registry exposed by GET /models
AVAILABLE_MODELS = {
    "spacy": {"default": SPACY_DEFAULT, "models": SPACY_MODELS_LIST},
    "llm": {"default": LLM_DEFAULT, "models": LLM_MODELS_LIST},
}


# Wikidata SPARQL — public endpoint, no API key needed
WIKIDATA_ENDPOINT = os.getenv(
    "WIKIDATA_ENDPOINT",
    "https://query.wikidata.org/sparql"
)
WIKIDATA_TEMPORAL_PROPERTIES = ["P580", "P582", "P585"]


# Binary fake/real threshold — article predicted FAKE if TCS < FAKE_THRESHOLD.
# Decorative: no endpoint currently reads this to produce a binary label (only
# the continuous score + the 5-band `label` below). Also exposed as the mutable
# "fake_threshold" parameter in runtime_settings.py for the UI; that copy does
# not change this constant's unused status either.
FAKE_THRESHOLD: float = 0.75

# TCS score-band thresholds (0.8/0.5/0.2) that used to live here as a decorative,
# never-read dict have moved to runtime_settings.py ("tcs_very_consistent" /
# "tcs_moderate" / "tcs_suspicious") — the single source TCSResult.label
# (pipeline/graph/models.py) and TCSExplainer._explain_score
# (pipeline/scoring/explainer.py) both read from.


# Wikipedia REST API — disabled in production; set USE_WEB_SEARCH=true only for debugging
USE_WEB_SEARCH: bool = os.getenv("USE_WEB_SEARCH", "false").lower() == "true"


# Neo4j — optional persistent store for cross-article analysis
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
NEO4J_ENABLED = os.getenv("NEO4J_ENABLED", "false").lower() == "true"


# FastAPI settings
API_TITLE = "TCS - Temporal Coherence Score API"
API_VERSION = "0.1.0"

# CORS — origins allowed to call the backend (React dev server by default)
_cors_raw = os.getenv("CORS_ORIGINS", "http://localhost:3000")
CORS_ORIGINS = [o.strip() for o in _cors_raw.split(",")]
