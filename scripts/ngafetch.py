#!/usr/bin/env python3
"""
ngafetch.py

National Gallery of Art (NGA) artwork downloader (public domain + images only).
Works with NGA's open data CSV files on GitHub.
Modeled after chicfetch.py / metfetch.py / rijksfetch.py for consistent behavior:
- Downloads and processes objects.csv and published_images.csv from GitHub
- Filters for paintings and drawings with public domain status
- Downloads images via IIIF endpoints
- Updates artworkids.json (TEMP behavior)
- Manages blacklist (ngadontfetch.json)
- Logs to ngafetch.log
"""

import requests
import json
import time
import logging
import csv
import zipfile
import io
from pathlib import Path
from typing import List, Dict, Optional, Set
from datetime import datetime

# ============================================================================
# CONFIGURATION
# ============================================================================

MAX_NEW_ARTWORKS = 1500
RATE_LIMIT_DELAY = 1.0  # seconds between API calls

# Filters for artwork selection
SEARCH_PARAMS = {
    "classifications": ["painting"],  # List of classifications to include
    "publicDomain": True,  # Only public domain works
    "onView": True,  # Only artworks currently on view (have locationid)
    "downloadable": True,  # Only images available for download (viewtype = 'primary')
}

# GitHub URLs for NGA open data
GITHUB_BASE = "https://github.com/NationalGalleryOfArt/opendata"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/NationalGalleryOfArt/opendata/main/data"
OBJECTS_CSV_URL = f"{GITHUB_RAW_BASE}/objects.csv"
PUBLISHED_IMAGES_CSV_URL = f"{GITHUB_RAW_BASE}/published_images.csv"

# IIIF Image endpoint template
IIIF_IMAGE_TEMPLATE = "https://api.nga.gov/iiif/{uuid}/full/!843,843/0/default.jpg"

