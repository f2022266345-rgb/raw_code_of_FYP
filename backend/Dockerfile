# ─────────────────────────────────────────────────────────────
# LUMINA FastAPI backend (AI agents + Digital Twin + pgvector)
# ─────────────────────────────────────────────────────────────
# NOTE: pyproject requires Python >=3.14. If a dependency has no
# cp314 wheel on your platform, switch the tag to python:3.12-slim
# (requirements.txt installs fine on 3.12+).
FROM python:3.14-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# curl is only needed for container healthchecks.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for better layer caching.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the application (model files .pkl/.pth/.csv are committed and needed).
COPY . .

# Render/Railway/Fly inject $PORT; default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/docs" || exit 1

# Shell form so ${PORT} is expanded at runtime.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
