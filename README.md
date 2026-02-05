# Twitter/X IEEE Profile Scraper

Playwright-stealth scraper that searches Twitter/X for IEEE-related accounts and extracts profile handle, display name, and follower count.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

## Usage

```bash
# 1. Save your login session (opens a browser — log in manually)
python save_auth.py

# 2. Small test run
python main.py --headed --max-scrolls 5

# 3. Full run (headless)
python main.py
```

### CLI Options

| Flag | Description |
|---|---|
| `--headed` | Show the browser window |
| `--max-scrolls N` | Limit scrolls per query (default: 50) |
| `--query "term"` | Override search terms (repeatable) |

## How It Works

Twitter's virtualized rendering destroys off-screen DOM elements as you scroll, making traditional scraping unreliable. This scraper uses two complementary strategies:

1. **API interception** — listens to `SearchTimeline` network responses and extracts user objects with exact follower counts directly from Twitter's backend JSON.
2. **DOM fallback** — parses visible `UserCell` elements on each scroll before they're recycled.

Both methods feed into a deduplicated set keyed by handle.

## Output

Results are saved to `output/` as both CSV and JSON, sorted by follower count descending.

## Configuration

Edit `config.py` to adjust search queries, scroll limits, and rate-limit pauses.
