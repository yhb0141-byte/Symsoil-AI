FROM node:22-bookworm-slim AS web
WORKDIR /build/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/services/api SYMSOIL_WEB_DIST=/app/apps/web/dist \
    DATABASE_URL=sqlite:////data/symsoil.db SYMSOIL_MODE=development \
    SYMSOIL_REVOCATION_DIR=/revocations SYMSOIL_RECOVERY_WITNESS_DIR=/witness
WORKDIR /app
COPY services/api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && useradd --uid 10001 --create-home symsoil \
    && mkdir -p /data /revocations /witness \
    && chown symsoil:symsoil /data /revocations /witness
COPY services/api/symsoil_api/ /app/services/api/symsoil_api/
COPY --from=web /build/apps/web/dist/ /app/apps/web/dist/
USER symsoil
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)" || exit 1
CMD ["python", "-m", "uvicorn", "symsoil_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
