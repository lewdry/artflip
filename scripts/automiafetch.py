#!/usr/bin/env python3
# =============================================================================
# automiafetch.py — Minneapolis Institute of Art collection fetcher
# =============================================================================
# Built against the MIA search API (search.artsmia.org).
#
#   Search endpoint  https://search.artsmia.org/{query}
#     - Elasticsearch-backed query string search
#     - All metadata is embedded in search results (_source), so no
#       separate per-object API call is needed
#     - Filters:
#         classification:"Paintings"   — paintings only
#         rights_type:"Public Domain"  — public domain only
#         image:valid                  — has an image
#         room:G*                      — currently on view in a gallery
#     - `restricted` artworks (image rights caveat despite PD rights_type)
#       are skipped at parse time; not excluded by the search query because
#       the field is absent on most records and `NOT restricted:1` would
#       also exclude records where the field doesn't exist in old ES versions
#     - Paginated via Elasticsearch `size` + `from` params (100 per page)
#     - Capped at MAX_SEARCH_RESULTS_CAP total items
#
#   Image  http://api.artsmia.org/images/{id}/large.jpg
#     - "large" = 800px on the long side (closest to the ~843px target
#       used by the other fetch scripts)
#     - No authentication or special headers required
#
#   ID format  numeric integers; stored in artworkids.json as "mia-{id}"
#     ("mia-" prefix avoids collision with Met and ARTIC numeric IDs
#     in the shared list)
#     - load_existing_ids() filters to IDs beginning with "mia-"
#     - Metadata saved as mia-{id}.json, image as mia-{id}.jpg
#
#   Paths  anchored to repo root via Path(__file__).parent.parent so the
#          script can be run from any working directory.
# =============================================================================
import time
import requests
import json
import urllib.parse
from pathlib import Path
from typing import List, Dict, Optional, Set
from datetime import datetime

# ============================================================================
# CONFIGURATION
# ============================================================================

MAX_NEW_ARTWORKS = 20
RATE_LIMIT_DELAY = 1.0  # seconds between image downloads

# Elasticsearch query string — all filters baked in
SEARCH_QUERY = (
    'classification:"Paintings" AND rights_type:"Public Domain" '
    'AND image:valid AND room:G*'
)

# Pagination
SEARCH_PAGE_SIZE = 100       # records per page (ES max is typically 10 000)
MAX_SEARCH_RESULTS_CAP = 10000  # safety cap on total items collected

# Paths (relative to repo root, not script location)
_REPO_ROOT = Path(__file__).parent.parent
ARTWORKIDS_FILE = _REPO_ROOT / "public/artworkids.json"
METADATA_OUTPUT_DIR = _REPO_ROOT / "public/metadata"
IMAGES_OUTPUT_DIR = _REPO_ROOT / "public/images"
DONTFETCH_FILE = Path(__file__).parent / "miadontfetch.json"

# ============================================================================
# MIA API endpoints
# ============================================================================
SEARCH_BASE = "https://search.artsmia.org"
IMAGE_CDN_BASE = "https://img.artsmia.org/web_objects_cache"


