"""Shared utilities for parsing and I/O."""

import csv
import json
import re
from pathlib import Path


def parse_follower_text(raw: str) -> int | None:
    """Convert display strings like '12.5K', '1.2M', '350' to an integer.

    Returns None if the string can't be parsed.
    """
    raw = raw.strip().upper().replace(",", "")
    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}

    m = re.match(r"^([\d.]+)\s*([KMB])?$", raw)
    if not m:
        return None
    number = float(m.group(1))
    suffix = m.group(2)
    if suffix:
        number *= multipliers[suffix]
    return int(number)


def save_csv(profiles: list[dict], path: Path) -> None:
    """Write profiles to a CSV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["handle", "display_name", "followers"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(profiles)
    print(f"Saved {len(profiles)} profiles to {path}")


def save_json(profiles: list[dict], path: Path) -> None:
    """Write profiles to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(profiles)} profiles to {path}")
