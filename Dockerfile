# One image: built React app + FastAPI backend (ARCHITECTURE 16.1).
# The model stage (weights from a private Hugging Face repo, D16) is added in P11.
# /health answers 503 until the model is loaded, so the start period allows for it.

# ---- frontend build ----
FROM node:22-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- runtime ----
FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    STATIC_DIR=/app/static
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown app:app /data
WORKDIR /app
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --no-cache-dir .
COPY --from=frontend /fe/dist /app/static
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=120s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=2)"
# One worker: the model and the scan queue live in this process (ARCHITECTURE 3.3, D17).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
