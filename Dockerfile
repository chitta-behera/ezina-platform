# Two images from one file. The LAST stage is the default target:
#   docker build -t ezina-connect .                                  the WhatsApp registration app
#   docker build --target id-verify-api -t ezina-id-verify .         the optional ID verification HTTP wrapper
# ezina-connect imports ezina_id_verify directly; the wrapper image is only for running it as a separate service.

# ---- ID verification HTTP wrapper (optional) ----
FROM python:3.12-slim AS id-verify-api

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY pyproject.toml README.md ./
COPY ezina_id_verify/ ./ezina_id_verify/
RUN pip install --no-cache-dir ".[api]" && rm -rf ezina_id_verify pyproject.toml && useradd -m app
USER app

EXPOSE 8000
CMD ["uvicorn", "ezina_id_verify.api:app", "--host", "0.0.0.0", "--port", "8000"]

# ---- Ezina Connect (default) ----
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY requirements.txt .
# requirements.txt has "-e ." (the local package, for development); here it is installed below instead, not editable
RUN grep -v '^-e' requirements.txt > requirements.docker.txt && pip install --no-cache-dir -r requirements.docker.txt

# the ID verification module, imported by ezina-connect
COPY pyproject.toml README.md ./
COPY ezina_id_verify/ ./ezina_id_verify/
RUN pip install --no-cache-dir . && rm -rf ezina_id_verify pyproject.toml requirements.docker.txt

COPY ezina-connect/ ./ezina-connect/
WORKDIR /srv/ezina-connect

RUN useradd -m app && chown -R app /srv
USER app

EXPOSE 8000
# Run migrations, then serve. Use one worker per container; scale by replicas.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
