#!/bin/bash

# Script to deploy Transmission config to the running container with merge support

set -e

CONTAINER_NAME="transmission"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/transmission.config.json"

echo "Checking if Transmission container is running..."
if ! docker ps | grep -q $CONTAINER_NAME; then
    echo "Error: Transmission container is not running!"
    echo "Please start it first with: docker-compose -f extended.yaml up -d transmission"
    exit 1
fi

echo "Fetching current settings from container..."
docker exec $CONTAINER_NAME cat /config/settings.json > /tmp/transmission_current.json

echo "Merging new config with existing settings..."
# Use jq to merge: current settings as base, overlay with new config
jq -s '.[0] * .[1]' /tmp/transmission_current.json $CONFIG_FILE > /tmp/transmission_merged.json

echo "Copying merged config to container..."
docker cp /tmp/transmission_merged.json $CONTAINER_NAME:/config/settings.json

echo "Cleaning up temporary files..."
rm -f /tmp/transmission_current.json /tmp/transmission_merged.json

echo "Restarting Transmission to apply new config..."
docker restart $CONTAINER_NAME

echo "Waiting for Transmission to start..."
sleep 5

echo "Verifying config was applied..."
docker exec $CONTAINER_NAME cat /config/settings.json | jq '.["default-trackers"]' | head -c 200

echo -e "\n\n✅ Transmission config merged and applied successfully!"
echo "The settings have been merged with existing configuration."
echo "Check the Transmission web UI to confirm."
