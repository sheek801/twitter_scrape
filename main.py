#!/usr/bin/env python3
"""
Twitter/X IEEE Profile Scraper — entry point.

Usage:
    # First time: save your login session
    python save_auth.py

    # Then run the scraper
    python main.py                 # headless (default)
    python main.py --headed        # watch the browser
    python main.py --max-scrolls 5 # small test run
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

import config
from scraper import run_scraper
from utils import save_csv, save_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Twitter/X for IEEE-related profiles."
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in headed mode (visible window).",
    )
    parser.add_argument(
        "--max-scrolls",
        type=int,
        default=None,
        help=f"Override max scrolls per query (default: {config.MAX_SCROLLS}).",
    )
    parser.add_argument(
        "--query",
        type=str,
        action="append",
        default=None,
        help="Override search queries. Can be specified multiple times.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    # Apply CLI overrides
    if args.max_scrolls is not None:
        config.MAX_SCROLLS = args.max_scrolls
    if args.query:
        config.SEARCH_QUERIES = args.query
    headless = not args.headed

    # Check auth state
    if not config.STATE_FILE.exists():
        print(f"Auth state not found at {config.STATE_FILE}")
        print("Run `python save_auth.py` first to log in and save your session.")
        sys.exit(1)

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

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

        # Apply stealth at context level — all pages inherit evasions
        await Stealth().apply_stealth_async(context)

        profiles = await run_scraper(context)

        await browser.close()

    if not profiles:
        print("\nNo profiles found. Check that your auth session is still valid.")
        sys.exit(0)

    # Sort by follower count (descending), unknowns at the end
    profiles.sort(
        key=lambda p: (p["followers"] is not None, p["followers"] or 0),
        reverse=True,
    )

    save_csv(profiles, config.CSV_FILE)
    save_json(profiles, config.JSON_FILE)

    print(f"\nDone. {len(profiles)} unique IEEE-related profiles collected.")


if __name__ == "__main__":
    asyncio.run(main())
