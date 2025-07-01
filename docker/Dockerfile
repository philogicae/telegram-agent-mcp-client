FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim
ENV UV_PROJECT_ENVIRONMENT=/usr/local
ENV UV_COMPILE_BYTECODE=1
ENV PYTHONUNBUFFERED=1

# Node is needed for MCP tools
RUN apt update && apt install -y nodejs npm

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-install-project --no-dev
COPY telegram_agent/ ./telegram_agent/
RUN uv sync --locked --no-dev
COPY mcp_config.json .env ./