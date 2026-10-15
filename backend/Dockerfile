# Brand DNA backend image — one image, three processes (choose with the command):
#   API     uvicorn app.main:app --host 0.0.0.0 --port 8000           (default)
#   worker  python -m app.cli worker
#   MCP     python -m app.mcp --transport streamable-http --host 0.0.0.0 --port 8001
#   ops     python -m app.cli migrate | create-admin | check | cleanup | reindex
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

# Media tooling: FFmpeg (video/audio), Tesseract (OCR fallback), glib for OpenCV headless.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg tesseract-ocr libglib2.0-0 curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first (cached unless pyproject changes). The project itself is not installed;
# it runs from /app so migrations, CLI and server share one copy of the code.
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py \
 && pip install . \
 && pip uninstall -y brand-dna-platform \
 && rm -rf app build *.egg-info

# Optional heavy document parser (pulls PyTorch). Build with --build-arg WITH_DOCLING=1.
ARG WITH_DOCLING=0
RUN if [ "$WITH_DOCLING" = "1" ]; then pip install "docling>=2.0"; fi

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin bdna \
 && mkdir -p /app/var/storage /app/var/tmp \
 && chown -R bdna /app/var
USER bdna

EXPOSE 8000 8001
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
