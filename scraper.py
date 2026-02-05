"""
Core scraper: visit Twitter/X profile pages from a list of handles
and extract display name + follower count.

For each handle, we:
  1. Navigate to x.com/<handle>
  2. Intercept the UserByScreenName API response for structured JSON
     (gives exact followers_count as an integer)
  3. Fall back to DOM parsing if the API intercept misses

Supports resume: pass in a set of already-completed handles and
they'll be skipped.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from playwright.async_api import BrowserContext, Page, Response

import config
from utils import parse_follower_text


@dataclass
class ProfileRecord:
    handle: str  # includes @
    display_name: str = ""
    followers: int | None = None

    def to_dict(self) -> dict:
        return {
            "handle": self.handle,
            "display_name": self.display_name,
            "followers": self.followers,
        }


# ---------------------------------------------------------------------------
# Single profile visit
# ---------------------------------------------------------------------------

async def visit_profile(
    context: BrowserContext,
    handle: str,
) -> ProfileRecord:
    """Visit a profile page and return a populated ProfileRecord."""
    clean = handle.lstrip("@")
    profile = ProfileRecord(handle=handle)
    page = await context.new_page()
    got_api = False

    async def _on_response(response: Response) -> None:
        nonlocal got_api
        if "UserByScreenName" not in response.url:
            return
        try:
            body = await response.json()
            _fill_from_user_api(body, profile)
            got_api = True
        except Exception:
            pass

    page.on("response", _on_response)

    url = f"https://x.com/{clean}"
    await page.goto(url, wait_until="domcontentloaded")

    # Wait for the profile header or error
    try:
        await page.wait_for_selector(
            '[data-testid="UserName"], [data-testid="emptyState"], '
            '[data-testid="error-detail"]',
            timeout=10_000,
        )
    except Exception:
        pass

    # Give API response time to arrive
    await asyncio.sleep(1.5)

    # DOM fallback if API didn't deliver
    if not got_api or profile.followers is None:
        await _fill_from_profile_dom(page, profile, clean)

    await page.close()
    return profile


def _fill_from_user_api(payload: dict, profile: ProfileRecord) -> None:
    """Extract display_name + followers from UserByScreenName JSON."""

    def _walk(obj: object) -> None:
        if isinstance(obj, dict):
            if "followers_count" in obj and "screen_name" in obj:
                if not profile.display_name:
                    profile.display_name = obj.get("name", "")
                fc = obj.get("followers_count")
                if isinstance(fc, int):
                    profile.followers = fc
                elif isinstance(fc, str):
                    profile.followers = parse_follower_text(fc)
                return
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(payload)


async def _fill_from_profile_dom(
    page: Page, profile: ProfileRecord, clean_handle: str
) -> None:
    """DOM fallback: parse followers from the profile page."""
    for suffix in ("verified_followers", "followers"):
        link = await page.query_selector(f'a[href="/{clean_handle}/{suffix}"]')
        if link:
            text = await link.inner_text()
            m = re.search(r"([\d,.]+[KMBkmb]?)", text)
            if m:
                profile.followers = parse_follower_text(m.group(1))
                break

    if not profile.display_name:
        name_el = await page.query_selector(
            '[data-testid="UserName"] div[dir="ltr"] > span > span'
        )
        if name_el:
            profile.display_name = (await name_el.inner_text()).strip()


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

async def run_scraper(
    context: BrowserContext,
    handles: list[str],
    done: set[str],
    on_profile_done: callable,
) -> list[dict]:
    """Visit each handle not already in `done`, calling on_profile_done
    after each so results can be saved incrementally.

    Returns the full list of ProfileRecord dicts (new ones only).
    """
    remaining = [h for h in handles if h.lower() not in done]
    total = len(remaining)
    skipped = len(handles) - total

    if skipped:
        print(f"Resuming: {skipped} already completed, {total} remaining.\n")
    else:
        print(f"Processing {total} handles.\n")

    results: list[dict] = []

    for i, handle in enumerate(remaining, 1):
        print(f"  [{i}/{total}] {handle} ...", end=" ", flush=True)
        profile = await visit_profile(context, handle)
        count_str = f"{profile.followers:,}" if profile.followers is not None else "?"
        print(f"{count_str} followers — {profile.display_name}")

        row = profile.to_dict()
        results.append(row)
        on_profile_done(row)

        if i < total:
            await asyncio.sleep(config.PROFILE_VISIT_DELAY_SEC)

    return results
