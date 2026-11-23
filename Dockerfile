FROM python:3.12-slim-bookworm

# ffmpeg merges video+audio and converts to MP3/M4A.
# Deno is the JavaScript runtime yt-dlp uses to solve YouTube's signatures.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=denoland/deno:bin-2.9.6 /deno /usr/local/bin/deno
COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app.py ./
COPY static ./static

RUN useradd --create-home appuser && mkdir -p /app/.downloads && chown -R appuser /app/.downloads
USER appuser

ENV PORT=8000 MAX_CONCURRENT_JOBS=2 MAX_FILESIZE_MB=500 JOB_TTL_SECONDS=1800
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz')"
CMD ["python", "app.py"]
