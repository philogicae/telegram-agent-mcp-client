#!/bin/bash
set -e

# Lock and sync dependencies
rtk uv lock
rtk uv sync -U --link-mode=copy

# Format code
rtk uv run ruff format

# Check for linting errors
rtk uv run ruff check --fix

# Run type checking
rtk uv run ty check