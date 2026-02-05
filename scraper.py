"""
Core scraper: search Twitter/X People tab for IEEE-related profiles,
then visit each profile page to get follower counts.

Two-phase approach:
  Phase 1 — Search: hit the People search tab for each query, scroll
            through results, and collect handles via API interception
            and DOM fallback.  Twitter's search cards do NOT show
            follower counts, so we only grab handles + display names.
  Phase 2 — Profile visits: for each discovered handle, visit the
            profile page and extract follower count + display name
            from the UserByScreenName API response (or DOM fallback).

This sidesteps the virtualized-DOM problem: we only need the search
page to give us handles (which it does reliably), then we get the
real data from individual profile pages.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from urllib.parse import quote_plus

from playwright.async_api import BrowserContext, Page, Response

import config
from utils import parse_follower_text


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

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


@dataclass
class ScrapeState:
    """Mutable accumulator shared across callbacks."""
    seen_handles: set[str] = field(default_factory=set)
    profiles: dict[str, ProfileRecord] = field(default_factory=dict)

    def add(self, handle: str, display_name: str = "") -> bool:
        """Register a handle. Returns True if it's new."""
        key = handle.lower()
        if key in self.seen_handles:
            # Update display_name if we didn't have one before
            if display_name and not self.profiles[key].display_name:
                self.profiles[key].display_name = display_name
            return False
        self.seen_handles.add(key)
        self.profiles[key] = ProfileRecord(handle=handle, display_name=display_name)
        return True


# ---------------------------------------------------------------------------
# Phase 1 helpers — search result extraction
# ---------------------------------------------------------------------------

def _collect_handles_from_api(payload: dict, state: ScrapeState) -> int:
    """Walk the API JSON tree and pull out screen_name values."""
    added = 0

    def _walk(obj: object) -> None:
        nonlocal added
        if isinstance(obj, dict):
            # Twitter GraphQL nests user data in "legacy" sub-objects
            screen_name = obj.get("screen_name")
            if screen_name and isinstance(screen_name, str) and len(screen_name) <= 15:
                handle = "@" + screen_name
                name = obj.get("name", "")
                if state.add(handle, name):
                    added += 1
                    print(f"  [API] {handle}")
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(payload)
    return added


async def _collect_handles_from_dom(page: Page, state: ScrapeState) -> int:
    """Parse visible UserCell elements for handles."""
    added = 0
    cells = await page.query_selector_all('[data-testid="UserCell"]')
    for cell in cells:
        # Every UserCell has links — find the one whose href is /<handle>
        links = await cell.query_selector_all('a[href]')
        for link in links:
            href = await link.get_attribute("href") or ""
            m = re.match(r"^/([A-Za-z0-9_]{1,15})$", href)
            if not m:
                continue
            handle = "@" + m.group(1)
            # Try to get display name from the cell text
            display_name = ""
            spans = await cell.query_selector_all('div[dir="ltr"] > span')
            for span in spans:
                text = (await span.inner_text()).strip()
                if text and not text.startswith("@"):
                    display_name = text
                    break
            if state.add(handle, display_name):
                added += 1
                print(f"  [DOM] {handle}")
            break  # one handle per cell
    return added


