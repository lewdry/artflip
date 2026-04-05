#!/usr/bin/env python3
"""
chicfetch.py

Art Institute of Chicago (AIC / ARTIC) artwork downloader for ArtFlip.
Updates:
 - Added custom User-Agent to bypass 403 CDN blocks.
 - Dynamic IIIF base URL extraction (no longer hardcoded).
 - Optimized API payload by requesting only mapped fields.
 - Cleaned up duplicate methods and logging bugs.
"""

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

MAX_NEW_ARTWORKS = 20
RATE_LIMIT_DELAY = 2.0  # seconds between API calls

# Updated headers
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
    'Referer': 'https://www.artic.edu/'
}

# Search parameters for Elasticsearch filtering
SEARCH_PARAMS = {
    'q': None,
    'isPublicDomain': True,
    'hasImages': True,
    'isOnView': True,
    'classification_filter': {
        "type": "match",          
        "value": ["painting"]     
    },
}

# File paths
ARTWORKIDS_FILE = Path(__file__).parent.parent / "public/artworkids.json"
METADATA_OUTPUT_DIR = Path(__file__).parent.parent / "public/metadata"
IMAGES_OUTPUT_DIR = Path(__file__).parent.parent / "public/images"
LOG_FILE = Path("scripts/chicfetch.log")
DONTFETCH_FILE = Path("scripts/chicdontfetch.json")
TEMP_NEWIDS_FILE = Path(__file__).parent.parent / "public/artworkids.json"

