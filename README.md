# Twitter/X IEEE Profile Scraper

Playwright-stealth scraper that reads a list of Twitter/X handles and extracts display name and follower count for each. Saves results incrementally so interrupted runs can be resumed.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

## Usage

```bash
# 1. Save your login session (opens a browser — log in manually)
python save_auth.py

# 2. Add your handles to handles.txt (one per line)

# 3. Test with a small batch
python main.py --headed --limit 5

# 4. Full run (headless)
python main.py
```

### CLI Options

| Flag | Description |
|---|---|
| `--headed` | Show the browser window |
| `--limit N` | Only process the first N handles |
| `--handles FILE` | Use a custom handles file (default: handles.txt) |

### Resume Support

Results are saved to CSV after each profile. If the run is interrupted (Ctrl+C, network issue, etc.), just re-run the same command — it will skip handles already in the output CSV and pick up where it left off.

## How It Works

For each handle in the input file, the scraper:

1. Opens `x.com/<handle>` in a stealth Playwright browser
2. Intercepts the `UserByScreenName` API response for structured JSON (exact follower count as an integer)
3. Falls back to DOM parsing if the API intercept misses

No official Twitter API access required — the scraper reads the same internal API responses that Twitter's own frontend receives.

## Output

Results are saved to `output/` as both CSV and JSON, sorted by follower count descending.

## Configuration

Edit `config.py` to adjust the delay between profile visits and browser settings.