async def _search_phase(context: BrowserContext, state: ScrapeState) -> None:
    """Phase 1: run search queries and collect handles."""

    for query in config.SEARCH_QUERIES:
        page = await context.new_page()

        # Intercept API responses
        async def _on_response(response: Response) -> None:
            if "SearchTimeline" not in response.url:
                return
            try:
                body = await response.json()
                _collect_handles_from_api(body, state)
            except Exception:
                pass

        page.on("response", _on_response)

        search_url = (
            f"https://x.com/search?q={quote_plus(query)}"
            f"&src=typed_query&f=user"
        )
        print(f"\n--- Phase 1: Searching '{query}' ---")
        print(f"URL: {search_url}")
        await page.goto(search_url, wait_until="domcontentloaded")

        # Wait for results or empty state
        try:
            await page.wait_for_selector(
                '[data-testid="UserCell"], [data-testid="emptyState"]',
                timeout=15_000,
            )
        except Exception:
            print("  Timed out waiting for results — session may have expired.")
            await page.close()
            continue

        empty = await page.query_selector('[data-testid="emptyState"]')
        if empty:
            print("  No results.")
            await page.close()
            continue

        # Scroll and collect
        consecutive_empty = 0
        for scroll_num in range(1, config.MAX_SCROLLS + 1):
            before = len(state.seen_handles)

            await _collect_handles_from_dom(page, state)
            await asyncio.sleep(0.3)  # let API responses arrive

            after = len(state.seen_handles)
            if after == before:
                consecutive_empty += 1
                if consecutive_empty >= config.MAX_CONSECUTIVE_EMPTY:
                    print(f"  Stopping after {scroll_num} scrolls (no new results).")
                    break
            else:
                consecutive_empty = 0

            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await asyncio.sleep(config.SCROLL_PAUSE_SEC)

        print(f"  Handles found so far: {len(state.seen_handles)}")
        await page.close()


# ---------------------------------------------------------------------------
# Phase 2 helpers — individual profile page visits
# ---------------------------------------------------------------------------

async def _visit_profile(
    context: BrowserContext,
    profile: ProfileRecord,
) -> None:
    """Visit a single profile page and fill in display_name + followers."""
    clean = profile.handle.lstrip("@")
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
                return  # found it
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
    # Follower link: /handle/verified_followers or /handle/followers
    for suffix in ("verified_followers", "followers"):
        link = await page.query_selector(f'a[href="/{clean_handle}/{suffix}"]')
        if link:
            text = await link.inner_text()
            m = re.search(r"([\d,.]+[KMBkmb]?)", text)
            if m:
                profile.followers = parse_follower_text(m.group(1))
                break

    # Display name fallback
    if not profile.display_name:
        name_el = await page.query_selector(
            '[data-testid="UserName"] div[dir="ltr"] > span > span'
        )
        if name_el:
            profile.display_name = (await name_el.inner_text()).strip()


async def _profile_phase(context: BrowserContext, state: ScrapeState) -> None:
    """Phase 2: visit each profile page to get follower counts."""
    profiles = list(state.profiles.values())
    total = len(profiles)
    print(f"\n--- Phase 2: Visiting {total} profile pages ---")

    for i, profile in enumerate(profiles, 1):
        print(f"  [{i}/{total}] {profile.handle} ...", end=" ", flush=True)
        await _visit_profile(context, profile)
        count_str = f"{profile.followers:,}" if profile.followers is not None else "?"
        print(f"{count_str} followers — {profile.display_name}")
        if i < total:
            await asyncio.sleep(config.PROFILE_VISIT_DELAY_SEC)


# ---------------------------------------------------------------------------
# IEEE filter
# ---------------------------------------------------------------------------

def _is_ieee_related(profile: ProfileRecord) -> bool:
    """Return True if handle or display name contains 'ieee' (case-insensitive)."""
    text = f"{profile.handle} {profile.display_name}".lower()
    return "ieee" in text


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_scraper(context: BrowserContext) -> list[dict]:
    """Run the full two-phase scrape and return deduplicated, filtered profiles."""
    state = ScrapeState()

    # Phase 1: collect handles from search
    await _search_phase(context, state)

    if not state.profiles:
        return []

    # Phase 2: visit each profile for follower counts
    await _profile_phase(context, state)

    # Filter for IEEE-related profiles
    results = [
        p.to_dict()
        for p in state.profiles.values()
        if _is_ieee_related(p)
    ]

    filtered_out = len(state.profiles) - len(results)
    if filtered_out:
        print(f"\nFiltered out {filtered_out} non-IEEE profiles.")

    return results
