#!/usr/bin/env python3
"""
chicfetch.py

Art Institute of Chicago (AIC / ARTIC) artwork downloader.
Updates from previous version:
 - Blacklist filename changed to "chicdontfetch.json"
 - Pagination support added to ARTIC search endpoint (fetches pages until exhausted or safe cap reached)
 - Keeps previous behavior: metadata + image saving, blacklist, artworkids update (TEMP), logging, rate limiting
 - Artist name cleaning: removes biographical info in parentheses and after newlines
 - Elasticsearch filtering: filters at API search level for much faster results
"""

import requests
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Optional, Set
from datetime import datetime

# ============================================================================
# CONFIGURATION - Modify these settings as needed
# ============================================================================

MAX_NEW_ARTWORKS = 100
RATE_LIMIT_DELAY = 1.0  # seconds between API calls

# Search parameters: use SEARCH_PARAMS['q'] as the main search term.
# NOTE: These filters are now applied at the API search level using Elasticsearch!
SEARCH_PARAMS = {
    'q': None,
    'isPublicDomain': True,
    'hasImages': True,
    'isOnView': True,
    'artistOrCulture': None,
    'medium': None,
    'dateBegin': None,
    'dateEnd': None,
    'objectName': None,
    'department': None,

    'classification_filter': {
        "type": "match",          # Options: "match", "match_phrase", "wildcard"
        "value": ["photograph"]  # ✨ Use a list for multiple values
    },
}

# File paths (kept same relative layout)
ARTWORKIDS_FILE = Path("../public/artworkids.json")
METADATA_OUTPUT_DIR = Path("../public/metadata")
IMAGES_OUTPUT_DIR = Path("../public/images")
LOG_FILE = Path("chicfetch.log")
DONTFETCH_FILE = Path("chicdontfetch.json")
TEMP_NEWIDS_FILE = Path("../public/artworkids.json")

# Pagination/search caps
SEARCH_PAGE_LIMIT = 100     # items per page requested from API (ARTIC may cap this)
MAX_SEARCH_PAGES = 10       # don't fetch more than this many pages (safety)
MAX_SEARCH_RESULTS_CAP = 5000  # absolute cap on total IDs fetched to avoid runaway queries

# ============================================================================
# SETUP logging
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# ============================================================================
# ARTIC API endpoints + IIIF template
# ============================================================================
API_BASE = "https://api.artic.edu/api/v1"
SEARCH_ENDPOINT = f"{API_BASE}/artworks/search"
ARTWORK_ENDPOINT = f"{API_BASE}/artworks"
IIIF_IMAGE_TEMPLATE = "https://www.artic.edu/iiif/2/{image_id}/full/843,/0/default.jpg"

