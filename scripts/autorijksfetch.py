#!/usr/bin/env python3
import os
import requests
import json
import time
from pathlib import Path
from typing import List, Dict, Optional, Any

# ============================================================================
# CONFIGURATION
# ============================================================================
MAX_NEW_ARTWORKS = 10
RATE_LIMIT_DELAY = 1.0  # Seconds between individual item requests

# Paths
ARTWORKIDS_FILE = Path("public/artworkids.json")
METADATA_OUTPUT_DIR = Path("public/metadata")
IMAGES_OUTPUT_DIR = Path("public/images")

# Endpoints
# Note: 's=chronologic' ensures we see the most recently added items first
SEARCH_URL = "https://data.rijksmuseum.nl/search/collection?type=painting&imageAvailable=true&s=chronologic"

class LODMapper:
    """Maps Linked Art JSON-LD to your site's original metadata schema."""
    
    @staticmethod
    def get_value_by_classification(items: List[Dict], classification_label: str) -> str:
        for item in items:
            classifications = item.get("classified_as", [])
            if any(c.get("_label") == classification_label for c in classifications):
                return item.get("content", item.get("_label", ""))
        return ""

    @classmethod
    def map_to_old_schema(cls, data: Dict, uri: str) -> Dict:
        obj_id = uri.split("/")[-1]
        
        # Artist & Date
        production = data.get("produced_by", {})
        artist = "Unknown"
        if "carried_out_by" in production:
            artist = production["carried_out_by"][0].get("_label", "Unknown")
        date = production.get("timespan", {}).get("_label", "")
        
        # Categories & Medium
        mediums = [m.get("_label") for m in data.get("made_of", [])]
        obj_types = [t.get("_label") for t in data.get("classified_as", []) if t.get("type") == "Type"]

        # IIIF Image Logic
        iiif_base = ""
        reps = data.get("digitally_represented_by", [])
        if reps:
            views = reps[0].get("has_view", [])
            if views:
                iiif_base = views[0].get("id", "").split("/info.json")[0]

        rights = data.get("rights", "")
        is_pd = any(term in rights.lower() for term in ["publicdomain", "cc0"])

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
            "department": "Paintings",
            "isPublicDomain": is_pd,
            "primaryImage": f"{iiif_base}/full/843,/0/default.jpg" if iiif_base else "",
            "primaryImageMedium": f"{iiif_base}/full/600,/0/default.jpg" if iiif_base else "",
            "primaryImageSmall": f"{iiif_base}/full/400,/0/default.jpg" if iiif_base else "",
            "localImage": f"{obj_id}.jpg",
            "webImage": f"{iiif_base}/full/max/0/default.jpg" if iiif_base else "",
            "tags": obj_types,
            "facets": {}
        }

class RijksLODFetcher:
    def __init__(self):
        METADATA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        IMAGES_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        # We use a list to preserve order for Git, but check existence via set
        self.master_list = self._load_ids()
        self.processed_set = set(self.master_list)

    def _load_ids(self) -> List[str]:
        if ARTWORKIDS_FILE.exists():
            with open(ARTWORKIDS_FILE, "r") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        return []

    def fetch(self):
        current_url = SEARCH_URL
        new_count = 0

        print(f"Starting crawl from: {current_url}")

        while new_count < MAX_NEW_ARTWORKS:
            try:
                # Use GET with Accept header for JSON-LD
                r = requests.get(current_url, headers={"Accept": "application/json"}, timeout=30)
                if r.status_code != 200:
                    print(f"Search failed: {r.status_code}")
                    break
                
                search_data = r.json()
                items = search_data.get("member", [])
                
                if not items:
                    print("End of collection reached.")
                    break

                for item in items:
                    if new_count >= MAX_NEW_ARTWORKS: break
                    
                    uri = item.get("id")
                    if not uri: continue
                    obj_id = uri.split("/")[-1]

                    if obj_id in self.processed_set:
                        continue 

                    print(f"Adding New: {obj_id}")
                    
                    # Resolve Metadata
                    detail_resp = requests.get(uri, headers={"Accept": "application/json"}, timeout=20)
                    if detail_resp.status_code == 200:
                        raw_meta = detail_resp.json()
                        mapped_meta = LODMapper.map_to_old_schema(raw_meta, uri)

                        # Download Image
                        if mapped_meta["primaryImage"]:
                            img_data = requests.get(mapped_meta["primaryImage"], timeout=30).content
                            with open(IMAGES_OUTPUT_DIR / f"{obj_id}.jpg", "wb") as f:
                                f.write(img_data)

                        # Save Individual Metadata File
                        with open(METADATA_OUTPUT_DIR / f"{obj_id}.json", "w") as f:
                            json.dump(mapped_meta, f, indent=2)

                        # Update Tracking
                        self.master_list.append(obj_id)
                        self.processed_set.add(obj_id)
                        new_count += 1
                        time.sleep(RATE_LIMIT_DELAY)

                # Page Flipping Logic
                next_page = search_data.get("next")
                if next_page and new_count < MAX_NEW_ARTWORKS:
                    current_url = next_page
                else:
                    break

            except Exception as e:
                print(f"Crawl Error: {e}")
                break

        # Save Master List (NO SORTING - preserves original order for clean Git diffs)
        with open(ARTWORKIDS_FILE, "w") as f:
            json.dump(self.master_list, f, indent=2)
            
        print(f"Finished. {new_count} new artworks added to public/metadata.")

if __name__ == "__main__":
    RijksLODFetcher().fetch()
