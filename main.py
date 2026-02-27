#!/usr/bin/env python3
"""
Twitter/X IEEE Profile Scraper — entry point.

Reads handles from a text file (one per line), visits each profile
page, and extracts display name + follower count.  Saves results
incrementally so interrupted runs can be resumed.

Usage:
    python save_auth.py                       # first time only
    python main.py                            # headless, all handles
    python main.py --headed                   # watch the browser
    python main.py --limit 20                 # first 20 handles only
    python main.py --handles my_handles.txt   # custom input file
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

import config
from scraper import run_scraper
from utils import save_json


FIELDNAMES = ["handle", "display_name", "followers"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Twitter/X profiles for follower counts."
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in headed mode (visible window).",
    )
    parser.add_argument(
        "--handles",
        type=str,
        default=None,
        help=f"Path to handles file (default: {config.HANDLES_FILE}).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N handles (for testing).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-scrape all handles even if they already exist in the output CSV.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Custom output CSV path (default: output/ieee_profiles.csv).",
    )
    return parser.parse_args()


def load_handles(path: Path, limit: int | None = None) -> list[str]:
    """Load handles from a text file, one per line.

    Accepts lines with or without @ prefix, ignores blanks and # comments.
    """
    if not path.exists():
        print(f"Handles file not found: {path}")
        sys.exit(1)

    handles: list[str] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Normalize: ensure @ prefix
            if not line.startswith("@"):
                line = "@" + line
            handles.append(line)

    if limit is not None:
        handles = handles[:limit]

    return handles


def load_completed(path: Path) -> set[str]:
    """Read the existing output CSV and return a set of lowercase handles
    that have already been scraped (for resume support)."""
    if not path.exists():
        return set()

    done: set[str] = set()
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            h = row.get("handle", "").strip().lower()
            if h:
                done.add(h)
    return done


def make_csv_appender(path: Path) -> callable:
    """Return a callback that appends one row to the CSV each time it's called.

    Creates the file with headers if it doesn't exist yet.
    """
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()

    def _append(row: dict) -> None:
        with open(path, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writerow(row)

    return _append


async def main() -> None:
    args = parse_args()

    handles_path = Path(args.handles) if args.handles else config.HANDLES_FILE
    headless = not args.headed

    # Check prerequisites
    if not config.STATE_FILE.exists():
        print(f"Auth state not found at {config.STATE_FILE}")
        print("Run `python save_auth.py` first to log in and save your session.")
        sys.exit(1)

    handles = load_handles(handles_path, limit=args.limit)
    if not handles:
        print("No handles to process.")
        sys.exit(0)

    print(f"Loaded {len(handles)} handles from {handles_path}")

    output_csv = Path(args.output) if args.output else config.CSV_FILE
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Check what's already done (resume support) — skip if --force
    done = set() if args.force else load_completed(output_csv)
    append_row = make_csv_appender(output_csv)

    print("Launching browser...")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            slow_mo=config.SLOW_MO,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            storage_state=str(config.STATE_FILE),
            viewport=config.VIEWPORT,
            user_agent=config.USER_AGENT,
        )

        await Stealth().apply_stealth_async(context)

        new_results = await run_scraper(context, handles, done, append_row)

        await browser.close()

    # Rebuild full JSON from CSV (includes both old + new)
    all_profiles: list[dict] = []
    if output_csv.exists():
        with open(output_csv, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Convert followers back to int
                fc = row.get("followers", "")
                row["followers"] = int(fc) if fc and fc.isdigit() else None
                all_profiles.append(row)

    all_profiles.sort(
        key=lambda p: (p["followers"] is not None, p["followers"] or 0),
        reverse=True,
    )
    save_json(all_profiles, config.JSON_FILE)

    print(f"\nDone. {len(new_results)} new profiles scraped this run.")
    print(f"Total in output: {len(all_profiles)} profiles.")


if __name__ == "__main__":
    asyncio.run(main())
