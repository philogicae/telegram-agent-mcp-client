#!/bin/bash
set -e

# Run in subshell to contain environment variables
(
	# Load .env file if it exists
	if [ -f ".env" ]; then
		# shellcheck disable=SC1091
		set -a
		source .env
		set +a
	fi

	echo "🚀 Starting docker compose deployment..."
	if [ -n "$DOCKER_HOST" ]; then
		echo "   Using Docker host: $DOCKER_HOST"
	fi
	docker compose -f compose.yaml up -d --build --remove-orphans
)
