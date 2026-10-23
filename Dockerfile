# Stage 1 — build React frontend without any local .env files
# VITE_API_URL is intentionally NOT set here so BASE_URL compiles to ""
# (relative URLs → same-origin API calls on HF Spaces single-port deployment)
FROM node:24-slim AS frontend-builder

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --silent
COPY frontend/tsconfig.json frontend/vite.config.ts frontend/index.html ./
COPY frontend/src/ ./src/
COPY frontend/public/ ./public/
RUN npm run build

# Stage 2 — Python backend + compiled frontend
FROM python:3.13-slim

RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# spaCy model
RUN python -m spacy download en_core_web_trf

# Copy project
COPY backend/ ./backend/
COPY data/ ./data/
COPY scripts/check_neo4j.py scripts/docker-entrypoint.sh ./scripts/
RUN sed -i 's/\r$//' ./scripts/docker-entrypoint.sh && chmod +x ./scripts/docker-entrypoint.sh
COPY --from=frontend-builder /frontend/build/ ./frontend/build/

# Neo4j Aura credentials injected via Spaces Secrets at runtime
# NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_ENABLED, NEO4J_DATABASE set via Spaces UI
ENV NEO4J_ENABLED=false
ENV USE_WEB_SEARCH=false
ENV CORS_ORIGINS=*
ENV PORT=7860
ENV HF_SPACES=true

EXPOSE 7860

# Entrypoint verifies the Neo4j instance from Secrets (Aura) before starting uvicorn;
# if unreachable, the API starts with NEO4J_ENABLED=false.
CMD ["./scripts/docker-entrypoint.sh"]
