#!/bin/bash
set -eo pipefail

# Deploy tools with automatic script execution

# Run in subshell to contain environment variables
(
    # Load .env file if it exists
    if [ -f ".env" ]; then
        set -a
        # shellcheck disable=SC1091
        source .env
        set +a
    fi

    DOCKER_ENVS_DIR="docker-envs"
    echo "🚀 Deploying containers..."
    if [ -n "$DOCKER_HOST" ]; then
        echo "   host: $DOCKER_HOST"
    fi
    docker compose -f extended.yaml up -d --build --remove-orphans

    echo ""
    echo "🔍 Running container scripts..."

    # Find all script files matching pattern: <container>.script.<index>.<name>.<ext>
    # Sort by container name and index to ensure proper execution order
    find "$DOCKER_ENVS_DIR" -name "*.script.*" -type f | sort | while read -r script; do
        filename=$(basename "$script")
        
        # Parse: <container>.script.<index>.<rest>
        container_name=$(echo "$filename" | cut -d'.' -f1)
        script_index=$(echo "$filename" | cut -d'.' -f3)
        
        if [ -n "$container_name" ] && [ -n "$script_index" ]; then
            
            # Check if container is running
            if ! docker ps --format '{{.Names}}' | grep -q "^${container_name}$"; then
                echo "   ⚠ $container_name not running, skipping $filename"
                continue
            fi
            
            # Determine how to execute based on file extension
            # Temporarily disable set -e to capture exit code
            if [[ $filename == *.py ]]; then
                echo "   ▶ [$container_name:$script_index] $filename"
                set +e
                python3 "$script"
                exit_code=$?
                set -e
            elif [[ $filename == *.sh ]]; then
                echo "   ▶ [$container_name:$script_index] $filename"
                chmod +x "$script"
                set +e
                bash "$script"
                exit_code=$?
                set -e
            else
                echo "   ⚠ Unknown script type, skipping $filename"
                continue
            fi
            
            if [ $exit_code -eq 0 ]; then
                echo "   ✅ $filename done"
            else
                echo "   ❌ $filename failed (exit $exit_code)"
                exit 1
            fi
        else
            echo "   ⚠ Could not parse: $filename"
        fi
    done

    echo ""
    echo "✅ All tasks completed!"
)