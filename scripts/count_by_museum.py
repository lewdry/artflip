#!/usr/bin/env python3
"""Count artworks per museum by reading creditLine from public/metadata/*.json"""

import json
import re
from pathlib import Path
from collections import defaultdict

METADATA_DIR = Path(__file__).parent.parent / "public" / "metadata"

MUSEUMS = [
    "Metropolitan Museum of Art",
    "Art Institute of Chicago",
    "Rijksmuseum",
    "National Gallery of Art",
    "Cleveland Museum of Art",
]

# Build a regex that matches museum name at start of creditLine followed by a period
# Rijksmuseum sometimes has no trailing period, so make it optional for that museum only
PATTERN = re.compile(r"^(" + "|".join(re.escape(m) for m in MUSEUMS) + r")(?:\.|\s*$)")

counts = defaultdict(int)
unmatched = 0

for path in METADATA_DIR.glob("*.json"):
    try:
        data = json.loads(path.read_text())
        credit = data.get("creditLine", "")
        m = PATTERN.match(credit)
        if m:
            counts[m.group(1)] += 1
        else:
            unmatched += 1
    except (json.JSONDecodeError, OSError):
        unmatched += 1

ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
total = sum(counts.values())

print(f"\nCurrent Count of artworks - {Path(__file__).name}")
for i, (museum, count) in enumerate(ranked, 1):
    print(f"  {i}. {count:>5}  {museum}")
print(f"\n  Total artworks: {total}")
if unmatched:
    print(f"  (unmatched/skipped: {unmatched})")
print()
