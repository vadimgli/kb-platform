# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Set python and uv environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_DEFAULT_INDEX=https://pypi.org/simple \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install uv package manager
RUN pip install --no-cache-dir uv

# Copy dependency lockfile and project metadata
COPY pyproject.toml uv.lock ./

# Synchronize production dependencies without development packages
RUN uv sync --frozen --no-dev

# Copy application source code, evaluation modules, and test datasets
COPY src/ ./src/
COPY evals/ ./evals/
COPY tests/ ./tests/

# Create non-root user for Google Cloud security compliance
RUN useradd -m -u 1000 copilot && \
    chown -R copilot:copilot /app

USER copilot

EXPOSE 8000

# Run Uvicorn server bound to all network interfaces on port provided by Cloud Run (defaulting to 8000)
CMD ["sh", "-c", "exec uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
