FROM ghcr.io/astral-sh/uv:python3.13-alpine
COPY pyproject.toml uv.lock README.md mcp_config.json ./
COPY telegram_agent/ ./telegram_agent/

EXPOSE 8000
CMD ["uv", "run", "--locked", "--no-sync", "-m", "telegram_agent"]