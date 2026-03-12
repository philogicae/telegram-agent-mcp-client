#!/bin/bash
set -e

# Deploy tools with automatic script execution

# Run in subshell to contain environment variables
(
    # Load .env file if it exists
    if [ -f ".env" ]; then
        export $(cat .env | grep -v '^#' | xargs)
    fi

    DOCKER_ENVS_DIR="docker-envs"
    echo "🚀 Starting docker compose deployment..."
    if [ -n "$DOCKER_HOST" ]; then
        echo "   Using Docker host: $DOCKER_HOST"
    fi
    docker compose -f extended.yaml up -d --build --remove-orphans

    echo ""
    echo "🔍 Scanning for container deployment scripts..."

    # Find all script files matching pattern: <container>.script.<index>.<name>.<ext>
    # Sort by container name and index to ensure proper execution order
    find "$DOCKER_ENVS_DIR" -name "*.script.*" -type f | sort | while read -r script; do
        filename=$(basename "$script")
        
        # Parse: <container>.script.<index>.<rest>
        container_name=$(echo "$filename" | cut -d'.' -f1)
        script_index=$(echo "$filename" | cut -d'.' -f3)
        
        if [ -n "$container_name" ] && [ -n "$script_index" ]; then
            
            echo ""
            echo "📋 Found script for container '$container_name' (index: $script_index)"
            echo "   Script: $filename"
            
            # Check if container is running
            if docker ps --format '{{.Names}}' | grep -q "^${container_name}$"; then
                echo "   ✓ Container '$container_name' is running"
            else
                echo "   ⚠ Container '$container_name' is not running, skipping script"
                continue
            fi
            
            # Determine how to execute based on file extension
            if [[ $filename == *.py ]]; then
                echo "   ▶ Executing Python script..."
                python3 "$script"
            elif [[ $filename == *.sh ]]; then
                echo "   ▶ Executing Bash script..."
                chmod +x "$script"
                bash "$script"
            else
                echo "   ⚠ Unknown script type, skipping"
                continue
            fi
            
            if [ $? -eq 0 ]; then
                echo "   ✅ Script completed successfully"
            else
                echo "   ❌ Script failed with exit code $?"
                exit 1
            fi
        else
            echo "   ⚠ Could not parse filename: $filename"
        fi
    done

    echo ""
    echo "✅ All deployment tasks completed!"
)