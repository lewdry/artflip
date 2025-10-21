#!/usr/bin/env python3
"""
Count museum names from public/metadata JSON files.
For each JSON file, read `creditLine`, extract text before the first period and treat that as the museum name.
Print a sorted list of museums with counts and a total.
"""
import json
from pathlib import Path
from collections import Counter

METADATA_DIR = Path(__file__).resolve().parents[1] / 'public' / 'metadata'

def extract_museum(credit_line):
    if not credit_line or not isinstance(credit_line, str):
        return 'UNKNOWN'
    # split on first period
    parts = credit_line.split('.', 1)
    name = parts[0].strip()
    return name if name else 'UNKNOWN'


def main():
    if not METADATA_DIR.exists():
        print(f"Metadata directory not found: {METADATA_DIR}")
        return

    files = sorted(METADATA_DIR.glob('*.json'))
    counter = Counter()
    total = 0
    errors = 0

    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding='utf-8'))
            credit = data.get('creditLine') or data.get('CreditLine') or ''
            museum = extract_museum(credit)
            counter[museum] += 1
            total += 1
        except Exception as e:
            print(f"Failed to read {fp}: {e}")
            errors += 1

    # Print results
    for name, count in counter.most_common():
        print(f"{count:5d}  {name}")

    print("\nTotal files processed:", total)
    if errors:
        print("Files failed:", errors)

if __name__ == '__main__':
    main()
