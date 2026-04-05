#!/usr/bin/env python3
# =============================================================================
# autorijksfetch.py — Rijksmuseum collection fetcher
# =============================================================================
# Originally built against the older Rijksmuseum REST API (api.rijksmuseum.nl).
#
# Updated 2026-04-05 to use the new Linked Art / LOD API:
#
#   Search endpoint  https://data.rijksmuseum.nl/search/collection
#     - Results returned in `orderedItems` (was `member`)
#     - Pagination via `next.id` object (was a raw URL string)
#     - Filter: type=painting&imageAvailable=true
#
#   Per-object metadata  https://id.rijksmuseum.nl/<id>
#     - Title now in `identified_by[].content` (was `_label`)
#     - Artist now in `produced_by.part[].carried_out_by[].notation` (was `carried_out_by._label`)
#     - Date now in `produced_by.timespan.identified_by[0].content` (was `timespan._label`)
#     - Medium and dimensions extracted from `referred_to_by[]` by AAT classifier IDs
#       (was classified by _label strings; `digitally_represented_by` field removed entirely)
#
#   Image resolution  (3-level chain, new)
#     object → `shows[0]` → VisualItem → `digitally_shown_by[0]`
#                         → DigitalObject → `access_point[0].id` (IIIF URL)
#
#   Public domain check  (moved to VisualItem)
#     VisualItem.subject_to[].classified_as[].id — checked for CC0/publicdomain URIs.
#     Non-public-domain artworks are now skipped entirely (no image download or metadata save).
#
#   Paths  anchored to repo root via Path(__file__).parent.parent so the script
#          can be run from any working directory.
# =============================================================================
import os
import requests
import json
import time
from pathlib import Path
from typing import List, Dict, Optional, Any

# ============================================================================
# CONFIGURATION
# ============================================================================
MAX_NEW_ARTWORKS = 20
RATE_LIMIT_DELAY = 1.0  # Seconds between individual item requests

# Paths (relative to repo root, not script location)
_REPO_ROOT = Path(__file__).parent.parent
ARTWORKIDS_FILE = _REPO_ROOT / "public/artworkids.json"
METADATA_OUTPUT_DIR = _REPO_ROOT / "public/metadata"
IMAGES_OUTPUT_DIR = _REPO_ROOT / "public/images"

# The LOD Search Endpoint (No sort parameter to avoid 400 errors)
SEARCH_URL = "https://data.rijksmuseum.nl/search/collection"
INITIAL_PARAMS = {
    "type": "painting",
    "imageAvailable": "true"
}

class LODMapper:
    """Maps Linked Art JSON-LD to your site's original metadata schema."""
    
    # AAT identifiers used in referred_to_by
    AAT_MEDIUM     = "300435429"  # materials/techniques statement
    AAT_DIMENSIONS = "300435430"  # dimensions statement
    AAT_CREDIT     = "300026687"  # credit/acknowledgement
    AAT_LANG_EN    = "300388277"  # English

    @classmethod
    def get_referred_to_by(cls, items: List[Dict], aat_id: str, lang_aat: str = None, primary_only: bool = False) -> str:
        """Extract content from referred_to_by matching a classified_as AAT id."""
        for item in items:
            classified_ids = [c.get("id", "") for c in item.get("classified_as", [])]
            if not any(aat_id in cid for cid in classified_ids):
                continue
            if lang_aat:
                lang_ids = [l.get("id", "") for l in item.get("language", [])]
                if not any(lang_aat in lid for lid in lang_ids):
                    continue
            if primary_only:
                id_contents = [i.get("content") for i in item.get("identified_by", [])]
                if "1" not in id_contents:
                    continue
            return item.get("content", "")
        return ""

    @staticmethod
    def resolve_visual_data(shows: List[Dict]) -> Dict:
        """Walk shows → VisualItem → DigitalObject to get IIIF base URL and public domain status."""
        result = {"iiif_base": "", "is_pd": False}
        if not shows:
            return result
        try:
            visual_item_id = shows[0].get("id")
            if not visual_item_id:
                return result
            vi_resp = requests.get(visual_item_id, headers={"Accept": "application/json"}, timeout=20)
            if vi_resp.status_code != 200:
                return result
            vi_data = vi_resp.json()
            # Public domain: check subject_to rights on the VisualItem
            for right in vi_data.get("subject_to", []):
                for cls_ in right.get("classified_as", []):
                    rid = cls_.get("id", "").lower()
                    if "publicdomain" in rid or "cc0" in rid:
                        result["is_pd"] = True
            digital_shown_by = vi_data.get("digitally_shown_by", [])
            if not digital_shown_by:
                return result
            digital_obj_id = digital_shown_by[0].get("id")
            if not digital_obj_id:
                return result
            do_resp = requests.get(digital_obj_id, headers={"Accept": "application/json"}, timeout=20)
            if do_resp.status_code != 200:
                return result
            do_data = do_resp.json()
            access_points = do_data.get("access_point", [])
            if not access_points:
                return result
            full_url = access_points[0].get("id", "")
            for suffix in ["/full/max/0/default.jpg", "/full/full/0/default.jpg", "/info.json"]:
                if suffix in full_url:
                    result["iiif_base"] = full_url.split(suffix)[0]
                    return result
            result["iiif_base"] = full_url
            return result
        except Exception:
            return result

    @classmethod
    def map_to_old_schema(cls, data: Dict, uri: str, iiif_base: str = "", is_pd: bool = False) -> Dict:
        obj_id = uri.split("/")[-1]

        # Title: prefer English Name (language AAT 300388277), fall back to any Name
        en_title = ""
        any_title = ""
        for ident in data.get("identified_by", []):
            if ident.get("type") == "Name" and ident.get("content"):
                lang_ids = [l.get("id", "") for l in ident.get("language", [])]
                if any(cls.AAT_LANG_EN in lid for lid in lang_ids):
                    if not en_title:
                        en_title = ident["content"]
                elif not any_title:
                    any_title = ident["content"]
        title = en_title or any_title or "Untitled"

        # Artist & Date
        production = data.get("produced_by", {})
        artist = "Unknown"
        # Artist is in produced_by.part[].carried_out_by[], name in notation (@language: en)
        for part in production.get("part", []):
            performers = part.get("carried_out_by", [])
            if performers:
                notations = performers[0].get("notation", [])
                en_name = next((n.get("@value") for n in notations if n.get("@language") == "en"), None)
                artist = en_name or (notations[0].get("@value") if notations else "Unknown")
                break
        # Date: timespan.identified_by[0].content
        timespan = production.get("timespan", {})
        date_entries = timespan.get("identified_by", [])
        date = date_entries[0].get("content", "") if date_entries else ""
        
        referred = data.get("referred_to_by", [])
        medium = cls.get_referred_to_by(referred, cls.AAT_MEDIUM, cls.AAT_LANG_EN)
        dimensions = cls.get_referred_to_by(referred, cls.AAT_DIMENSIONS, cls.AAT_LANG_EN, primary_only=True)
        credit_suffix = cls.get_referred_to_by(referred, cls.AAT_CREDIT, cls.AAT_LANG_EN)
        credit_line = f"Rijksmuseum. {credit_suffix}".rstrip(". ") if credit_suffix else "Rijksmuseum"

        return {
            "objectID": obj_id,
            "title": title,
            "artistDisplayName": artist,
            "objectDate": date,
            "objectName": "painting",
            "medium": medium,
            "dimensions": dimensions,
            "creditLine": credit_line,
            "objectURL": f"https://www.rijksmuseum.nl/en/collection/{obj_id}",
            "department": "Paintings",
            "isPublicDomain": is_pd,
            "primaryImage": f"{iiif_base}/full/843,/0/default.jpg" if iiif_base else "",
            "primaryImageMedium": f"{iiif_base}/full/600,/0/default.jpg" if iiif_base else "",
            "primaryImageSmall": f"{iiif_base}/full/400,/0/default.jpg" if iiif_base else "",
            "localImage": f"{obj_id}.jpg",
            "webImage": f"{iiif_base}/full/max/0/default.jpg" if iiif_base else "",
            "tags": [],
            "facets": {}
        }

