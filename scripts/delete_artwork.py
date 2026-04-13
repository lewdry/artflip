#!/usr/bin/env python3
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES_DIR = os.path.join(BASE, "public", "images")
METADATA_DIR = os.path.join(BASE, "public", "metadata")
ARTWORKIDS_FILE = os.path.join(BASE, "public", "artworkids.json")

DONTFETCH_FILES = {
    "Art Institute of Chicago": os.path.join(BASE, "scripts", "chicdontfetch.json"),
    "Cleveland Museum of Art": os.path.join(BASE, "scripts", "clevedontfetch.json"),
    "Metropolitan Museum of Art": os.path.join(BASE, "scripts", "metdontfetch.json"),
    "Minneapolis Institute of Art": os.path.join(BASE, "scripts", "miadontfetch.json"),
    "Rijksmuseum": os.path.join(BASE, "scripts", "rijksdontfetch.json"),
}

object_id = input("Enter objectID to delete: ").strip()
if not object_id:
    print("No objectID entered. Exiting.")
    sys.exit(1)

# --- Read metadata first to determine institution ---
metadata_path = os.path.join(METADATA_DIR, f"{object_id}.json")
if not os.path.exists(metadata_path):
    print(f"Metadata file not found: {metadata_path}")
    sys.exit(1)

with open(metadata_path) as f:
    metadata = json.load(f)

credit_line = metadata.get("creditLine", "")
institution = next((name for name in DONTFETCH_FILES if name in credit_line), None)
if institution is None:
    print(f"Warning: no dontfetch file for institution in creditLine: {credit_line!r}")
    print("Deletion will proceed without adding to a blacklist.")
else:
    print(f"Institution: {institution}")

# --- 1. Delete image ---
image_path = os.path.join(IMAGES_DIR, f"{object_id}.jpg")
if os.path.exists(image_path):
    os.remove(image_path)
    print(f"Deleted image: {image_path}")
else:
    print(f"Image not found (skipping): {image_path}")

# --- 2. Delete metadata ---
os.remove(metadata_path)
print(f"Deleted metadata: {metadata_path}")

# --- 3. Remove from artworkids.json ---
with open(ARTWORKIDS_FILE) as f:
    artwork_ids = json.load(f)

if object_id in artwork_ids:
    artwork_ids.remove(object_id)
    with open(ARTWORKIDS_FILE, "w") as f:
        json.dump(artwork_ids, f, indent=2)
    print(f"Removed {object_id!r} from artworkids.json")
else:
    print(f"{object_id!r} not found in artworkids.json (skipping)")

# --- 4. Add to institution dontfetch list ---
if institution is None:
    print("Skipping blacklist update (no dontfetch file for this institution).")
else:
    dontfetch_path = DONTFETCH_FILES[institution]
    with open(dontfetch_path) as f:
        dontfetch = json.load(f)

    if object_id not in dontfetch:
        dontfetch.append(object_id)
        with open(dontfetch_path, "w") as f:
            json.dump(dontfetch, f, indent=2)
        print(f"Added {object_id!r} to {os.path.basename(dontfetch_path)}")
    else:
        print(f"{object_id!r} already in {os.path.basename(dontfetch_path)}")

print("Done.")
