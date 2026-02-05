"""
Core scraper: search Twitter/X People tab for IEEE-related profiles
and extract handle, display name, and follower count.

Strategy for handling Twitter's virtualized DOM:
  - Twitter destroys off-screen DOM nodes as you scroll.
  - We can't just scroll to the bottom and querySelectorAll — elements
    from earlier in the list will be gone.
  - Instead we extract profile data from whatever cells are currently
    visible BEFORE each scroll, accumulating into a set keyed by handle
    so duplicates are ignored.
  - We also intercept the search API responses to get structured JSON
    directly, which is far more reliable than DOM parsing.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field

from playwright.async_api import BrowserContext, Page, Response

import config
from utils import parse_follower_text


@dataclass
class ProfileRecord:
    handle: str
    display_name: str
    followers: int | None

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
    profiles: list[ProfileRecord] = field(default_factory=list)

    def add(self, profile: ProfileRecord) -> bool:
        """Add profile if not already seen. Returns True if new."""
        key = profile.handle.lower()
        if key in self.seen_handles:
            return False
        self.seen_handles.add(key)
        self.profiles.append(profile)
        return True


def _extract_profiles_from_api(payload: dict, state: ScrapeState) -> int:
    """Parse Twitter's internal search API JSON and add profiles to state.

    Twitter search API responses nest user objects in various places.
    We walk the JSON tree looking for objects that have 'screen_name'
    and 'followers_count' keys.

    Returns the number of new profiles added.
    """
    added = 0
    users_found: list[dict] = []

    def _walk(obj: object) -> None:
        if isinstance(obj, dict):
            # A user object has screen_name + followers_count
            if "screen_name" in obj and "followers_count" in obj:
                users_found.append(obj)
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(payload)

    for user in users_found:
        handle = "@" + user["screen_name"]
        display_name = user.get("name", "")
        followers = user.get("followers_count")
        if isinstance(followers, str):
            followers = parse_follower_text(followers)
        record = ProfileRecord(
            handle=handle,
            display_name=display_name,
            followers=followers,
        )
        if state.add(record):
            added += 1
            print(f"  [API] {handle:30s}  {followers or '?':>10}  {display_name}")

    return added


async def _extract_profiles_from_dom(page: Page, state: ScrapeState) -> int:
    """Fallback: scrape visible user cells from the DOM.

    Returns the number of new profiles added.
    """
    added = 0

    cells = await page.query_selector_all('[data-testid="UserCell"]')
    for cell in cells:
        # Handle is in an <a> whose href is /<handle> or a span with @
        link_el = await cell.query_selector('a[role="link"][href]')
        if not link_el:
            continue
        href = await link_el.get_attribute("href") or ""
        handle_match = re.match(r"^/([A-Za-z0-9_]+)$", href)
        if not handle_match:
            continue
        handle = "@" + handle_match.group(1)

        # Display name: first <span dir="auto"> inside the link tends to
        # be the display name.
        name_span = await link_el.query_selector('span > span')
        display_name = (await name_span.inner_text()).strip() if name_span else ""

        # Follower count: look for text matching a number pattern inside
        # the cell but outside the link.
        full_text = await cell.inner_text()
        follower_match = re.search(
            r"([\d,.]+[KMBkmb]?)\s*[Ff]ollower", full_text
        )
        followers = None
        if follower_match:
            followers = parse_follower_text(follower_match.group(1))

        record = ProfileRecord(
            handle=handle,
            display_name=display_name,
            followers=followers,
        )
        if state.add(record):
            added += 1
            print(f"  [DOM] {handle:30s}  {followers or '?':>10}  {display_name}")

    return added


async def scrape_query(
    context: BrowserContext,
    query: str,
    state: ScrapeState,
) -> None:
    """Run a single search query on Twitter's People tab and scroll
    through results, extracting profiles as we go."""

    page = await context.new_page()

    # --- Intercept API responses for structured data ---
    api_new_count = 0

    async def _on_response(response: Response) -> None:
        nonlocal api_new_count
        url = response.url
        # Twitter search API endpoints we care about
        if "SearchTimeline" not in url and "search/typeahead" not in url:
            return
        try:
            body = await response.json()
            n = _extract_profiles_from_api(body, state)
            api_new_count += n
        except Exception:
            pass

    page.on("response", _on_response)

    # Navigate to the People search tab
    search_url = f"https://x.com/search?q={query}&src=typed_query&f=people"
    print(f"\nSearching: {search_url}")
    await page.goto(search_url, wait_until="domcontentloaded")

    # Wait for results to render (or a "no results" notice)
    try:
        await page.wait_for_selector(
            '[data-testid="UserCell"], [data-testid="emptyState"]',
            timeout=15_000,
        )
    except Exception:
        print("  Timed out waiting for search results — page may require login.")
        await page.close()
        return

    # Check for empty state
    empty = await page.query_selector('[data-testid="emptyState"]')
    if empty:
        print("  No results for this query.")
        await page.close()
        return

    # Scroll loop — collect from API intercepts + DOM fallback
    consecutive_empty = 0
    for scroll_num in range(1, config.MAX_SCROLLS + 1):
        before = len(state.profiles)

        # DOM fallback extraction for whatever is visible right now
        await _extract_profiles_from_dom(page, state)

        # Small pause so API responses have time to arrive
        await asyncio.sleep(0.3)

        after = len(state.profiles)
        new_this_scroll = after - before

        if new_this_scroll == 0:
            consecutive_empty += 1
            if consecutive_empty >= config.MAX_CONSECUTIVE_EMPTY:
                print(
                    f"  Stopping after {scroll_num} scrolls "
                    f"({config.MAX_CONSECUTIVE_EMPTY} consecutive with no new results)."
                )
                break
        else:
            consecutive_empty = 0

        # Scroll down
        await page.evaluate("window.scrollBy(0, window.innerHeight)")
        await asyncio.sleep(config.SCROLL_PAUSE_SEC)

    print(f"  Total unique profiles so far: {len(state.profiles)}")
    await page.close()


async def run_scraper(context: BrowserContext) -> list[dict]:
    """Run all configured search queries and return deduplicated profiles."""
    state = ScrapeState()

    for query in config.SEARCH_QUERIES:
        await scrape_query(context, query, state)

    # If any profiles came from the API without follower counts,
    # we could optionally visit each profile page. For now we skip
    # that to keep the initial version simple and fast.

    return [p.to_dict() for p in state.profiles]
