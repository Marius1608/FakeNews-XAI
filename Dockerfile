FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir aiofiles

# spaCy model
RUN python -m spacy download en_core_web_trf

# Copy project
COPY backend/ ./backend/
COPY data/ ./data/
COPY frontend/build/ ./frontend/build/

# Neo4j Aura credentials injected via Spaces Secrets at runtime
# NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_ENABLED, NEO4J_DATABASE set via Spaces UI
ENV NEO4J_ENABLED=false
ENV USE_WEB_SEARCH=false
ENV CORS_ORIGINS=*
ENV PORT=7860
ENV HF_SPACES=true

EXPOSE 7860

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860"]
