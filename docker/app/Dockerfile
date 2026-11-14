# App FastAPI + Jinja2. Build context = carpeta app/ (ver docker-compose.yaml)
# Etapa 1: instalar dependencias
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Etapa 2: imagen final ligera
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# gnupg: para cifrar los documentos subidos con GPG
RUN apt-get update \
 && apt-get install -y --no-install-recommends gnupg \
 && rm -rf /var/lib/apt/lists/*

# Usuario sin privilegios
RUN groupadd --system --gid 10001 sarais \
 && useradd --system --uid 10001 --gid sarais --home-dir /srv --shell /usr/sbin/nologin sarais

COPY --from=builder /install /usr/local
WORKDIR /srv
COPY --chown=sarais:sarais . /srv/app

# Carpeta de documentos cifrados (volumen) y home de GPG
RUN mkdir -p /srv/data/documents /srv/.gnupg \
 && chown -R sarais:sarais /srv/data /srv/.gnupg \
 && chmod 700 /srv/.gnupg

USER sarais
EXPOSE 8000

# La app debe exponer GET /health que responda 200
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
