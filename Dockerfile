# syntax=docker/dockerfile:1

# --- Builder: install deps and warm the HuggingFace model cache ---
FROM python:3.11-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.30 /uv /uvx /usr/local/bin/

WORKDIR /app

# A C toolchain for the few transitive deps without prebuilt wheels.
# Builder-only, never reaches the final image.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Keep the HF cache under /app so it survives the copy into the runtime stage.
ENV HF_HOME=/app/.cache/huggingface \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Dependency layer first, cached across code-only changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Application code + source PDFs.
COPY core ./core
COPY db ./db
COPY knowledge_base ./knowledge_base
COPY rag ./rag
COPY tools ./tools
COPY server.py ./server.py
COPY ["UC Davis AI", "./UC Davis AI"]
RUN uv sync --frozen

# Download both HuggingFace models at build time so the running container
# never needs a network call to Hugging Face. The vector store is NOT built
# here (it lives in Postgres/pgvector, unreachable from a CI build) — the
# server seeds it at startup, or you run `python -m knowledge_base.build_index`
# once against the production database.
RUN uv run python -c "\
from knowledge_base.embedder import get_embedding_model; \
from rag.reranker import get_reranker_model; \
get_embedding_model(); get_reranker_model()"

# --- Runtime: slim image with just the venv, code, and model cache ---
FROM python:3.11-slim

WORKDIR /app

ENV HF_HOME=/app/.cache/huggingface \
    HF_HUB_OFFLINE=1 \
    PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PORT=8080

COPY --from=builder /app /app

# Cloud Run injects $PORT and expects the container to listen on it.
EXPOSE 8080
CMD ["sh", "-c", "python server.py"]
