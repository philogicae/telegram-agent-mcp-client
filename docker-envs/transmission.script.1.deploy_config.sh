#!/bin/bash

# Script to deploy Transmission config to the running container with merge support

set -eo pipefail

CONTAINER_NAME="transmission"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/transmission.config.json"

# Temp files with cleanup on exit
CURRENT_JSON=$(mktemp /tmp/transmission_current.XXXXXX.json)
MERGED_JSON=$(mktemp /tmp/transmission_merged.XXXXXX.json)
cleanup() {
    rm -f "$CURRENT_JSON" "$MERGED_JSON"
}
trap cleanup EXIT

# Check dependencies
if ! command -v jq &>/dev/null; then
    echo "Error: jq is required (apt install jq)"
    exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
    echo "Error: $CONTAINER_NAME not running"
    exit 1
fi

echo "Fetching current settings..."
docker exec "$CONTAINER_NAME" cat /config/settings.json > "$CURRENT_JSON"

echo "Merging config..."
jq -s '.[0] * .[1]' "$CURRENT_JSON" "$CONFIG_FILE" > "$MERGED_JSON"

echo "Stopping container (prevents Transmission from overwriting config on shutdown)..."
docker stop "$CONTAINER_NAME"

echo "Applying to container..."
docker cp "$MERGED_JSON" "$CONTAINER_NAME:/config/settings.json"
docker start "$CONTAINER_NAME"

echo "Waiting for restart..."
for i in $(seq 1 30); do
    if docker exec "$CONTAINER_NAME" sh -c 'wget -q -O /dev/null http://localhost:9091/transmission/rpc 2>/dev/null || curl -sf http://localhost:9091/transmission/rpc >/dev/null 2>&1' 2>/dev/null; then
        break
    fi
    sleep 1
done

# Compare tracker sets (Transmission normalizes separators on restart, so compare parsed entries not raw bytes)
APPLIED_COUNT=$(docker exec "$CONTAINER_NAME" cat /config/settings.json | jq -r '.["default-trackers"] // empty' | tr '\n' '\n' | grep -c . || echo 0)
CONFIG_COUNT=$(jq -r '.["default-trackers"] // empty' "$CONFIG_FILE" | grep -c . || echo 0)

if [ "$APPLIED_COUNT" -eq 0 ]; then
    echo "⚠ default-trackers is empty"
elif [ "$APPLIED_COUNT" -ge "$CONFIG_COUNT" ]; then
    echo "✓ Verified ($APPLIED_COUNT trackers)"
else
    echo "⚠ Mismatch: expected $CONFIG_COUNT trackers, got $APPLIED_COUNT"
fi

echo "✅ Config applied"
