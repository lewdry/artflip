#!/usr/bin/env python3
import os
import requests
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any

# ============================================================================
# CONFIGURATION
# ============================================================================
MAX_NEW_ARTWORKS = 10
SEARCH_PAGE_SIZE = 50
RATE_LIMIT_DELAY = 1.0

# Paths
ARTWORKIDS_FILE = Path("public/artworkids.json")
METADATA_OUTPUT_DIR = Path("public/metadata")
IMAGES_OUTPUT_DIR = Path("public/images")

# Endpoints
SEARCH_URL = "https://data.rijksmuseum.nl/search/collection"

class LODMapper:
    """Handles mapping Linked Art JSON to the original metadata schema."""
    
    @staticmethod
    def get_value_by_classification(items: List[Dict], classification_label: str) -> str:
        for item in items:
            classifications = item.get("classified_as", [])
            if any(c.get("_label") == classification_label for c in classifications):
                return item.get("content", item.get("_label", ""))
        return ""

    @classmethod
    def map_to_old_schema(cls, data: Dict, uri: str) -> Dict:
        # 1. Extraction Logic
        obj_id = uri.split("/")[-1]
        
        # Production details (Artist & Date)
        production = data.get("produced_by", {})
        artist = ""
        if "carried_out_by" in production:
            artist = production["carried_out_by"][0].get("_label", "Unknown")
        
        date = production.get("timespan", {}).get("_label", "")
        
        # Mediums and Types
        mediums = [m.get("_label") for m in data.get("made_of", [])]
        obj_types = [t.get("_label") for t in data.get("classified_as", []) if t.get("type") == "Type"]

        # Image Handling (IIIF)
        iiif_base = ""
        reps = data.get("digitally_represented_by", [])
        if reps:
            # Navigate to the IIIF service ID
            views = reps[0].get("has_view", [])
            if views:
                iiif_base = views[0].get("id", "").split("/info.json")[0]

        # Rights / Public Domain
        rights = data.get("rights", "")
        is_pd = "publicdomain" in rights.lower() or "cc0" in rights.lower()

        # 2. Build the exact dictionary from your previous script
        return {
            "objectID": obj_id,
            "title": data.get("_label", "Untitled"),
            "artistDisplayName": artist,
            "objectDate": date,
            "objectName": obj_types[0] if obj_types else "painting",
            "medium": ", ".join(mediums),
            "dimensions": cls.get_value_by_classification(data.get("referred_to_by", []), "dimensions"),
            "creditLine": f"Rijksmuseum. {cls.get_value_by_classification(data.get('referred_to_by', []), 'credit line')}",
            "objectURL": f"https://www.rijksmuseum.nl/en/collection/{obj_id}",
            "department": "Paintings", # Simplified mapping
            "isPublicDomain": is_pd,
            "primaryImage": f"{iiif_base}/full/843,/0/default.jpg" if iiif_base else "",
            "primaryImageMedium": f"{iiif_base}/full/600,/0/default.jpg" if iiif_base else "",
            "primaryImageSmall": f"{iiif_base}/full/400,/0/default.jpg" if iiif_base else "",
            "localImage": f"{obj_id}.jpg",
            "webImage": f"{iiif_base}/full/max/0/default.jpg" if iiif_base else "",
            "tags": obj_types,
            "facets": {} # The LOD API handles facets differently, keeping empty to avoid breaks
        }

class RijksLODFetcher:
    def __init__(self):
        METADATA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        IMAGES_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.processed_ids = self._load_ids()

    def _load_ids(self):
        if ARTWORKIDS_FILE.exists():
            return set(json.load(open(ARTWORKIDS_FILE)))
        return set()

    def fetch(self):
        # Step 1: Search (LOD search uses 'type' and 'imageAvailable')
        params = {"type": "painting", "imageAvailable": "true", "ps": SEARCH_PAGE_SIZE}
        print(f"Searching: {SEARCH_URL}")
        
        try:
            r = requests.get(SEARCH_URL, params=params)
            r.raise_for_status()
            search_data = r.json()
            items = search_data.get("member", [])
        except Exception as e:
            print(f"Search failed: {e}")
            return

        new_count = 0
        for item in items:
            if new_count >= MAX_NEW_ARTWORKS: break
            uri = item.get("id")
            obj_id = uri.split("/")[-1]

            if obj_id in self.processed_ids:
                continue

            print(f"Processing: {obj_id}")
            # Step 2: Resolve full metadata
            headers = {"Accept": "application/json"}
            detail_resp = requests.get(uri, headers=headers)
            if detail_resp.status_code != 200: continue
            
            raw_metadata = detail_resp.json()
            mapped_metadata = LODMapper.map_to_old_schema(raw_metadata, uri)

            # Step 3: Download image
            if mapped_metadata["primaryImage"]:
                img_data = requests.get(mapped_metadata["primaryImage"]).content
                with open(IMAGES_OUTPUT_DIR / f"{obj_id}.jpg", "wb") as f:
                    f.write(img_data)

            # Step 4: Save JSON
            with open(METADATA_OUTPUT_DIR / f"{obj_id}.json", "w") as f:
                json.dump(mapped_metadata, f, indent=2)

            self.processed_ids.add(obj_id)
            new_count += 1
            time.sleep(RATE_LIMIT_DELAY)

        # Update Master List
        with open(ARTWORKIDS_FILE, "w") as f:
            json.dump(sorted(list(self.processed_ids)), f, indent=2)

if __name__ == "__main__":
    RijksLODFetcher().fetch()