# ============================================================================
# Downloader class
# ============================================================================
class MIADownloader:
    def __init__(self):
        self.existing_ids: Set[str] = set()
        self.blacklist_ids: Set[str] = set()
        self.downloaded_count = 0
        self.failed_downloads: List[Dict] = []
        self.successful_downloads: List[Dict] = []
        self.newly_blacklisted: List[Dict] = []

        METADATA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        IMAGES_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---------- File loaders ----------

    def load_existing_ids(self) -> Set[str]:
        """Load MIA artwork IDs from artworkids.json.
        MIA IDs are stored with "mia-" prefix to avoid collision with
        Met and ARTIC numeric IDs in the shared list.
        """
        try:
            if ARTWORKIDS_FILE.exists():
                with open(ARTWORKIDS_FILE, "r", encoding="utf-8") as f:
                    all_ids = json.load(f)
                return {i for i in all_ids if isinstance(i, str) and i.startswith("mia-")}
            return set()
        except Exception:
            return set()

    def load_blacklist(self) -> Set[str]:
        try:
            if DONTFETCH_FILE.exists():
                with open(DONTFETCH_FILE, "r", encoding="utf-8") as f:
                    return set(json.load(f))
            return set()
        except Exception:
            return set()

    def add_to_blacklist(self, mia_id: str, reason: str = "") -> bool:
        try:
            if mia_id in self.blacklist_ids:
                return True
            self.blacklist_ids.add(mia_id)
            existing = []
            if DONTFETCH_FILE.exists():
                with open(DONTFETCH_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            if mia_id not in existing:
                existing.append(mia_id)
                existing.sort()
                with open(DONTFETCH_FILE, "w", encoding="utf-8") as f:
                    json.dump(existing, f, indent=2)
            self.newly_blacklisted.append({"objectID": mia_id, "reason": reason})
            return True
        except Exception:
            return False

    # ---------- Search / compare ----------

    def fetch_available_artworks(self) -> List[Dict]:
        """Paginate through MIA search API and return list of _source dicts."""
        all_items: List[Dict] = []
        offset = 0
        total = None

        try:
            while len(all_items) < MAX_SEARCH_RESULTS_CAP:
                encoded_query = urllib.parse.quote(SEARCH_QUERY, safe="")
                url = f"{SEARCH_BASE}/{encoded_query}"
                params = {"size": SEARCH_PAGE_SIZE, "from": offset}

                resp = requests.get(url, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()

                hits_block = data.get("hits", {})

                # Elasticsearch 7+ wraps total in {"value": N, "relation": "eq"}
                raw_total = hits_block.get("total", 0)
                if isinstance(raw_total, dict):
                    total = raw_total.get("value", 0)
                else:
                    total = int(raw_total)

                batch = hits_block.get("hits", [])
                if not batch:
                    break

                for hit in batch:
                    source = hit.get("_source")
                    if source and isinstance(source, dict):
                        all_items.append(source)

                offset += len(batch)
                print(f"  Fetched {offset}/{total} ...", end="\r")

                if offset >= total or offset >= MAX_SEARCH_RESULTS_CAP:
                    break

                time.sleep(0.5)

            print(f"  Fetched {len(all_items)} artworks from search API (total available: {total}).")
            return all_items

        except requests.exceptions.RequestException as e:
            print(f"\nSearch API request failed: {e}")
            return []
        except Exception as e:
            print(f"\nUnexpected error during search: {e}")
            return []

    def compare_and_report(self, api_items: List[Dict], existing_ids: Set[str]) -> List[Dict]:
        # Build mia-prefixed ID set from the API response
        api_mia_ids = {f"mia-{item['id']}" for item in api_items if item.get("id") is not None}
        already_have = api_mia_ids & existing_ids
        blacklisted = api_mia_ids & self.blacklist_ids
        new_mia_ids = api_mia_ids - existing_ids - self.blacklist_ids

        # Preserve original order, filtered to new only
        new_items = [
            item for item in api_items
            if f"mia-{item.get('id')}" in new_mia_ids
        ]

        print("\n" + "=" * 70)
        print("COMPARISON RESULTS (MIA)")
        print("=" * 70)
        print(f"Total artworks from API:     {len(api_items)}")
        print(f"MIA IDs in collection:       {len(existing_ids)}")
        print(f"Blacklisted IDs:             {len(self.blacklist_ids)}")
        print(f"Overlap (API ∩ Collection):  {len(already_have)}")
        print(f"Blacklisted (API ∩ Skip):    {len(blacklisted)}")
        print(f"New artworks available:      {len(new_items)}")
        print(f"Will download (max):         {min(MAX_NEW_ARTWORKS, len(new_items))}")

        if new_items:
            sample = new_items[:5]
            print("\nSample of new artworks:")
            for item in sample:
                print(
                    f"  mia-{item.get('id')} | "
                    f"{item.get('title', 'N/A')} — {item.get('artist', 'N/A')}"
                )

        print("=" * 70 + "\n")
        return new_items

    # ---------- Image download ----------

    def build_image_url(self, source: Dict) -> Optional[str]:
        """Construct the CDN image URL from Cache_Location and Primary_RenditionNumber.
        URL pattern: https://img.artsmia.org/web_objects_cache/{cache_path}/{stem}_800.jpg
        Cache_Location uses backslashes (Windows-style) and must be normalised.
        """
        cache_loc = source.get("Cache_Location", "")
        rendition = source.get("Primary_RenditionNumber", "")
        if not cache_loc or not rendition:
            return None
        # Normalise backslashes → forward slashes
        cache_path = cache_loc.replace("\\\\", "/").replace("\\", "/")
        # Strip any existing extension from the rendition number
        stem = rendition.rsplit(".", 1)[0] if "." in rendition else rendition
        return f"{IMAGE_CDN_BASE}/{cache_path}/{stem}_800.jpg"

    def download_image(self, source: Dict, mia_id: str) -> Optional[str]:
        """Download 800px image from img.artsmia.org CDN."""
        image_url = self.build_image_url(source)
        if not image_url:
            print(f"    Cannot build image URL for {mia_id}: missing Cache_Location or Primary_RenditionNumber.")
            return None
        try:
            resp = requests.get(image_url, timeout=30, stream=True)
            resp.raise_for_status()
            filename = f"{mia_id}.jpg"
            with open(IMAGES_OUTPUT_DIR / filename, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return filename
        except requests.exceptions.RequestException as e:
            print(f"    Image download failed for {mia_id}: {e}")
            return None

    # ---------- Metadata ----------

    def format_metadata(self, source: Dict, mia_id: str, local_image_filename: str) -> Dict:
        object_id = source.get("id")
        return {
            "objectID": mia_id,
            "title": source.get("title", "Untitled"),
            "artistDisplayName": source.get("artist", ""),
            "objectDate": source.get("dated", ""),
            "objectName": source.get("object_name", ""),
            "medium": source.get("medium", ""),
            "dimensions": source.get("dimension", ""),
            "department": source.get("department", ""),
            "culture": source.get("culture", ""),
            "period": source.get("style", ""),
            "dynasty": "",
            "creditLine": "Minneapolis Institute of Art. " + (source.get("creditline") or ""),
            "objectURL": f"https://collections.artsmia.org/art/{object_id}",
            "isPublicDomain": source.get("rights_type") == "Public Domain",
            "isOnView": str(source.get("room", "")).upper().startswith("G"),
            "localImage": local_image_filename,
            "tags": [],
        }

    def save_metadata(self, metadata: Dict, mia_id: str) -> bool:
        try:
            with open(METADATA_OUTPUT_DIR / f"{mia_id}.json", "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"    Failed to save metadata for {mia_id}: {e}")
            return False

    def append_to_artworkids(self, mia_id: str) -> bool:
        try:
            existing = []
            if ARTWORKIDS_FILE.exists():
                with open(ARTWORKIDS_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            if mia_id not in existing:
                existing.append(mia_id)
                with open(ARTWORKIDS_FILE, "w", encoding="utf-8") as f:
                    json.dump(existing, f, indent=2)
            return True
        except Exception as e:
            print(f"    Failed to update artworkids.json for {mia_id}: {e}")
            return False

    # ---------- Process single artwork ----------

    def process_artwork(self, source: Dict) -> bool:
        object_id = source.get("id")
        mia_id = f"mia-{object_id}"

        # Skip artworks whose images carry additional restrictions
        # (restricted:1 can appear on PD works due to artist estate requests)
        if source.get("restricted") == 1:
            self.add_to_blacklist(mia_id, "Restricted image (restricted:1)")
            print(f"    Skipped {mia_id}: restricted image.")
            return False

        # Belt-and-suspenders public domain check
        if source.get("rights_type") != "Public Domain":
            self.add_to_blacklist(mia_id, "Not public domain")
            print(f"    Skipped {mia_id}: not public domain.")
            return False

        time.sleep(RATE_LIMIT_DELAY)

        local_image_filename = self.download_image(source, mia_id)
        if not local_image_filename:
            self.failed_downloads.append({"objectID": mia_id, "reason": "Image download failed"})
            return False

        metadata = self.format_metadata(source, mia_id, local_image_filename)

        if not self.save_metadata(metadata, mia_id):
            self.failed_downloads.append({"objectID": mia_id, "reason": "Failed to save metadata"})
            return False

        if not self.append_to_artworkids(mia_id):
            self.failed_downloads.append({"objectID": mia_id, "reason": "Failed to update artworkids.json"})
            return False

        self.successful_downloads.append({
            "objectID": mia_id,
            "title": metadata["title"],
            "artist": metadata["artistDisplayName"],
        })
        self.downloaded_count += 1
        return True

    # ---------- Run ----------

    def run(self):
        start_time = datetime.now()

        print("\n" + "=" * 70)
        print("MINNEAPOLIS INSTITUTE OF ART ARTWORK DOWNLOADER")
        print("=" * 70)
        print(f"Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Max new artworks to download: {MAX_NEW_ARTWORKS}")
        print(f"Filters: Paintings, Public Domain, image:valid, room:G* (on view)")
        print("=" * 70 + "\n")

        self.existing_ids = self.load_existing_ids()
        self.blacklist_ids = self.load_blacklist()

        print(f"MIA IDs already in collection: {len(self.existing_ids)}")
        print(f"Blacklisted IDs:               {len(self.blacklist_ids)}\n")

        print("Fetching artwork list from MIA search API...")
        api_items = self.fetch_available_artworks()
        if not api_items:
            print("No artworks returned from API. Exiting.")
            return

        new_items = self.compare_and_report(api_items, self.existing_ids)
        if not new_items:
            print("No new artworks to download. Collection is up to date.")
            return

        to_download = new_items[:MAX_NEW_ARTWORKS]
        print(f"Starting download of {len(to_download)} artworks...\n")

        for idx, source in enumerate(to_download, 1):
            mia_id = f"mia-{source.get('id')}"
            print(f"[{idx}/{len(to_download)}] {mia_id}: {source.get('title', 'N/A')}")
            self.process_artwork(source)

        self.print_summary(start_time)

    def print_summary(self, start_time: datetime):
        end_time = datetime.now()
        duration = end_time - start_time

        print("\n" + "=" * 70)
        print("DOWNLOAD SUMMARY")
        print("=" * 70)
        print(f"Start time:           {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"End time:             {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Duration:             {duration.total_seconds():.1f} seconds")
        print(f"\nSuccessful downloads: {self.downloaded_count}")
        print(f"Failed downloads:     {len(self.failed_downloads)}")
        print(f"Added to blacklist:   {len(self.newly_blacklisted)}")

        if self.successful_downloads:
            print("\n✓ Successfully downloaded:")
            for item in self.successful_downloads:
                print(f"  - [{item['objectID']}] {item['title']} — {item['artist']}")

        if self.failed_downloads:
            print("\n❌ Failed downloads:")
            for item in self.failed_downloads:
                print(f"  - [{item['objectID']}] {item.get('reason', '')}")

        if self.newly_blacklisted:
            print(f"\n🚫 Added to blacklist ({DONTFETCH_FILE.name}):")
            for item in self.newly_blacklisted:
                print(f"  - [{item['objectID']}] {item.get('reason', '')}")

        print("\nFiles saved to:")
        print(f"  - Metadata: {METADATA_OUTPUT_DIR}/")
        print(f"  - Images:   {IMAGES_OUTPUT_DIR}/")
        print(f"  - IDs:      {ARTWORKIDS_FILE}")
        print(f"  - Blacklist: {DONTFETCH_FILE}")

        print("\n" + "=" * 70)
        if self.downloaded_count > 0:
            print(f"✓ Process completed successfully! Downloaded {self.downloaded_count} new artwork(s).")
        else:
            print("⚠ Process completed with no successful downloads.")
        print("=" * 70 + "\n")


def main():
    downloader = MIADownloader()
    downloader.run()


if __name__ == "__main__":
    main()
