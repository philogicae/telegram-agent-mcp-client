FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS runner
ENV UV_PYTHON_DOWNLOADS=0 PYTHONUNBUFFERED=1

# Node is needed for MCP tools
RUN apt-get update && \
    apt-get install -y nodejs npm && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app

# Install dependencies
COPY pyproject.toml uv.lock README.md /app/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

# Install project
COPY telegram_agent /app/telegram_agent
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

FROM runner
COPY --from=builder --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH"