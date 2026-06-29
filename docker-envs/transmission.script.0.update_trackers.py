#!/usr/bin/env python3
"""Script to update Transmission default trackers from trackers.txt file."""

import json
import sys
from pathlib import Path


def load_trackers(trackers_file: str) -> list[str]:
    """Load trackers from file, filter out comments, and deduplicate (preserving order)."""
    trackers = []
    seen = set()
    with Path(trackers_file).open() as f:
        for raw_line in f:
            line = raw_line.strip()
            if line and not line.startswith("#") and line not in seen:
                seen.add(line)
                trackers.append(line)
    return trackers


def update_transmission_config(config_file: str, trackers_file: str) -> str:
    """Update Transmission config with default trackers."""
    # Load trackers
    trackers = load_trackers(trackers_file)

    # Format according to Transmission docs:
    # - Double newline for additional trackers
    # - Single newline for backup trackers
    # We'll use double newlines for all to ensure they're all used
    default_trackers = "\n\n".join(trackers)

    # Load existing config
    with Path(config_file).open() as f:
        config = json.load(f)

    # Update default-trackers
    config["default-trackers"] = default_trackers

    # Save updated config
    with Path(config_file).open("w") as f:
        json.dump(config, f, indent=2)

    print(f"Updated {Path(config_file).name} with {len(trackers)} trackers")
    return default_trackers


if __name__ == "__main__":
    # Get paths (script is now in docker-envs)
    script_dir = Path(__file__).resolve().parent

    config_file = script_dir / "transmission.config.json"
    trackers_file = script_dir / "transmission.trackers.txt"

    if not trackers_file.exists():
        print(f"Error: {trackers_file.name} not found")
        sys.exit(1)
    if not config_file.exists():
        print(f"Error: {config_file.name} not found")
        sys.exit(1)

    # Update config
    default_trackers = update_transmission_config(str(config_file), str(trackers_file))