# Paths - match your other scripts' layout
ARTWORKIDS_FILE = Path("../public/artworkids.json")
METADATA_OUTPUT_DIR = Path("../scripts/metadata")
IMAGES_OUTPUT_DIR = Path("../scripts/images")
LOG_FILE = Path("ngafetch.log")
DONTFETCH_FILE = Path("ngadontfetch.json")
TEMP_NEWIDS_FILE = Path("../scripts/artworkids.json")  # TEMP behavior matches other scripts
TEMP_DATA_DIR = Path("temp_nga_data")

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
# NGADownloader
# ============================================================================
class NGADownloader:
    def __init__(self):
        self.existing_ids: Set[str] = set()
        self.blacklist_ids: Set[str] = set()
        self.downloaded_count = 0
        self.failed_downloads: List[Dict] = []
        self.successful_downloads: List[Dict] = []
        self.newly_blacklisted: List[Dict] = []
        
        # Data storage
        self.objects_data: Dict[str, Dict] = {}  # objectid -> object data
        self.image_mappings: Dict[str, str] = {}  # objectid -> image uuid
        # Cache of verified public-domain object IDs (reduces scraping)
        self.public_domain_ids: Set[str] = self.load_public_domain_cache()

        METADATA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        IMAGES_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        TEMP_DATA_DIR.mkdir(parents=True, exist_ok=True)

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

    def add_to_blacklist(self, object_id: str, reason: str = "") -> bool:
        try:
            if DONTFETCH_FILE.exists():
                with open(DONTFETCH_FILE, "r", encoding="utf-8") as fh:
                    try:
                        current = json.load(fh)
                    except Exception:
                        current = []
            else:
                current = []

            if object_id not in current:
                current.append(object_id)
                current_sorted = sorted(current, key=lambda x: int(x) if x.isdigit() else x)
                with open(DONTFETCH_FILE, "w", encoding="utf-8") as fh:
                    json.dump(current_sorted, fh, indent=2)
                self.newly_blacklisted.append({"objectID": object_id, "reason": reason})
                logging.info(f"Added {object_id} to blacklist: {reason}")
                return True
            return False
        except Exception as e:
            logging.error(f"Failed to add {object_id} to blacklist: {e}")
            return False

    # ---------- CSV Download and Processing ----------
    def download_csv(self, url: str, filename: str) -> Optional[Path]:
        """Download CSV file from GitHub"""
        try:
            logging.info(f"Downloading {filename} from GitHub...")
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            
            filepath = TEMP_DATA_DIR / filename
            with open(filepath, 'wb') as f:
                f.write(resp.content)
            
            logging.info(f"Downloaded {filename} ({len(resp.content)} bytes)")
            return filepath
        except Exception as e:
            logging.error(f"Failed to download {filename}: {e}")
            return None

    # ---------- Public domain verification ----------
    def load_public_domain_cache(self) -> Set[str]:
        """Load cached set of verified public-domain object IDs from disk."""
        cache_file = TEMP_DATA_DIR / "public_domain_ids.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    return set(str(i) for i in data)
            except Exception:
                return set()
        return set()

    def save_public_domain_cache(self):
        cache_file = TEMP_DATA_DIR / "public_domain_ids.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as fh:
                json.dump(list(self.public_domain_ids), fh)
        except Exception as e:
            logging.warning(f"Failed to save public domain cache: {e}")

    def is_public_domain(self, object_id: str, uuid: str = "") -> bool:
        """Verify whether NGA designates the *image* for this object as public domain.

        Strategy (in order):
         1. Check cached results
         2. Try object page URLs and look for the canonical phrase used by NGA:
            "This object's media is free and in the public domain."
         3. As a fallback, try the IIIF/zoom API link (api.nga.gov) referenced on pages
            to detect download availability.

        Results are cached to TEMP_DATA_DIR/public_domain_ids.json to avoid repeated scraping.
        """
        if object_id in self.public_domain_ids:
            return True

        candidates = [
            f"https://www.nga.gov/artworks/{object_id}",
            f"https://www.nga.gov/artworks/{object_id}-",
            f"https://www.nga.gov/collection/art-object-page.{object_id}.html"
        ]

        headers = {"User-Agent": "ngafetch/1.0 (check public-domain)"}
        phrase_patterns = [
            "This object's media is free and in the public domain",
            "This object\u2019s media is free and in the public domain",  # typographic apostrophe
            "media is free and in the public domain",
            "Image Download Available",
            "Download"  # last-resort cue (will be combined with api.nga.gov presence)
        ]

        found_pd = False
        for url in candidates:
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code != 200:
                    continue
                text = resp.text
                # quick textual checks
                for p in phrase_patterns:
                    if p in text:
                        found_pd = True
                        break
                if found_pd:
                    break
                # check presence of api.nga.gov download link (common on PD pages)
                if "api.nga.gov" in text and ("download" in text.lower() or "public domain" in text.lower() or "cc0" in text.lower()):
                    found_pd = True
                    break
            except Exception:
                continue

        if found_pd:
            self.public_domain_ids.add(object_id)
            # persist cache opportunistically
            self.save_public_domain_cache()
            return True

        return False


    def load_objects_csv(self, filepath: Path) -> Dict[str, Dict]:
        """Load and filter objects.csv"""
        objects = {}
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    object_id = row.get('objectid', '').strip()
                    classification = row.get('classification', '').strip().lower()
                    location_id = row.get('locationid', '').strip()
                    
                    if not object_id:
                        continue
                    
                    # Filter by classification
                    classifications_lower = [c.lower() for c in SEARCH_PARAMS.get('classifications', [])]
                    if classifications_lower and classification not in classifications_lower:
                        continue
                    
                    # Filter by on view status (has locationid means it's on view)
                    if SEARCH_PARAMS.get('onView', False):
                        if not location_id:
                            continue
                    
                    objects[object_id] = row
            
            logging.info(f"Loaded {len(objects)} objects matching filters from objects.csv")
            return objects
        except Exception as e:
            logging.error(f"Error loading objects.csv: {e}")
            return {}

    def load_published_images_csv(self, filepath: Path) -> Dict[str, str]:
        """Load published_images.csv and create objectid -> uuid mapping
        Optionally filter for downloadable images (viewtype = 'primary')
        """
        mappings = {}
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    object_id = row.get('depictstmsobjectid', '').strip()
                    uuid = row.get('uuid', '').strip()
                    viewtype = row.get('viewtype', '').strip().lower()
                    
                    if not object_id or not uuid:
                        continue
                    
                    # Filter for downloadable images (viewtype = 'primary' indicates main downloadable image)
                    if SEARCH_PARAMS.get('downloadable', False):
                        if viewtype != 'primary':
                            continue
                    
                    # Only keep the first matching UUID for each object
                    if object_id not in mappings:
                        mappings[object_id] = uuid
            
            logging.info(f"Loaded {len(mappings)} image mappings from published_images.csv")
            return mappings
        except Exception as e:
            logging.error(f"Error loading published_images.csv: {e}")
            return {}

    def fetch_available_artworks(self) -> List[str]:
        """
        Download CSV files from GitHub and filter for eligible artworks
        """
        print("\nDownloading NGA open data from GitHub...")
        
        # Download CSVs
        objects_path = self.download_csv(OBJECTS_CSV_URL, "objects.csv")
        images_path = self.download_csv(PUBLISHED_IMAGES_CSV_URL, "published_images.csv")
        
        if not objects_path or not images_path:
            logging.error("Failed to download required CSV files")
            return []
        
        # Load and process data
        self.objects_data = self.load_objects_csv(objects_path)
        self.image_mappings = self.load_published_images_csv(images_path)
        
        # Find objects that have images
        available_ids = []
        for object_id in self.objects_data.keys():
            if object_id in self.image_mappings:
                available_ids.append(object_id)
        
        logging.info(f"Found {len(available_ids)} artworks with images matching filters")
        return available_ids

    def compare_and_report(self, api_ids: List[str], existing_ids: Set[str]) -> List[str]:
        api_ids_str = set(api_ids)
        already_have = api_ids_str & existing_ids
        blacklisted = api_ids_str & self.blacklist_ids
        new_ids_str = api_ids_str - existing_ids - self.blacklist_ids
        new_ids = sorted(list(new_ids_str), key=lambda x: int(x) if x.isdigit() else x)

        print("\n" + "="*70)
        print("COMPARISON RESULTS (NGA)")
        print("="*70)
        print(f"Total artworks from data:    {len(api_ids)}")
        print(f"IDs in collection:           {len(existing_ids)}")
        print(f"Blacklisted IDs:             {len(self.blacklist_ids)}")
        print(f"Overlap (Data ∩ Collection): {len(already_have)}")
        print(f"Blacklisted (Data ∩ Skip):   {len(blacklisted)}")
        print(f"New artworks available:      {len(new_ids)}")
        print(f"Will download (max):         {min(MAX_NEW_ARTWORKS, len(new_ids))}")

        if new_ids:
            sample = new_ids[:50]
            print(f"\nNew artwork IDs (first {min(50, len(new_ids))}):")
            print(sample)
            if len(new_ids) > 50:
                print(f"... and {len(new_ids) - 50} more")

        print("="*70 + "\n")

        logging.info(f"Found {len(new_ids)} new artworks (NGA)")
        return new_ids

    # ---------- Metadata + image fetch ----------
    def get_artwork_metadata(self, object_id: str) -> Optional[Dict]:
        """Get metadata from loaded CSV data"""
        try:
            if object_id not in self.objects_data:
                logging.warning(f"Object {object_id} not found in loaded data")
                return None
            
            if object_id not in self.image_mappings:
                logging.warning(f"Object {object_id} has no image UUID. Blacklisting.")
                self.add_to_blacklist(object_id, "No image UUID")
                return None
            
            return self.objects_data[object_id]
        except Exception as e:
            logging.error(f"Error getting metadata for {object_id}: {e}")
            return None

    def download_image(self, uuid: str, object_id: str) -> Optional[str]:
        if not uuid:
            return None
        
        try:
            image_url = IIIF_IMAGE_TEMPLATE.format(uuid=uuid)
            resp = requests.get(image_url, timeout=40, stream=True)
            resp.raise_for_status()
            
            content_type = resp.headers.get("content-type", "")
            ext = ".png" if "png" in content_type else ".jpg"
            filename = f"{object_id}{ext}"
            filepath = IMAGES_OUTPUT_DIR / filename
            
            with open(filepath, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
            
            logging.info(f"Downloaded image for {object_id} -> {filename}")
            return filename
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to download image for {object_id}: {e}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error saving image for {object_id}: {e}")
            return None

    def format_metadata(self, data: Dict, object_id: str, local_image_filename: str, verified_public_domain: bool) -> Dict:
        """Map NGA CSV fields to metadata structure"""
        uuid = self.image_mappings.get(object_id, "")
        
        # Get artist name
        attribution = data.get('attribution', '')
        artist_name = attribution.split(',')[0] if attribution else ''
        
        # Build credit line
        credit = data.get('creditline', '')
        credit_line = f"National Gallery of Art. {credit}" if credit else "National Gallery of Art"
        
        # Get dimensions
        dimensions = data.get('dimensions', '')
        
        # Build object URL
        object_url = f"https://www.nga.gov/collection/art-object-page.{object_id}.html"
        
        # Get medium
        medium = data.get('medium', '')
        
        # Get date info
        date_display = data.get('displaydate', '')
        begin_year = data.get('beginyear', '')
        end_year = data.get('endyear', '')
        
        return {
            "objectID": object_id,
            "title": data.get('title', 'Untitled'),
            "artistDisplayName": artist_name,
            "objectDate": date_display,
            "beginYear": begin_year,
            "endYear": end_year,
            "objectName": data.get('classification', ''),
            "medium": medium,
            "dimensions": dimensions,
            "department": "",
            "culture": "",
            "period": "",
            "dynasty": "",
            "creditLine": credit_line,
            "objectURL": object_url,
            "isPublicDomain": verified_public_domain,  # Verified from NGA object page
            "imageUUID": uuid,
            "iiifImageURL": IIIF_IMAGE_TEMPLATE.format(uuid=uuid),
            "localImage": local_image_filename,
            "tags": []
        }

    def save_metadata(self, metadata: Dict, object_id: str) -> bool:
        try:
            filepath = METADATA_OUTPUT_DIR / f"{object_id}.json"
            with open(filepath, "w", encoding="utf-8") as fh:
                json.dump(metadata, fh, indent=2, ensure_ascii=False)
            logging.info(f"Saved metadata for {object_id}")
            return True
        except Exception as e:
            logging.error(f"Failed to save metadata for {object_id}: {e}")
            return False

    def append_to_artworkids(self, object_id: str) -> bool:
        try:
            if TEMP_NEWIDS_FILE.exists():
                with open(TEMP_NEWIDS_FILE, "r", encoding="utf-8") as fh:
                    try:
                        ids = json.load(fh)
                    except Exception:
                        ids = []
            else:
                ids = []

            if object_id not in ids:
                ids.append(str(object_id))
                with open(TEMP_NEWIDS_FILE, "w", encoding="utf-8") as fh:
                    json.dump(ids, fh, indent=2)
                logging.info(f"Appended {object_id} to {TEMP_NEWIDS_FILE}")
            return True
        except Exception as e:
            logging.error(f"Failed to append to {TEMP_NEWIDS_FILE}: {e}")
            return False

    # ---------- Process single artwork ----------
    def process_artwork(self, object_id: str) -> bool:
        logging.info(f"Processing NGA artwork {object_id}...")
        
        data = self.get_artwork_metadata(object_id)
        if not data:
            self.failed_downloads.append({"objectID": object_id, "reason": "Failed to get metadata or blacklisted"})
            return False

        time.sleep(RATE_LIMIT_DELAY)
        
        uuid = self.image_mappings.get(object_id)
        local_image_filename = self.download_image(uuid, object_id)
        
        if not local_image_filename:
            self.failed_downloads.append({"objectID": object_id, "reason": "Failed image download"})
            return False

        # Check public domain status
        verified_public_domain = self.is_public_domain(object_id, uuid)
        if not verified_public_domain:
            self.failed_downloads.append({"objectID": object_id, "reason": "Not verified as public domain"})
            return False
            
        metadata = self.format_metadata(data, object_id, local_image_filename, verified_public_domain)
        
        if not self.save_metadata(metadata, object_id):
            self.failed_downloads.append({"objectID": object_id, "reason": "Failed to save metadata"})
            return False

        if not self.append_to_artworkids(object_id):
            self.failed_downloads.append({"objectID": object_id, "reason": "Failed to update artworkids.json"})
            return False

        self.successful_downloads.append({
            "objectID": object_id,
            "title": metadata.get("title"),
            "artist": metadata.get("artistDisplayName")
        })
        self.downloaded_count += 1
        logging.info(f"✓ Successfully processed artwork {object_id}")
        return True

    # ---------- Run ----------
    def run(self):
        start_time = datetime.now()

        print("\n" + "="*70)
        print("NATIONAL GALLERY OF ART DOWNLOADER")
        print("="*70)
        print(f"Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Max new artworks to download: {MAX_NEW_ARTWORKS}")
        
        # Print active filters
        active_filters = []
        classifications = SEARCH_PARAMS.get('classifications', [])
        if classifications:
            active_filters.append(f"Classifications: {', '.join(classifications)}")
        if SEARCH_PARAMS.get('publicDomain', False):
            active_filters.append("Public Domain: True")
        if SEARCH_PARAMS.get('onView', False):
            active_filters.append("On View: True")
        if SEARCH_PARAMS.get('downloadable', False):
            active_filters.append("Downloadable Images: True")
        
        if active_filters:
            print("Active filters:")
            for filter_str in active_filters:
                print(f"  - {filter_str}")
        
        print("="*70 + "\n")

        logging.info("Starting NGA download process")
        logging.info(f"Configuration: MAX_NEW_ARTWORKS={MAX_NEW_ARTWORKS}")
        logging.info(f"Classifications filter: {classifications}")

        self.existing_ids = self.load_existing_ids()
        self.blacklist_ids = self.load_blacklist()

        api_ids = self.fetch_available_artworks()
        if not api_ids:
            print("✗ No artworks found matching filters. Exiting.")
            logging.error("No artworks found")
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
                artist = item.get("artist") or "Unknown Artist"
                print(f"  - {item['objectID']}: {item.get('title')} by {artist}")

        if self.failed_downloads:
            print("\n✗ Failed downloads:")
            for item in self.failed_downloads:
                print(f"  - {item.get('objectID')}: {item.get('reason')}")

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

# -----------------------------------------------------------------------------
def main():
    downloader = NGADownloader()
    downloader.run()

if __name__ == "__main__":
    main()
