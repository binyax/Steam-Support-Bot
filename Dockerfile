# =====================================================================
# Steam-Support-Bot - Imagen del backend (FastAPI + agente CrewAI)
# Multi-stage para mantener la imagen final pequena.
# Corre como usuario non-root (hardening).
# =====================================================================

FROM python:3.11-slim AS builder

# Sin .pyc y stdout sin buffer
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build deps minimas para faiss-cpu y otras wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Instalamos en un prefijo aislado y luego lo copiamos a la imagen final
COPY requirements.txt agent/requirements-agent.txt webapp/requirements-web.txt ./
RUN pip install --upgrade pip wheel && \
    pip install --prefix=/install \
        -r requirements.txt \
        -r requirements-agent.txt \
        -r requirements-web.txt

# =====================================================================
# Imagen final
# =====================================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOG_LEVEL=INFO \
    PORT=8000

# Dependencia runtime de faiss-cpu
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Usuario no privilegiado
RUN groupadd --system app && useradd --system --gid app --home /app --shell /sbin/nologin app

WORKDIR /app

# Copiamos las dependencias desde el stage builder
COPY --from=builder /install /usr/local

# Copiamos solo lo necesario (el .dockerignore evita basura)
COPY agent/ ./agent/
COPY webapp/ ./webapp/

# Carpeta para datos persistentes (faiss_index, email_outbox, jsonl).
# El docker-compose la monta como volumen.
RUN mkdir -p /app/agent/data && chown -R app:app /app

USER app

EXPOSE 8000

# Healthcheck propio (independiente del LB)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

# Un solo worker para no multiplicar la memoria de FAISS.
# proxy-headers + forwarded-allow-ips para respetar X-Forwarded-For de Nginx.
CMD ["uvicorn", "webapp.server:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
