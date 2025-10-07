#!/usr/bin/env python3
"""
rijksfetch.py

Rijksmuseum artwork downloader (public domain + images only).
Modeled after chicfetch.py / metfetch.py for consistent behavior:
- loads API key from RIJKS_API_KEY (env)
- paginates safely
- downloads image + metadata per artwork
- updates artworkids.json (TEMP behavior)
- manages blacklist (rijksdontfetch.json)
- logs to rijksfetch.log
"""

import os
import requests
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Optional, Set
from datetime import datetime

# ============================================================================
# CONFIGURATION
# ============================================================================

API_KEY = os.getenv("RIJKS_API_KEY")
if not API_KEY:
    raise EnvironmentError("❌ Missing Rijksmuseum API key. Please set RIJKS_API_KEY environment variable.")

MAX_NEW_ARTWORKS = 20
RATE_LIMIT_DELAY = 1.0  # seconds between API calls
SEARCH_PAGE_LIMIT = 100  # items per page (Rijks uses 'ps')
MAX_SEARCH_PAGES = 10
MAX_SEARCH_RESULTS_CAP = 5000

# Filters (only non-None values will be sent)
SEARCH_PARAMS = {
    "imgonly": True,                # only artworks with images
    "rightsType": "Public Domain",  # public domain only
    "toppieces": True, 
    "ondisplay": True,          # only top pieces (True/False)
    "involvedMaker": None,
    "type": None,
    "material": None,
    # You can add other Rijks params here if needed (e.g. 'rp' for Rijks pages)
}

# Paths - match your other scripts' layout
ARTWORKIDS_FILE = Path("../scripts/artworkids.json")
METADATA_OUTPUT_DIR = Path("../scripts/metadata")
IMAGES_OUTPUT_DIR = Path("../scripts/images")
LOG_FILE = Path("rijksfetch.log")
DONTFETCH_FILE = Path("rijksdontfetch.json")
TEMP_NEWIDS_FILE = ARTWORKIDS_FILE  # TEMP behavior matches chicfetch/metfetch

# ============================================================================
# LOGGING
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
        logging.StreamHandler()
    ],
)

# ============================================================================
# API ENDPOINTS & HEADERS
# ============================================================================
BASE_URL = "https://www.rijksmuseum.nl/api/en"
SEARCH_ENDPOINT = f"{BASE_URL}/collection"
DETAIL_ENDPOINT = f"{BASE_URL}/collection/{{object_number}}"

HEADERS = {
    "User-Agent": "ArtFlip/1.0 (hello@artflip.me)"
}