# Pagination/search caps
SEARCH_PAGE_LIMIT = 100     
MAX_SEARCH_PAGES = 10       
MAX_SEARCH_RESULTS_CAP = 5000  

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
# ARTIC API endpoints
# ============================================================================
API_BASE = "https://api.artic.edu/api/v1"
SEARCH_ENDPOINT = f"{API_BASE}/artworks/search"
ARTWORK_ENDPOINT = f"{API_BASE}/artworks"

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
        
        query_filters = []
        
        if SEARCH_PARAMS.get('isPublicDomain') is not None:
            query_filters.append({"term": {"is_public_domain": SEARCH_PARAMS.get('isPublicDomain')}})
        
        if SEARCH_PARAMS.get('hasImages'):
            query_filters.append({"exists": {"field": "image_id"}})
        
        if SEARCH_PARAMS.get('isOnView') is not None:
            query_filters.append({"term": {"is_on_view": SEARCH_PARAMS.get('isOnView')}})

        classification_filter = SEARCH_PARAMS.get('classification_filter')
        if classification_filter:
            query_type = classification_filter.get("type", "match")
            query_value = classification_filter.get("value")
            
            if query_value:
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
                    query_filters.append({query_type: {"classification_titles": query_value}})
        
        if query_filters:
            params['query'] = {"bool": {"must": query_filters}}
        
        return params

    def fetch_available_artworks(self) -> List[int]:
        all_ids: List[int] = []
        page = 1
        pages_fetched = 0

        try:
            while True:
                params = self.build_search_params(page=page)
                logging.info(f"ARTIC search page {page} with payload: {json.dumps(params)}")
                
                # Appended HEADERS here
                resp = requests.post(SEARCH_ENDPOINT, json=params, headers=HEADERS, timeout=30)

                if resp.status_code == 502:
                    logging.error("ARTIC API returned 502 Bad Gateway")
                    print("\n❌ ARTIC API is currently unavailable (502).")
                    break

                resp.raise_for_status()
                payload = resp.json()

                hits = payload.get('data', [])
                ids_this_page = [int(item['id']) for item in hits if 'id' in item]
                all_ids.extend(ids_this_page)

                pages_fetched += 1
                logging.info(f"Fetched page {page}: {len(ids_this_page)} ids (total collected: {len(all_ids)})")

                if len(all_ids) >= MAX_SEARCH_RESULTS_CAP:
                    logging.info(f"Reached MAX_SEARCH_RESULTS_CAP ({MAX_SEARCH_RESULTS_CAP}). Stopping pagination.")
                    break

                pagination = payload.get('pagination', {})
                if pagination:
                    current_page = int(pagination.get('current_page', page))
                    total_pages = int(pagination.get('total_pages', current_page))
                    total_results = int(pagination.get('total', 0))
                    logging.info(f"Pagination: current_page={current_page}, total_pages={total_pages}, total_results={total_results}")
                    if current_page >= total_pages:
                        break
                else:
                    if len(ids_this_page) < SEARCH_PAGE_LIMIT:
                        break

                if pages_fetched >= MAX_SEARCH_PAGES:
                    logging.info(f"Reached MAX_SEARCH_PAGES ({MAX_SEARCH_PAGES}). Stopping pagination.")
                    break

                page += 1
                time.sleep(RATE_LIMIT_DELAY)

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
    def fetch_artwork_metadata(self, object_id: int) -> Dict:
        """Fetch strictly required artwork metadata + config for IIIF domain."""
        try:
            # Removed heavy text fields not utilized in format_metadata. 
            # Added "config" to retrieve the correct dynamic iiif_url.
            fields = [
                "id", "title", "image_id", "is_public_domain", "artist_display", 
                "artist_title", "date_display", "medium_display", "dimensions", 
                "credit_line", "department_title", "place_of_origin", "thumbnail", 
                "artwork_type_title", "alt_titles", "is_on_view", "is_boosted", 
                "gallery_id", "gallery_title", "config"
            ]
            url = f"{ARTWORK_ENDPOINT}/{object_id}"
            
            # Appended HEADERS here
            resp = requests.get(url, params={"fields": ",".join(fields)}, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            payload = resp.json()
            
            # The artwork data is inside 'data', the configuration is inside 'config'
            data = payload.get('data', {})
            config = payload.get('config', {})
            
            # Attach config to the data dict so we have access to it down the line
            data['_config'] = config 

            image_id = data.get('image_id')
            if not image_id:
                logging.warning(f"Object {object_id} has no image_id despite search filter. Blacklisting.")
                self.add_to_blacklist(object_id, "No image_id (search filter mismatch)")
                return {}

            return data

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "HTTPError"
            logging.warning(f"HTTP error fetching {object_id}: {status}")
            if status in [404, 502, 403]:
                self.add_to_blacklist(object_id, f"HTTP {status}")
            return {}
        except Exception as e:
            logging.error(f"Error fetching metadata for {object_id}: {e}")
            return {}

    def construct_image_url(self, image_id: Optional[str], iiif_base_url: str) -> Optional[str]:
        """Construct IIIF URL dynamically using the base URL provided by the API"""
        if not image_id or not iiif_base_url:
            return None
        return f"{iiif_base_url}/{image_id}/full/843,/0/default.jpg"

    def download_image(self, image_url: str, object_id: int) -> Optional[str]:
        if not image_url:
            return None
        try:
            # Appended HEADERS here
            resp = requests.get(image_url, headers=HEADERS, timeout=40, stream=True)
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
        if not artist_display:
            return ''
        name = artist_display.split('\n')[0]
        if '(' in name:
            name = name.split('(')[0]
        return name.strip()

    def format_metadata(self, artwork_data: Dict, local_image_filename: str, iiif_base_url: str) -> Dict:
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
            'iiifImageURL': self.construct_image_url(artwork_data.get('image_id'), iiif_base_url),
            'localImage': local_image_filename,
            'thumbnail': artwork_data.get('thumbnail'),
            'tags': artwork_data.get('alt_titles') or []
        }

    def save_metadata(self, metadata: Dict, object_id: int) -> bool:
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

        # Extract the dynamic IIIF base url directly from the config payload (fallback to legacy domain if missing)
        iiif_base_url = artwork_data.get('_config', {}).get('iiif_url', 'https://www.artic.edu/iiif/2')

        image_url = self.construct_image_url(artwork_data.get('image_id'), iiif_base_url)
        local_image_filename = self.download_image(image_url, object_id)
        if not local_image_filename:
            self.failed_downloads.append({'objectID': object_id, 'reason': 'Failed to download image'})
            return False

        metadata = self.format_metadata(artwork_data, local_image_filename, iiif_base_url)
        
        # Cleanup the temporary _config key before saving the payload
        if '_config' in artwork_data:
            del artwork_data['_config']

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
        
        active_filters = []
        if SEARCH_PARAMS.get('isPublicDomain') is not None:
            active_filters.append(f"Public Domain: {SEARCH_PARAMS['isPublicDomain']}")
        if SEARCH_PARAMS.get('hasImages'):
            active_filters.append("Has Images: True")
        if SEARCH_PARAMS.get('isOnView') is not None:
            active_filters.append(f"On View: {SEARCH_PARAMS['isOnView']}")
        
        # Fixed bug here: referenced the dict safely
        classification = SEARCH_PARAMS.get('classification_filter', {}).get('value')
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
