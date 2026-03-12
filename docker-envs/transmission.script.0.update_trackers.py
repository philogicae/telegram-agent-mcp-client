#!/usr/bin/env python3
"""Script to update Transmission default trackers from trackers.txt file"""

import json
import os


def load_trackers(trackers_file):
    """Load trackers from file and filter out comments"""
    trackers = []
    with open(trackers_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                trackers.append(line)
    return trackers


def update_transmission_config(config_file, trackers_file):
    """Update Transmission config with default trackers"""
    # Load trackers
    trackers = load_trackers(trackers_file)

    # Format according to Transmission docs:
    # - Double newline for additional trackers
    # - Single newline for backup trackers
    # We'll use double newlines for all to ensure they're all used
    default_trackers = "\n\n".join(trackers)

    # Load existing config
    with open(config_file, "r") as f:
        config = json.load(f)

    # Update default-trackers
    config["default-trackers"] = default_trackers

    # Save updated config
    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)

    print(f"Updated {config_file} with {len(trackers)} trackers")
    return default_trackers


if __name__ == "__main__":
    # Get paths (script is now in docker-envs)
    script_dir = os.path.dirname(os.path.abspath(__file__))

    config_file = os.path.join(script_dir, "transmission.config.json")
    trackers_file = os.path.join(script_dir, "transmission.trackers.txt")

    # Update config
    default_trackers = update_transmission_config(config_file, trackers_file)
