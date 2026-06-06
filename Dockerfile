# Root-level Dockerfile for platforms (Railway) that use the repo root as build context.
# Mirrors backend/Dockerfile but with backend/ prefixed paths.
FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY backend/pyproject.toml ./
RUN uv pip install --system --no-cache .

COPY backend/ .

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