class RijksLODFetcher:
    def __init__(self):
        METADATA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        IMAGES_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        # Load as list to preserve Git order, set for fast lookups
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

        print(f"Starting crawl...")

        while new_count < MAX_NEW_ARTWORKS:
            try:
                # Use params only on the first request; 'next' URLs have them baked in
                r = requests.get(
                    current_url, 
                    params=INITIAL_PARAMS if current_url == SEARCH_URL else None,
                    headers={"Accept": "application/json"}, 
                    timeout=30
                )
                
                if r.status_code != 200:
                    print(f"Search failed: {r.status_code} - {r.text}")
                    break
                
                search_data = r.json()
                items = search_data.get("orderedItems", [])
                
                if not items:
                    print("Reached end of search results.")
                    break

                for item in items:
                    if new_count >= MAX_NEW_ARTWORKS: 
                        break
                    
                    uri = item.get("id")
                    if not uri: continue
                    obj_id = uri.split("/")[-1]

                    # If we already have this painting, skip it and keep looking
                    if obj_id in self.processed_set:
                        continue 

                    print(f"Processing New Artwork: {obj_id}")
                    
                    # Resolve Full Metadata via JSON-LD
                    detail_resp = requests.get(uri, headers={"Accept": "application/json"}, timeout=20)
                    if detail_resp.status_code == 200:
                        raw_meta = detail_resp.json()
                        visual_data = LODMapper.resolve_visual_data(raw_meta.get("shows", []))
                        iiif_base = visual_data["iiif_base"]
                        is_pd = visual_data["is_pd"]

                        if not is_pd:
                            print(f"Skipping {obj_id}: not public domain")
                            continue

                        mapped_meta = LODMapper.map_to_old_schema(raw_meta, uri, iiif_base, is_pd)

                        # Download Image via IIIF URL
                        if mapped_meta["primaryImage"]:
                            try:
                                img_data = requests.get(mapped_meta["primaryImage"], timeout=30).content
                                with open(IMAGES_OUTPUT_DIR / f"{obj_id}.jpg", "wb") as f:
                                    f.write(img_data)
                            except Exception as img_err:
                                print(f"Image download failed for {obj_id}: {img_err}")
                                continue

                        # Save individual JSON metadata file
                        with open(METADATA_OUTPUT_DIR / f"{obj_id}.json", "w") as f:
                            json.dump(mapped_meta, f, indent=2)

                        # Track progress
                        self.master_list.append(obj_id)
                        self.processed_set.add(obj_id)
                        new_count += 1
                        time.sleep(RATE_LIMIT_DELAY)

                # Find the 'next' page link (the token bookmark)
                next_page = search_data.get("next")
                if next_page and new_count < MAX_NEW_ARTWORKS:
                    current_url = next_page.get("id", "") if isinstance(next_page, dict) else next_page
                    print("Page full of known items. Flipping to next page...")
                else:
                    break

            except Exception as e:
                print(f"Error during execution: {e}")
                break

        # Save Master List (Stable order: new IDs added to the end)
        with open(ARTWORKIDS_FILE, "w") as f:
            json.dump(self.master_list, f, indent=2)
            
        print(f"Success. Added {new_count} new artworks to the collection.")

if __name__ == "__main__":
    RijksLODFetcher().fetch()
