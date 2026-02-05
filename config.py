"""Scraper configuration."""

from pathlib import Path

# --- Paths ---
ROOT_DIR = Path(__file__).parent
AUTH_DIR = ROOT_DIR / "auth"
OUTPUT_DIR = ROOT_DIR / "output"
STATE_FILE = AUTH_DIR / "twitter_state.json"
HANDLES_FILE = ROOT_DIR / "handles.txt"

# --- Browser ---
HEADLESS = True
SLOW_MO = 0  # ms between actions; raise to 100-300 for debugging
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
VIEWPORT = {"width": 1280, "height": 900}

# --- Rate-limit ---
PROFILE_VISIT_DELAY_SEC = 2.0  # pause between individual profile page visits

# --- Output ---
CSV_FILE = OUTPUT_DIR / "ieee_profiles.csv"
JSON_FILE = OUTPUT_DIR / "ieee_profiles.json"
