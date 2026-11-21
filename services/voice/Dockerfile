FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra engines --no-install-project
COPY . .
RUN uv sync --frozen --no-dev --extra engines && useradd --system --uid 10001 nexus \
    && mkdir -p /data && chown -R nexus /data
USER nexus
ENV PATH="/app/.venv/bin:$PATH" VOICE_HOST=0.0.0.0 VOICE_DATA_DIR=/data
EXPOSE 8880
CMD ["nexus-voice"]
