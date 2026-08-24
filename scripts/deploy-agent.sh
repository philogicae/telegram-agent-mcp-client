#!/bin/bash
set -e

# Run in subshell to contain environment variables
(
	SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
	source "$SCRIPT_DIR/load-env.sh"
	load_env ".env"

	echo "🚀 Starting docker compose deployment..."
	if [ -n "$DOCKER_HOST" ]; then
		echo "   Using Docker host: $DOCKER_HOST"
	fi
	docker compose -f compose.yaml up -d --build --remove-orphans
)
