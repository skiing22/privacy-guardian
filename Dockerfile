# syntax=docker/dockerfile:1.7
# One image: built React app + FastAPI backend + NER model (ARCHITECTURE 16.1).
#
# Model delivery (API 8.2, D16):
#   real (default) docker build --secret id=hf_token,src=.secrets/hf_token \
#                    --build-arg MODEL_REPO=owner/name \
#                    --build-arg MODEL_REVISION=<40-char commit> \
#                    --build-arg MODEL_SHA256=<64 hex> .
#   CI / trial     docker build --build-arg MODEL_SOURCE=fake .   (tiny random model: never ship)
#
# The token is a BuildKit secret: mounted for one RUN step only, never in a layer, never in
# the image's environment or history. The running app never contacts Hugging Face.

ARG MODEL_SOURCE=hf

# ---- frontend build ----
FROM node:22-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- python base: backend + CPU-only PyTorch + transformers ----
FROM python:3.11-slim AS base
ARG TORCH_VERSION=2.15.0
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    TRANSFORMERS_OFFLINE=1
WORKDIR /app
# CPU wheel first: the default PyPI wheel pulls in GPU libraries (~2 GB we never use).
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch==${TORCH_VERSION}" \
 && echo "torch==${TORCH_VERSION}" > /tmp/constraints.txt
COPY backend/pyproject.toml ./
COPY backend/app ./app
# The constraint stops pip from swapping in the GPU build while installing transformers.
RUN pip install --no-cache-dir -c /tmp/constraints.txt ".[ml]"

# ---- model, option 1: private Hugging Face repo (production) ----
FROM python:3.11-slim AS model-hf
ARG MODEL_REPO
ARG MODEL_REVISION
ARG MODEL_SHA256
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --no-cache-dir "huggingface_hub==2.4.0"
COPY backend/scripts/model_fetch.py /tools/model_fetch.py
RUN --mount=type=secret,id=hf_token,target=/run/secrets/hf_token,required=true \
    MODEL_REPO="$MODEL_REPO" MODEL_REVISION="$MODEL_REVISION" MODEL_SHA256="$MODEL_SHA256" \
    python /tools/model_fetch.py download --out /model

# ---- model, option 2: tiny random model (CI, trying the image without the weights) ----
FROM base AS model-fake
COPY backend/scripts/model_fetch.py /app/scripts/model_fetch.py
RUN python /app/scripts/model_fetch.py fake --out /model

FROM model-${MODEL_SOURCE} AS model

# ---- runtime ----
FROM base AS runtime
ENV DATA_DIR=/data \
    STATIC_DIR=/app/static \
    NER_MODEL_PATH=/app/model
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown app:app /data
COPY --from=frontend /fe/dist /app/static
# Root-owned and read-only for the app user: the app can load the model, never change it.
COPY --from=model /model /app/model
USER app
EXPOSE 8000
# /health answers 503 until the model is loaded, so the start period allows for it.
HEALTHCHECK --interval=15s --timeout=3s --start-period=120s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=2)"
# One worker: the model and the scan queue live in this process (ARCHITECTURE 3.3, D17).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
