#!/usr/bin/env python3
"""Update the additional tracker section from upstream sources.

Keeps the default section untouched, refetches the two source lists,
merges them, removes duplicates, removes trackers already present in the
default section, sorts the result, and writes it back.

Run: python3 update_trackers.py
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

FILE = Path(__file__).with_name("transmission.trackers.txt")

SOURCES = [
    "https://raw.githubusercontent.com/ngosang/trackerslist/refs/heads/master/trackers_best.txt",
    "https://raw.githubusercontent.com/XIU2/TrackersListCollection/refs/heads/master/best.txt",
]


def parse_sections(text: str) -> list[dict]:
    """Split the tracker file into sections (header comments + trackers)."""
    sections: list[dict] = []
    header: list[str] = []
    trackers: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            if trackers:
                sections.append({"header": header, "trackers": trackers})
                header = []
                trackers = []
            header.append(line)
        elif line.strip():
            trackers.append(line.strip())
        else:
            if trackers:
                sections.append({"header": header, "trackers": trackers})
                header = []
                trackers = []
    if header or trackers:
        sections.append({"header": header, "trackers": trackers})
    return sections


def build_file(sections: list[dict]) -> str:
    lines: list[str] = []
    for i, sec in enumerate(sections):
        lines.extend(sec["header"])
        lines.extend(sorted(sec["trackers"], key=str.lower))
        if i < len(sections) - 1:
            lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    text = FILE.read_text()
    sections = parse_sections(text)
    if not sections:
        raise SystemExit("No sections found in tracker file.")

    default_trackers = set(sections[0]["trackers"])

    merged: list[str] = []
    seen: set[str] = set()
    for url in SOURCES:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})  # noqa: S310 - only hardcoded http(s) sources
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - only hardcoded http(s) source URLs are fetched
            for line in resp.read().decode("utf-8").splitlines():
                tracker = line.strip()
                if tracker and tracker not in default_trackers and tracker not in seen:
                    seen.add(tracker)
                    merged.append(tracker)

    if len(sections) > 1:
        sections[1]["trackers"] = merged
    else:
        sections.append(
            {
                "header": [
                    "# additional deduped trackers from:",
                    "# - " + SOURCES[0],
                    "# - " + SOURCES[1],
                ],
                "trackers": merged,
            }
        )

    FILE.write_text(build_file(sections))
    print(
        f"Updated {FILE.name}: default={len(default_trackers)}, additional={len(merged)}"
    )


if __name__ == "__main__":
    main()
