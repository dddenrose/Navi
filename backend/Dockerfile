# ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency spec and install
# uv 預設不編 .pyc，而執行期的 appuser 寫不進 site-packages：不在這裡編好，
# 每次冷啟動都要把一萬多個 .py 從原始碼重編（實測 import main 22.6s → 7.3s）
COPY pyproject.toml ./
ENV UV_COMPILE_BYTECODE=1
RUN uv pip install --system --no-cache -r pyproject.toml

# ── Runtime stage ────────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code（.dockerignore 排除了 .pyc，在 image 內重編）
COPY . .
RUN python -m compileall -q /app

# Non-root user for security
RUN adduser --disabled-password --no-create-home appuser
USER appuser

# Expose port (Cloud Run uses PORT env, default 8080)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8080}/health')" || exit 1

# Run with uvicorn — honour $PORT for Cloud Run compatibility
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
