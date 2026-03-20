"""
Configurare centralizata pentru proiect
"""

from pathlib import Path
from dotenv import load_dotenv
import os

# ──────────────────────────────────────────────
# Incarca variabilele din .env
# ──────────────────────────────────────────────
# load_dotenv() cauta fisierul .env in directorul curent
# si incarca variabilele in os.environ
# Exemplu: daca in .env ai NEWSAPI_KEY=abc123
# dupa load_dotenv() poti face os.getenv("NEWSAPI_KEY") → "abc123"
load_dotenv()


# ──────────────────────────────────────────────
# Paths — unde se afla fiecare folder important
# ──────────────────────────────────────────────
# __file__ = calea catre ACEST fisier (backend/config.py)
# .parent = backend/
# .parent.parent = radacina proiectului (FakeNews-XAI/)
PROJECT_ROOT = Path(__file__).parent.parent

DATA_DIR = PROJECT_ROOT / "data"
DATASETS_DIR = DATA_DIR / "datasets"
REFERENCE_KG_DIR = DATA_DIR / "reference_kg"
CACHE_DIR = DATA_DIR / "cache"


# ──────────────────────────────────────────────
# spaCy — modelul NLP folosit in Pipeline A
# ──────────────────────────────────────────────
# en_core_web_trf = model transformer (cel mai precis)
# Poate fi suprascris din .env daca vrem sa testam alt model
SPACY_MODEL = os.getenv("SPACY_MODEL", "en_core_web_trf")


# ──────────────────────────────────────────────
# Wikidata SPARQL — pentru verificare externa
# ──────────────────────────────────────────────
# Endpoint-ul e public, nu necesita API key
# Proprietati temporale pe care le interogam:
#   P580 = start time (cand a inceput ceva)
#   P582 = end time (cand s-a terminat)
#   P585 = point in time (cand s-a intamplat punctual)
WIKIDATA_ENDPOINT = os.getenv(
    "WIKIDATA_ENDPOINT",
    "https://query.wikidata.org/sparql"
)
WIKIDATA_TEMPORAL_PROPERTIES = ["P580", "P582", "P585"]


# ──────────────────────────────────────────────
# NewsAPI — doar pentru demo/notebook
# ──────────────────────────────────────────────
# NU face parte din pipeline-ul principal
# Folosim doar in notebook pentru a lua articole live
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")
NEWSAPI_BASE_URL = "https://newsapi.org/v2"


# ──────────────────────────────────────────────
# Ollama / LLM local — Pipeline B (Sprint 3)
# ──────────────────────────────────────────────
# On-premise, fara dependente externe
# Se activeaza doar cand implementam Pipeline B
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")


# ──────────────────────────────────────────────
# TCS Thresholds — praguri de interpretare scor
# ──────────────────────────────────────────────
# Scorul TCS e intre 0 si 1
# Aceste praguri determina eticheta finala
TCS_THRESHOLDS = {
    "very_consistent": 0.8,    # 0.8 - 1.0: Probabil real
    "moderate": 0.5,           # 0.5 - 0.7: Moderat consistent
    "suspicious": 0.2,         # 0.2 - 0.4: Inconsistente multiple
    "severe": 0.0,             # 0.0 - 0.2: Violari severe (probabil fake)
}


# ──────────────────────────────────────────────
# FastAPI — setari server
# ──────────────────────────────────────────────
API_TITLE = "TCS - Temporal Coherence Score API"
API_VERSION = "0.1.0"
# CORS — permite frontend-ului React sa comunice cu backend-ul
# localhost:3000 = portul default React dev server
CORS_ORIGINS = ["http://localhost:3000"]