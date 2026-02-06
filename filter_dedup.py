"""Filter ieee_profiles.csv to only include handles from deduplicated.txt.

Deduplicates the CSV rows (keeps first occurrence with data), then
outputs only rows whose handle appears in deduplicated.txt.
"""

import csv
from pathlib import Path

ROOT = Path(__file__).parent
DEDUP_FILE = ROOT / "deduplicated.txt"
INPUT_CSV = ROOT / "output" / "ieee_profiles.csv"
OUTPUT_CSV = ROOT / "output" / "ieee_profiles_filtered.csv"

# Load deduplicated handles (lowercase for matching)
dedup_handles: set[str] = set()
with open(DEDUP_FILE, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Skip malformed lines (like the mastodon bio line)
        if " " in line:
            continue
        if not line.startswith("@"):
            line = "@" + line
        dedup_handles.add(line.lower())

print(f"Deduplicated list: {len(dedup_handles)} handles")

# Read CSV, deduplicate rows (prefer rows with data), filter to dedup list
best: dict[str, dict] = {}
with open(INPUT_CSV, encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        handle = row.get("handle", "").strip()
        key = handle.lower()
        if key not in dedup_handles:
            continue
        # Keep the first row that has follower data; skip empty dupes
        if key in best:
            existing = best[key]
            if not existing["followers"] and row.get("followers"):
                best[key] = row
        else:
            best[key] = row

# Write filtered output, sorted by followers descending
rows = list(best.values())
rows.sort(
    key=lambda r: (
        r["followers"] != "",
        int(r["followers"]) if r["followers"] and r["followers"].isdigit() else 0,
    ),
    reverse=True,
)

fieldnames = ["handle", "display_name", "followers"]
with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

with_data = sum(1 for r in rows if r.get("followers"))
print(f"Filtered output: {len(rows)} profiles ({with_data} with follower counts)")
print(f"Saved to {OUTPUT_CSV}")