# ============================================================================
# RijksDownloader
# ============================================================================
class RijksDownloader:
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
        try:
            if ARTWORKIDS_FILE.exists():
                with open(ARTWORKIDS_FILE, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    ids = {str(i) for i in data}
                    logging.info(f"Loaded {len(ids)} existing IDs from {ARTWORKIDS_FILE}")
                    return ids
            else:
                logging.info(f"No {ARTWORKIDS_FILE} found. Starting with empty set.")
                return set()
        except Exception as e:
            logging.error(f"Error loading {ARTWORKIDS_FILE}: {e}")
            return set()

    def load_blacklist(self) -> Set[str]:
        try:
            if DONTFETCH_FILE.exists():
                with open(DONTFETCH_FILE, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    bl = {str(i) for i in data}
                    logging.info(f"Loaded {len(bl)} blacklisted IDs from {DONTFETCH_FILE}")
                    return bl
            else:
                logging.info(f"No {DONTFETCH_FILE} found. Starting with empty blacklist.")
                return set()
        except Exception as e:
            logging.error(f"Error loading {DONTFETCH_FILE}: {e}")
            return set()

    def add_to_blacklist(self, object_number: str, reason: str = "") -> bool:
        try:
            if DONTFETCH_FILE.exists():
                with open(DONTFETCH_FILE, "r", encoding="utf-8") as fh:
                    try:
                        current = json.load(fh)
                    except Exception:
                        current = []
            else:
                current = []

            if object_number not in current:
                current.append(object_number)
                current_sorted = sorted(current)
                with open(DONTFETCH_FILE, "w", encoding="utf-8") as fh:
                    json.dump(current_sorted, fh, indent=2)
                self.newly_blacklisted.append({"objectNumber": object_number, "reason": reason})
                logging.info(f"Added {object_number} to blacklist: {reason}")
                return True
            return False
        except Exception as e:
            logging.error(f"Failed to add {object_number} to blacklist: {e}")
            return False

    # ---------- Search ----------
    def fetch_available_artworks(self) -> List[str]:
        """
        Fetch artwork 'objectNumber's from Rijks collection endpoint with the configured filters.
        Only collects artworks that have a webImage present (imgonly).
        """
        all_ids: List[str] = []
        page = 1
        pages_fetched = 0

        try:
            while page <= MAX_SEARCH_PAGES:
                params = {"key": API_KEY, "p": page, "ps": SEARCH_PAGE_LIMIT}
                # add non-None search params
                for k, v in SEARCH_PARAMS.items():
                    if v is not None:
                        # Rijks expects lowercase true/false for booleans in querystring
                        if isinstance(v, bool):
                            params[k] = str(v).lower()
                        else:
                            params[k] = v

                logging.info(f"RIJKS search page {page} -> params: {params}")
                resp = requests.get(SEARCH_ENDPOINT, params=params, headers=HEADERS, timeout=30)

                if resp.status_code == 502:
                    logging.error("Rijks API returned 502 Bad Gateway")
                    print("\n❌ Rijks API is currently unavailable (502).")
                    break

                resp.raise_for_status()

                # parse JSON; handle servers returning HTML (non-JSON)
                try:
                    payload = resp.json()
                except json.JSONDecodeError:
                    logging.error("Non-JSON response from Rijks API (likely server error/HTML)")
                    print("\n❌ Rijks API returned an unexpected response format.")
                    break

                art_objects = payload.get("artObjects", [])
                ids_this_page = [obj.get("objectNumber") for obj in art_objects if obj.get("webImage")]
                all_ids.extend(ids_this_page)

                pages_fetched += 1
                logging.info(f"Fetched page {page}: {len(ids_this_page)} ids (total collected: {len(all_ids)})")

                # Stop conditions
                if len(all_ids) >= MAX_SEARCH_RESULTS_CAP:
                    logging.info(f"Reached MAX_SEARCH_RESULTS_CAP ({MAX_SEARCH_RESULTS_CAP}). Stopping pagination.")
                    break

                # If fewer returned than page size, last page
                if len(art_objects) < SEARCH_PAGE_LIMIT:
                    break

                page += 1
                time.sleep(RATE_LIMIT_DELAY)

            # deduplicate while preserving order
            unique_ids = list(dict.fromkeys(all_ids))
            logging.info(f"RIJKS search completed: collected {len(unique_ids)} unique IDs across {pages_fetched} pages")
            return unique_ids

        except requests.exceptions.RequestException as e:
            logging.error(f"Network error during Rijks search: {e}")
            print(f"\n❌ Network error: {e}")
            return []
        except Exception as e:
            logging.error(f"Error parsing Rijks search response: {e}")
            return []

    # ---------- Metadata + image fetch ----------
    def fetch_metadata(self, object_number: str) -> Optional[Dict]:
        try:
            url = DETAIL_ENDPOINT.format(object_number=object_number)
            params = {"key": API_KEY}
            resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
            resp.raise_for_status()

            try:
                payload = resp.json()
            except json.JSONDecodeError:
                logging.error(f"Non-JSON response for {object_number}")
                return None

            data = payload.get("artObject", {})

            # Ensure image present (extra check)
            if not data.get("webImage"):
                logging.warning(f"{object_number} has no webImage despite search filter. Blacklisting.")
                self.add_to_blacklist(object_number, "No webImage (search mismatch)")
                return None

            # Ensure public domain (defensive)
            if data.get("rightsType") != "Public Domain":
                logging.warning(f"{object_number} is not public domain. Blacklisting.")
                self.add_to_blacklist(object_number, "Not Public Domain")
                return None

            return data
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "HTTPError"
            logging.warning(f"HTTP error fetching {object_number}: {status}")
            if status in [404, 502]:
                self.add_to_blacklist(object_number, f"HTTP {status}")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Network error fetching metadata for {object_number}: {e}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error fetching metadata for {object_number}: {e}")
            return None

    def download_image(self, image_url: str, object_number: str) -> Optional[str]:
        if not image_url:
            return None
        try:
            resp = requests.get(image_url, timeout=40, stream=True, headers=HEADERS)
            resp.raise_for_status()
            # default extension jpg unless content-type says png
            content_type = resp.headers.get("content-type", "")
            ext = ".png" if "png" in content_type else ".jpg"
            filename = f"{object_number}{ext}"
            filepath = IMAGES_OUTPUT_DIR / filename
            with open(filepath, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
            logging.info(f"Downloaded image for {object_number} -> {filename}")
            return filename
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to download image for {object_number}: {e}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error saving image for {object_number}: {e}")
            return None

    def format_metadata(self, data: Dict, local_image_filename: str) -> Dict:
        # Map Rijks fields into your metadata structure similar to others
        return {
            "objectNumber": data.get("objectNumber"),
            "title": data.get("title"),
            "artistDisplayName": data.get("principalOrFirstMaker"),
            "objectDate": data.get("dating", {}).get("presentingDate", ""),
            "objectName": data.get("objectType", ""),
            "medium": ", ".join(data.get("materials", [])) if data.get("materials") else "",
            "dimensions": data.get("subTitle", ""),
            "creditLine": "Rijksmuseum. " + (data.get("creditLine") or ""),
            "department": "",
            "culture": "",
            "objectURL": data.get("links", {}).get("web"),
            "isPublicDomain": data.get("rightsType") == "Public Domain",
            "localImage": local_image_filename,
            "webImage": data.get("webImage", {}).get("url"),
            "facets": data.get("facets", {}),
        }

    def save_metadata(self, metadata: Dict, object_number: str) -> bool:
        try:
            filepath = METADATA_OUTPUT_DIR / f"{object_number}.json"
            with open(filepath, "w", encoding="utf-8") as fh:
                json.dump(metadata, fh, indent=2, ensure_ascii=False)
            logging.info(f"Saved metadata for {object_number}")
            return True
        except Exception as e:
            logging.error(f"Failed to save metadata for {object_number}: {e}")
            return False

    def append_to_artworkids(self, object_number: str) -> bool:
        try:
            if TEMP_NEWIDS_FILE.exists():
                with open(TEMP_NEWIDS_FILE, "r", encoding="utf-8") as fh:
                    try:
                        ids = json.load(fh)
                    except Exception:
                        ids = []
            else:
                ids = []

            if object_number not in ids:
                ids.append(str(object_number))
                with open(TEMP_NEWIDS_FILE, "w", encoding="utf-8") as fh:
                    json.dump(ids, fh, indent=2)
                logging.info(f"Appended {object_number} to {TEMP_NEWIDS_FILE}")
            return True
        except Exception as e:
            logging.error(f"Failed to append to {TEMP_NEWIDS_FILE}: {e}")
            return False

    # ---------- Process single artwork ----------
    def process_artwork(self, object_number: str) -> bool:
        logging.info(f"Processing Rijks artwork {object_number}...")
        data = self.fetch_metadata(object_number)
        if not data:
            self.failed_downloads.append({"objectNumber": object_number, "reason": "Failed metadata or blacklisted"})
            return False

        time.sleep(RATE_LIMIT_DELAY)
        image_url = data.get("webImage", {}).get("url")
        local_image_filename = self.download_image(image_url, object_number)
        if not local_image_filename:
            self.failed_downloads.append({"objectNumber": object_number, "reason": "Failed image download"})
            return False

        metadata = self.format_metadata(data, local_image_filename)
        if not self.save_metadata(metadata, object_number):
            self.failed_downloads.append({"objectNumber": object_number, "reason": "Failed to save metadata"})
            return False

        if not self.append_to_artworkids(object_number):
            self.failed_downloads.append({"objectNumber": object_number, "reason": "Failed to update artworkids.json"})
            return False

        self.successful_downloads.append({
            "objectNumber": object_number,
            "title": metadata.get("title"),
            "artist": metadata.get("artistDisplayName")
        })
        self.downloaded_count += 1
        logging.info(f"✓ Successfully processed artwork {object_number}")
        return True

    # ---------- Run ----------
    def run(self):
        start_time = datetime.now()

        print("\n" + "="*70)
        print("RIJKSMUSEUM PUBLIC DOMAIN FETCHER")
        print("="*70)
        print(f"Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Max new artworks to download: {MAX_NEW_ARTWORKS}")
        print("Active filters: Public Domain + Images only")
        print("="*70 + "\n")

        logging.info("Starting Rijks download process")
        logging.info(f"Configuration: MAX_NEW_ARTWORKS={MAX_NEW_ARTWORKS}")

        self.existing_ids = self.load_existing_ids()
        self.blacklist_ids = self.load_blacklist()

        api_ids = self.fetch_available_artworks()
        if not api_ids:
            print("❌ No artworks returned from Rijks search. Exiting.")
            logging.error("No artworks returned from Rijks API")
            return

        # determine new ids (strings)
        api_ids_set = {str(i) for i in api_ids}
        new_ids = sorted([i for i in api_ids_set - self.existing_ids - self.blacklist_ids])

        print("\n" + "="*70)
        print("COMPARISON RESULTS (RIJKS)")
        print("="*70)
        print(f"Total artworks from API:     {len(api_ids)}")
        print(f"IDs in collection:           {len(self.existing_ids)}")
        print(f"Blacklisted IDs:             {len(self.blacklist_ids)}")
        print(f"New artworks available:      {len(new_ids)}")
        print(f"Will download (max):         {min(MAX_NEW_ARTWORKS, len(new_ids))}")
        if new_ids:
            sample = new_ids[:50]
            print(f"\nNew artwork IDs (first {len(sample)}): {sample}")
            if len(new_ids) > len(sample):
                print(f"... and {len(new_ids) - len(sample)} more")
        print("="*70 + "\n")

        if not new_ids:
            print("✓ No new artworks to download. Collection is up to date!")
            logging.info("No new artworks to download")
            return

        to_download = new_ids[:MAX_NEW_ARTWORKS]
        print(f"\nStarting download of {len(to_download)} artworks...\n")
        for idx, object_number in enumerate(to_download, 1):
            print(f"[{idx}/{len(to_download)}] Processing artwork {object_number}...")
            self.process_artwork(object_number)
            time.sleep(RATE_LIMIT_DELAY)

        self.print_summary(start_time)

    def print_summary(self, start_time: datetime):
        end_time = datetime.now()
        duration = end_time - start_time

        print("\n" + "="*70)
        print("DOWNLOAD SUMMARY")
        print("="*70)
        print(f"Start time:           {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"End time:             {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Duration:             {duration.total_seconds():.1f} seconds")
        print(f"\nSuccessful downloads: {self.downloaded_count}")
        print(f"Failed downloads:     {len(self.failed_downloads)}")
        print(f"Added to blacklist:   {len(self.newly_blacklisted)}")

        if self.successful_downloads:
            print("\n✓ Successfully downloaded:")
            for item in self.successful_downloads:
                artist = item.get("artist") or "Unknown Artist"
                print(f"  - {item['objectNumber']}: {item.get('title')} by {artist}")

        if self.failed_downloads:
            print("\n❌ Failed downloads:")
            for item in self.failed_downloads:
                print(f"  - {item.get('objectNumber')}: {item.get('reason')}")

        if self.newly_blacklisted:
            print(f"\n🚫 Added to blacklist ({DONTFETCH_FILE.name}):")
            for item in self.newly_blacklisted:
                print(f"  - {item['objectNumber']}: {item['reason']}")

        print("\nFiles saved to:")
        print(f"  - Metadata: {METADATA_OUTPUT_DIR}/")
        print(f"  - Images:   {IMAGES_OUTPUT_DIR}/")
        print(f"  - Log file: {LOG_FILE}")
        print(f"  - New IDs:  {TEMP_NEWIDS_FILE} (TEMP)")
        print(f"  - Blacklist: {DONTFETCH_FILE}")

        print("\n" + "="*70)
        if self.downloaded_count > 0:
            print(f"✓ Process completed successfully! Downloaded {self.downloaded_count} new artwork(s).")
        else:
            print("⚠ Process completed with no successful downloads.")
        print("="*70 + "\n")

        logging.info(f"Download session complete: {self.downloaded_count} successful, {len(self.failed_downloads)} failed, {len(self.newly_blacklisted)} blacklisted")

# -----------------------------------------------------------------------------
def main():
    downloader = RijksDownloader()
    downloader.run()

if __name__ == "__main__":
    main()