# ============================================================================
# Downloader class
# ============================================================================
class ChicDownloader:
    def __init__(self):
        self.existing_ids: Set[str] = set()
        self.blacklist_ids: Set[str] = set()
        self.downloaded_count = 0
        self.failed_downloads = []
        self.successful_downloads = []
        self.newly_blacklisted = []

        METADATA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        IMAGES_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---------- File loaders ----------
    def load_existing_ids(self) -> Set[str]:
        """Load existing artwork IDs (strings) from artworkids.json"""
        try:
            if ARTWORKIDS_FILE.exists():
                with open(ARTWORKIDS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
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
        """Load blacklisted IDs from chicdontfetch.json (JSON array expected)"""
        try:
            if DONTFETCH_FILE.exists():
                with open(DONTFETCH_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    bl = {str(i) for i in data}
                    logging.info(f"Loaded {len(bl)} blacklisted IDs from {DONTFETCH_FILE}")
                    return bl
            else:
                logging.info(f"No {DONTFETCH_FILE} found. Starting with empty blacklist.")
                return set()
        except Exception as e:
            logging.error(f"Error loading {DONTFETCH_FILE}: {e}")
            return set()

    def add_to_blacklist(self, object_id: int, reason: str = ""):
        """Add an ID to the blacklist file (keeps JSON array)"""
        try:
            if DONTFETCH_FILE.exists():
                with open(DONTFETCH_FILE, 'r', encoding='utf-8') as f:
                    try:
                        current = json.load(f)
                    except Exception:
                        current = []
            else:
                current = []

            id_str = str(object_id)
            if id_str not in current:
                current.append(id_str)
                # try to keep numeric-sorted order if possible
                try:
                    current_sorted = sorted(current, key=lambda x: int(x))
                except Exception:
                    current_sorted = sorted(current)
                with open(DONTFETCH_FILE, 'w', encoding='utf-8') as f:
                    json.dump(current_sorted, f, indent=2)
                self.newly_blacklisted.append({'objectID': object_id, 'reason': reason})
                logging.info(f"Added {object_id} to blacklist: {reason}")
                return True
            return False
        except Exception as e:
            logging.error(f"Failed to add {object_id} to blacklist: {e}")
            return False

    # ---------- Search / compare ----------
    def build_search_params(self, page: int = 1) -> Dict:
        """Construct parameters for the ARTIC search endpoint with Elasticsearch filtering"""
        params = {
            "limit": SEARCH_PAGE_LIMIT,
            "page": page,
            "fields": "id"
        }
        
        # Add text search query if provided
    def build_search_params(self, page: int = 1) -> Dict:
        """Construct parameters for the ARTIC search endpoint with Elasticsearch filtering"""
        params = {
            "limit": SEARCH_PAGE_LIMIT,
            "page": page,
            "fields": "id"
        }
        
        # ... (the 'q' and other filters remain the same) ...
        query_filters = []
        
        if SEARCH_PARAMS.get('isPublicDomain') is not None:
            query_filters.append({"term": {"is_public_domain": SEARCH_PARAMS.get('isPublicDomain')}})
        
        if SEARCH_PARAMS.get('hasImages'):
            query_filters.append({"exists": {"field": "image_id"}})
        
        if SEARCH_PARAMS.get('isOnView') is not None:
            query_filters.append({"term": {"is_on_view": SEARCH_PARAMS.get('isOnView')}})

        # ✨ UPDATED LOGIC TO HANDLE A LIST OF CLASSIFICATIONS ✨
        classification_filter = SEARCH_PARAMS.get('classification_filter')
        if classification_filter:
            query_type = classification_filter.get("type", "match")
            query_value = classification_filter.get("value")
            
            if query_value:
                # Check if the value is a list (for an OR search)
                if isinstance(query_value, list):
                    should_queries = []
                    for item in query_value:
                        should_queries.append({query_type: {"classification_titles": item}})
                    
                    query_filters.append({
                        "bool": {
                            "should": should_queries,
                            "minimum_should_match": 1
                        }
                    })
                else:
                    # If it's just a string, handle it the old way
                    query_filters.append({query_type: {"classification_titles": query_value}})
        
        # Add the query filters if any exist
        if query_filters:
            params['query'] = {"bool": {"must": query_filters}}
        
        return params

    def fetch_available_artworks(self) -> List[int]:
        """
        Call ARTIC /artworks/search with Elasticsearch filtering and pagination.
        Returns list of artwork IDs that match the filters.
        """
        all_ids: List[int] = []
        page = 1
        pages_fetched = 0

        try:
            while True:
                params = self.build_search_params(page=page)
                # Log the params payload to help with debugging
                logging.info(f"ARTIC search page {page} with payload: {json.dumps(params)}")
                
                # Use POST for complex Elasticsearch queries
                resp = requests.post(SEARCH_ENDPOINT, json=params, timeout=30)

                if resp.status_code == 502:
                    logging.error("ARTIC API returned 502 Bad Gateway")
                    print("\n❌ ARTIC API is currently unavailable (502).")
                    break

                resp.raise_for_status()
                payload = resp.json()

                hits = payload.get('data', [])
                # Extract ids from hits
                ids_this_page = [int(item['id']) for item in hits if 'id' in item]
                all_ids.extend(ids_this_page)

                pages_fetched += 1

                # Log progress
                logging.info(f"Fetched page {page}: {len(ids_this_page)} ids (total collected: {len(all_ids)})")

                # Safety: stop if we've reached absolute cap
                if len(all_ids) >= MAX_SEARCH_RESULTS_CAP:
                    logging.info(f"Reached MAX_SEARCH_RESULTS_CAP ({MAX_SEARCH_RESULTS_CAP}). Stopping pagination.")
                    break

                # If pagination info present, use it to know when to stop
                pagination = payload.get('pagination', {})
                if pagination:
                    current_page = int(pagination.get('current_page', page))
                    total_pages = int(pagination.get('total_pages', current_page))
                    total_results = int(pagination.get('total', 0))
                    logging.info(f"Pagination: current_page={current_page}, total_pages={total_pages}, total_results={total_results}")
                    if current_page >= total_pages:
                        break
                else:
                    # If no pagination info, stop when results fewer than requested limit (last page)
                    if len(ids_this_page) < SEARCH_PAGE_LIMIT:
                        break

                # Safety cap on pages fetched
                if pages_fetched >= MAX_SEARCH_PAGES:
                    logging.info(f"Reached MAX_SEARCH_PAGES ({MAX_SEARCH_PAGES}). Stopping pagination.")
                    break

                # Early exit optimization: if we've already found enough potential new IDs to satisfy download need,
                # we can stop paging to save API calls (we look for at least MAX_NEW_ARTWORKS * 3 to have buffer)
              #  if len(all_ids) >= MAX_NEW_ARTWORKS * 3:
                #    logging.info("Collected sufficient IDs for potential downloads; stopping early.")
               #     break

                page += 1
                time.sleep(RATE_LIMIT_DELAY)  # polite pause between pages

            # Deduplicate and return
            unique_ids = list(dict.fromkeys(all_ids))
            logging.info(f"ARTIC search completed: collected {len(unique_ids)} unique IDs across {pages_fetched} pages")
            return unique_ids

        except requests.exceptions.RequestException as e:
            logging.error(f"Network error during ARTIC search: {e}")
            print(f"\n❌ Network error: {e}")
            return []
        except Exception as e:
            logging.error(f"Error parsing ARTIC search response: {e}")
            return []

    def compare_and_report(self, api_ids: List[int], existing_ids: Set[str]) -> List[int]:
        api_ids_str = {str(i) for i in api_ids}
        already_have = api_ids_str & existing_ids
        blacklisted = api_ids_str & self.blacklist_ids
        new_ids_str = api_ids_str - existing_ids - self.blacklist_ids
        new_ids = sorted([int(i) for i in new_ids_str])

        print("\n" + "="*70)
        print("COMPARISON RESULTS (ARTIC)")
        print("="*70)
        print(f"Total artworks from API:     {len(api_ids)}")
        print(f"IDs in collection:           {len(existing_ids)}")
        print(f"Blacklisted IDs:             {len(self.blacklist_ids)}")
        print(f"Overlap (API ∩ Collection):  {len(already_have)}")
        print(f"Blacklisted (API ∩ Skip):    {len(blacklisted)}")
        print(f"New artworks available:      {len(new_ids)}")
        print(f"Will download (max):         {min(MAX_NEW_ARTWORKS, len(new_ids))}")

        if new_ids:
            new_ids_list = new_ids[:50]
            print(f"\nNew artwork IDs (first {min(50, len(new_ids))}):")
            print(new_ids_list)
            if len(new_ids) > 50:
                print(f"... and {len(new_ids) - 50} more")

        print("="*70 + "\n")

        logging.info(f"Found {len(new_ids)} new artworks (ARTIC)")
        return new_ids

    # ---------- Metadata + image fetch ----------
    def fetch_artwork_metadata(self, object_id: int) -> Optional[Dict]:
        """Fetch detailed artwork metadata from ARTIC. Validation already done by search filters."""
        try:
            fields = [
                "id","title","image_id","is_public_domain","artist_display","artist_title",
                "date_display","medium_display","dimensions","credit_line","department_title",
                "place_of_origin","thumbnail","api_link","artwork_type_title","classification_title",
                "inscriptions","provenance_text","alt_titles","is_on_view","is_boosted","gallery_id","gallery_title"
            ]
            url = f"{ARTWORK_ENDPOINT}/{object_id}"
            resp = requests.get(url, params={"fields": ",".join(fields)}, timeout=20)
            resp.raise_for_status()
            payload = resp.json()
            data = payload.get('data', {})

            # Basic validation (most filtering already done by Elasticsearch)
            # Only check for critical issues that would prevent download
            image_id = data.get('image_id')
            if not image_id:
                logging.warning(f"Object {object_id} has no image_id despite search filter. Blacklisting.")
                self.add_to_blacklist(object_id, "No image_id (search filter mismatch)")
                return None

            return data

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "HTTPError"
            logging.warning(f"HTTP error fetching {object_id}: {status}")
            if status in [404, 502]:
                self.add_to_blacklist(object_id, f"HTTP {status}")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Network error fetching metadata for {object_id}: {e}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error fetching metadata for {object_id}: {e}")
            return None

    def construct_image_url(self, image_id: Optional[str]) -> Optional[str]:
        """Construct IIIF URL for a given image_id"""
        if not image_id:
            return None
        return IIIF_IMAGE_TEMPLATE.format(image_id=image_id)

    def download_image(self, image_url: str, object_id: int) -> Optional[str]:
        """Download image via IIIF URL to images folder"""
        if not image_url:
            return None
        try:
            resp = requests.get(image_url, timeout=40, stream=True)
            resp.raise_for_status()
            ext = '.jpg'
            filename = f"{object_id}{ext}"
            filepath = IMAGES_OUTPUT_DIR / filename
            with open(filepath, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    f.write(chunk)
            logging.info(f"Downloaded image for {object_id} -> {filename}")
            return filename
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to download image for {object_id}: {e}")
            return None

    def clean_artist_name(self, artist_display: str) -> str:
        """Extract just the artist name, removing biographical info in parentheses or after newlines"""
        if not artist_display:
            return ''
        
        # Split on newline and take first part
        name = artist_display.split('\n')[0]
        
        # Remove content in parentheses (nationality, dates, etc.)
        if '(' in name:
            name = name.split('(')[0]
        
        # Clean up any trailing whitespace
        return name.strip()

    def format_metadata(self, artwork_data: Dict, local_image_filename: str) -> Dict:
        """Map ARTIC fields to your metadata structure (keeps familiar keys)"""
        raw_artist = artwork_data.get('artist_display', artwork_data.get('artist_title', ''))
        
        return {
            'objectID': artwork_data.get('id'),
            'title': artwork_data.get('title', 'Untitled'),
            'artistDisplayName': self.clean_artist_name(raw_artist),
            'objectDate': artwork_data.get('date_display', ''),
            'objectName': artwork_data.get('artwork_type_title', ''),
            'medium': artwork_data.get('medium_display', ''),
            'dimensions': artwork_data.get('dimensions', ''),
            'department': artwork_data.get('department_title', ''),
            'culture': artwork_data.get('place_of_origin', ''),
            'period': '',
            'dynasty': '',
            'creditLine': 'Art Institute of Chicago. ' + (artwork_data.get('credit_line') or ''),
            'objectURL':  f"https://www.artic.edu/artworks/{artwork_data.get('id')}",
            'isPublicDomain': artwork_data.get('is_public_domain', False),
            'isOnView': artwork_data.get('is_on_view', False),
            'isBoosted': artwork_data.get('is_boosted', False),
            'galleryId': artwork_data.get('gallery_id'),
            'galleryTitle': artwork_data.get('gallery_title'),
            'image_id': artwork_data.get('image_id', ''),
            'iiifImageURL': self.construct_image_url(artwork_data.get('image_id')),
            'localImage': local_image_filename,
            'thumbnail': artwork_data.get('thumbnail'),
            'tags': artwork_data.get('alt_titles') or []
        }

    def save_metadata(self, metadata: Dict, object_id: int) -> bool:
        """Save metadata JSON for the artwork"""
        try:
            filepath = METADATA_OUTPUT_DIR / f"{object_id}.json"
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            logging.info(f"Saved metadata for {object_id}")
            return True
        except Exception as e:
            logging.error(f"Failed to save metadata for {object_id}: {e}")
            return False

    def append_to_artworkids(self, object_id: int) -> bool:
        """Append new object ID to artworkids.json (temp behavior same as original)"""
        try:
            if TEMP_NEWIDS_FILE.exists():
                with open(TEMP_NEWIDS_FILE, 'r', encoding='utf-8') as f:
                    try:
                        ids = json.load(f)
                    except Exception:
                        ids = []
            else:
                ids = []

            ids.append(str(object_id))
            with open(TEMP_NEWIDS_FILE, 'w', encoding='utf-8') as f:
                json.dump(ids, f, indent=2)
            logging.info(f"Appended {object_id} to {TEMP_NEWIDS_FILE}")
            return True
        except Exception as e:
            logging.error(f"Failed to append to {TEMP_NEWIDS_FILE}: {e}")
            return False

    # ---------- Process single artwork ----------
    def process_artwork(self, object_id: int) -> bool:
        logging.info(f"Processing ARTIC artwork {object_id}...")
        artwork_data = self.fetch_artwork_metadata(object_id)
        if not artwork_data:
            self.failed_downloads.append({'objectID': object_id, 'reason': 'Failed to fetch metadata or blacklisted'})
            return False

        time.sleep(RATE_LIMIT_DELAY)

        image_url = self.construct_image_url(artwork_data.get('image_id'))
        local_image_filename = self.download_image(image_url, object_id)
        if not local_image_filename:
            self.failed_downloads.append({'objectID': object_id, 'reason': 'Failed to download image'})
            return False

        metadata = self.format_metadata(artwork_data, local_image_filename)
        if not self.save_metadata(metadata, object_id):
            self.failed_downloads.append({'objectID': object_id, 'reason': 'Failed to save metadata'})
            return False

        if not self.append_to_artworkids(object_id):
            self.failed_downloads.append({'objectID': object_id, 'reason': 'Failed to update artworkids.json'})
            return False

        self.successful_downloads.append({
            'objectID': object_id,
            'title': metadata['title'],
            'artist': metadata['artistDisplayName']
        })
        self.downloaded_count += 1
        logging.info(f"✓ Successfully processed artwork {object_id}")
        return True

    # ---------- Run ----------
    def run(self):
        start_time = datetime.now()

        print("\n" + "="*70)
        print("ART INSTITUTE OF CHICAGO ARTWORK DOWNLOADER")
        print("="*70)
        print(f"Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Max new artworks to download: {MAX_NEW_ARTWORKS}")
        
        # Print active filters
        active_filters = []
        if SEARCH_PARAMS.get('isPublicDomain') is not None:
            active_filters.append(f"Public Domain: {SEARCH_PARAMS['isPublicDomain']}")
        if SEARCH_PARAMS.get('hasImages'):
            active_filters.append("Has Images: True")
        if SEARCH_PARAMS.get('isOnView') is not None:
            active_filters.append(f"On View: {SEARCH_PARAMS['isOnView']}")
        
        # ✨ ADDED: Log the classification filter
        classification = SEARCH_PARAMS.get('classification_titles')
        if classification:
            active_filters.append(f"Classification: {classification}")
        
        if active_filters:
            print(f"Active filters (Elasticsearch): {', '.join(active_filters)}")
        
        print("="*70 + "\n")

        logging.info("Starting ARTIC download process")
        logging.info(f"Configuration: MAX_NEW_ARTWORKS={MAX_NEW_ARTWORKS}")
        if active_filters:
            logging.info(f"Active Elasticsearch filters: {', '.join(active_filters)}")

        self.existing_ids = self.load_existing_ids()
        self.blacklist_ids = self.load_blacklist()

        api_ids = self.fetch_available_artworks()
        if not api_ids:
            print("❌ No artworks returned by ARTIC search. Exiting.")
            logging.error("No artworks returned from ARTIC")
            return

        new_ids = self.compare_and_report(api_ids, self.existing_ids)
        if not new_ids:
            print("✓ No new artworks to download. Collection is up to date!")
            logging.info("No new artworks to download")
            return

        to_download = new_ids[:MAX_NEW_ARTWORKS]
        print(f"\nStarting download of {len(to_download)} artworks...\n")

        for idx, object_id in enumerate(to_download, 1):
            print(f"[{idx}/{len(to_download)}] Processing artwork {object_id}...")
            self.process_artwork(object_id)
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
                artist = item['artist'] if item['artist'] else 'Unknown Artist'
                print(f"  - {item['objectID']}: {item['title']} by {artist}")

        if self.failed_downloads:
            print("\n❌ Failed downloads:")
            for item in self.failed_downloads:
                print(f"  - {item['objectID']}: {item['reason']}")

        if self.newly_blacklisted:
            print(f"\n🚫 Added to blacklist ({DONTFETCH_FILE.name}):")
            for item in self.newly_blacklisted:
                print(f"  - {item['objectID']}: {item['reason']}")

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

def main():
    downloader = ChicDownloader()
    downloader.run()

if __name__ == "__main__":
    main()