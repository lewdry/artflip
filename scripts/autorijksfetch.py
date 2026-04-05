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
RATE_LIMIT_DELAY = 1.0  # Respectful delay between resolving individual items

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
        # 1. Identification
        obj_id = uri.split("/")[-1]
        
        # 2. Production details (Artist & Date)
        production = data.get("produced_by", {})
        artist = "Unknown"
        if "carried_out_by" in production:
            artist = production["carried_out_by"][0].get("_label", "Unknown")
        
        date = production.get("timespan", {}).get("_label", "")
        
        # 3. Mediums and Types
        mediums = [m.get("_label") for m in data.get("made_of", [])]
        obj_types = [t.get("_label") for t in data.get("classified_as", []) if t.get("type") == "Type"]

        # 4. Image Handling (IIIF Standard)
        iiif_base = ""
        reps = data.get("digitally_represented_by", [])
        if reps:
            views = reps[0].get("has_view", [])
            if views:
                # Extract base ID by stripping the IIIF info.json suffix
                iiif_base = views[0].get("id", "").split("/info.json")[0]

        # 5. Rights
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
        self.processed_ids = self._load_ids()

    def _load_ids(self):
        if ARTWORKIDS_FILE.exists():
            with open(ARTWORKIDS_FILE, "r") as f:
                return set(json.load(f))
        return set()

    def fetch(self):
        # The LOD API is strict: no 'ps' or 'key' allowed. 
        # It returns 100 items by default.
        params = {
            "type": "painting", 
            "imageAvailable": "true" 
        }
        
        print(f"Searching: {SEARCH_URL}")
        
        try:
            r = requests.get(SEARCH_URL, params=params, timeout=30)
            if r.status_code != 200:
                print(f"Search failed: {r.status_code} - {r.text}")
                return
                
            search_data = r.json()
            items = search_data.get("member", [])
        except Exception as e:
            print(f"Search connection error: {e}")
            return

        new_count = 0
        for item in items:
            if new_count >= MAX_NEW_ARTWORKS: 
                break
            
            uri = item.get("id")
            if not uri: continue
            
            obj_id = uri.split("/")[-1]

            if obj_id in self.processed_ids:
                continue

            print(f"Resolving Metadata: {obj_id}")
            
            headers = {"Accept": "application/json"}
            try:
                # Step 2: Fetch full Linked Art JSON for the object
                detail_resp = requests.get(uri, headers=headers, timeout=20)
                if detail_resp.status_code != 200: continue
                
                raw_metadata = detail_resp.json()
                mapped_metadata = LODMapper.map_to_old_schema(raw_metadata, uri)

                # Step 3: Download image via IIIF
                if mapped_metadata["primaryImage"]:
                    img_resp = requests.get(mapped_metadata["primaryImage"], timeout=30)
                    if img_resp.status_code == 200:
                        with open(IMAGES_OUTPUT_DIR / f"{obj_id}.jpg", "wb") as f:
                            f.write(img_resp.content)

                # Step 4: Save metadata JSON
                with open(METADATA_OUTPUT_DIR / f"{obj_id}.json", "w") as f:
                    json.dump(mapped_metadata, f, indent=2)

                self.processed_ids.add(obj_id)
                new_count += 1
                time.sleep(RATE_LIMIT_DELAY)
                
            except Exception as e:
                print(f"Failed to process {obj_id}: {e}")
                continue

        # Final Step: Update the master ID list
        with open(ARTWORKIDS_FILE, "w") as f:
            json.dump(sorted(list(self.processed_ids)), f, indent=2)
        print(f"Success. Added {new_count} new artworks.")

if __name__ == "__main__":
    RijksLODFetcher().fetch()
