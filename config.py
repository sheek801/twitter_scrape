"""Scraper configuration."""

from pathlib import Path

# --- Paths ---
ROOT_DIR = Path(__file__).parent
AUTH_DIR = ROOT_DIR / "auth"
OUTPUT_DIR = ROOT_DIR / "output"
STATE_FILE = AUTH_DIR / "twitter_state.json"

# --- Search ---
# Each query is run via Twitter's People search tab.
SEARCH_QUERIES: list[str] = [
    "IEEE",
]

# --- Browser ---
HEADLESS = True
SLOW_MO = 0  # ms between actions; raise to 100-300 for debugging
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
VIEWPORT = {"width": 1280, "height": 900}

# --- Scroll / rate-limit ---
SCROLL_PAUSE_SEC = 2.0  # pause between scrolls to let DOM render
MAX_SCROLLS = 50  # safety cap per search query
MAX_CONSECUTIVE_EMPTY = 5  # stop scrolling after N scrolls with no new results
PROFILE_VISIT_DELAY_SEC = 2.0  # pause between individual profile page visits

# --- Output ---
CSV_FILE = OUTPUT_DIR / "ieee_profiles.csv"
JSON_FILE = OUTPUT_DIR / "ieee_profiles.json"
