"""
Save Twitter/X authentication state for reuse by the scraper.

Opens a browser window so you can manually log in to Twitter/X.
Once logged in, press Enter in the terminal to save the session cookies
and storage state to auth/twitter_state.json.

Usage:
    python save_auth.py
"""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

AUTH_DIR = Path(__file__).parent / "auth"
STATE_FILE = AUTH_DIR / "twitter_state.json"


async def main() -> None:
    AUTH_DIR.mkdir(exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        await stealth_async(page)

        await page.goto("https://x.com/i/flow/login", wait_until="networkidle")

        print()
        print("=" * 60)
        print("  Log in to Twitter/X in the browser window.")
        print("  When you're fully logged in (home feed visible),")
        print("  come back here and press ENTER to save the session.")
        print("=" * 60)
        print()
        input("Press ENTER after logging in... ")

        await context.storage_state(path=str(STATE_FILE))
        print(f"Auth state saved to {STATE_FILE}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
