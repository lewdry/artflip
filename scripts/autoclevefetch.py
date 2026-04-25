#!/usr/bin/env python3
# =============================================================================
# autoclevefetch.py — Cleveland Museum of Art collection fetcher
# =============================================================================
# Built against the CMA Open Access API v4 (openaccess-api.clevelandart.org).
#
#   Search endpoint  https://openaccess-api.clevelandart.org/api/artworks/
#     - Simple REST query-param API (not Elasticsearch)
#     - Filters: cc0 (flag), type=Painting, has_image=1, currently_on_view (flag)
#     - Paginated via skip (offset) + limit; total count in info.total
#     - Max 1000 records per page; capped at MAX_SEARCH_RESULTS_CAP total IDs
#
#   Per-object metadata  https://openaccess-api.clevelandart.org/api/artworks/{id}
#     - Fetched by numeric Athena id (from search results)
#     - Artist cleaned from creators[0].description (strip parenthetical)
#     - culture field is a list → joined with "; "
#
#   Image  images.web.url (~900px JPEG, CDN-hosted)
#     - Closest resolution match to the ~843px used by ARTIC and Met scripts
#     - No authentication or special headers required
#
#   ID format  accession_number string (e.g. "1953.424")
#     - Avoids numeric collision with Met/NGA/ARTIC IDs in artworkids.json
#     - load_existing_ids() filters to IDs containing "." (CMA-specific pattern)
#     - Metadata saved as {accession_number}.json, image as {accession_number}.jpg
#
#   Paths  anchored to repo root via Path(__file__).parent.parent so the
#          script can be run from any working directory.
# =============================================================================
import requests
import json
import time
from pathlib import Path
from typing import List, Dict, Optional, Set
from datetime import datetime
from PIL import Image, ImageFilter

# ============================================================================
# CONFIGURATION
# ============================================================================

MAX_NEW_ARTWORKS = 20
RATE_LIMIT_DELAY = 1.0  # seconds between API calls

# Search parameters
SEARCH_PARAMS = {
    'type': 'Painting',
    'has_image': 1,
    # 'cc0' and 'currently_on_view' are flag params (no value) — handled separately
}

# File paths
_REPO_ROOT = Path(__file__).parent.parent
ARTWORKIDS_FILE = _REPO_ROOT / "public/artworkids.json"
METADATA_OUTPUT_DIR = _REPO_ROOT / "public/metadata"
IMAGES_OUTPUT_DIR = _REPO_ROOT / "public/images"
THUMBS_DIR        = _REPO_ROOT / "public/thumbs"
DONTFETCH_FILE = Path(__file__).parent / "clevedontfetch.json"

# Pagination
SEARCH_PAGE_LIMIT = 1000       # max records per page the API allows
MAX_SEARCH_RESULTS_CAP = 10000 # safety cap on total IDs collected

# ============================================================================
# CMA API endpoints
# ============================================================================
API_BASE = "https://openaccess-api.clevelandart.org/api"
SEARCH_ENDPOINT = f"{API_BASE}/artworks/"
ARTWORK_ENDPOINT = f"{API_BASE}/artworks"

# ============================================================================
# Downloader class
# ============================================================================

def generate_thumbnail(src_path: Path, thumb_stem: str) -> None:
    """Generate a 50×50 WebP thumbnail matching the microfiche display format."""
    try:
        with Image.open(src_path) as img:
            if img.mode != 'RGB':
                img = img.convert('RGB')
            w, h = img.size
            min_dim = min(w, h)
            left = (w - min_dim) // 2
            top = (h - min_dim) // 2
            img = img.crop((left, top, left + min_dim, top + min_dim))
            img = img.resize((100, 100), Image.LANCZOS)
            img = img.filter(ImageFilter.UnsharpMask(radius=0.3, percent=150, threshold=3))
            img.save(THUMBS_DIR / f"{thumb_stem}.webp", 'WEBP', quality=60, method=6)
    except Exception as e:
        print(f"  ⚠ Thumbnail generation failed for {thumb_stem}: {e}")


class CleveDownloader:
    def __init__(self):
        self.existing_ids: Set[str] = set()
        self.blacklist_ids: Set[str] = set()
        self.downloaded_count = 0
        self.failed_downloads = []
        self.successful_downloads = []
        self.newly_blacklisted = []

        METADATA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        IMAGES_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        THUMBS_DIR.mkdir(parents=True, exist_ok=True)

    # ---------- File loaders ----------

    def load_existing_ids(self) -> Set[str]:
        """Load CMA artwork IDs from artworkids.json.
        CMA uses accession_number as its ID (e.g. '1953.424'), which always
        contains a '.' — this distinguishes them from the pure-numeric IDs
        used by Met, NGA, and ARTIC in the shared list.
        """
        try:
            if ARTWORKIDS_FILE.exists():
                with open(ARTWORKIDS_FILE, "r") as f:
                    all_ids = json.load(f)
                return {str(i) for i in all_ids if "." in str(i)}
            return set()
        except Exception:
            return set()

    def load_blacklist(self) -> Set[str]:
        try:
            if DONTFETCH_FILE.exists():
                with open(DONTFETCH_FILE, "r") as f:
                    data = json.load(f)
                return set(data) if isinstance(data, list) else set()
            return set()
        except Exception:
            return set()

    def add_to_blacklist(self, accession_number: str, reason: str = "") -> bool:
        try:
            if DONTFETCH_FILE.exists():
                with open(DONTFETCH_FILE, "r") as f:
                    current = json.load(f)
            else:
                current = []

            if accession_number not in current:
                current.append(accession_number)
                current.sort()
                with open(DONTFETCH_FILE, "w") as f:
                    json.dump(current, f, indent=2)
                self.blacklist_ids.add(accession_number)
                self.newly_blacklisted.append({
                    'objectID': accession_number,
                    'reason': reason
                })
                return True
            return False
        except Exception:
            return False

    # ---------- Search / compare ----------

    def fetch_available_artworks(self) -> List[Dict]:
        """Paginate through CMA search and return a list of {id, accession_number} dicts."""
        all_items: List[Dict] = []
        skip = 0

        try:
            while len(all_items) < MAX_SEARCH_RESULTS_CAP:
                # Flag params ('cc0', 'currently_on_view') must be present in the URL
                # with no value; build them into the base URL and use params for the rest.
                params = {
                    **SEARCH_PARAMS,
                    'skip': skip,
                    'limit': SEARCH_PAGE_LIMIT,
                    'fields': 'id,accession_number',
                }
                # Append flag params as bare keys (no value)
                url = f"{SEARCH_ENDPOINT}?cc0&currently_on_view"

                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                info = data.get('info', {})
                total = info.get('total', 0)
                page_items = data.get('data', [])

                if not page_items:
                    break

                for item in page_items:
                    acc = item.get('accession_number')
                    art_id = item.get('id')
                    if acc and art_id:
                        all_items.append({'id': art_id, 'accession_number': acc})

                print(f"  Page fetched: skip={skip}, got {len(page_items)} items "
                      f"(total so far: {len(all_items)} / {total})")

                skip += SEARCH_PAGE_LIMIT
                if skip >= total:
                    break

                time.sleep(RATE_LIMIT_DELAY)

            return all_items

        except requests.exceptions.RequestException as e:
            print(f"\n❌ Network error fetching artwork list: {e}")
            return []
        except Exception as e:
            print(f"\n❌ Unexpected error fetching artwork list: {e}")
            return []

    def compare_and_report(self, api_items: List[Dict], existing_ids: Set[str]) -> List[Dict]:
        api_accessions = {item['accession_number'] for item in api_items}
        already_have = api_accessions & existing_ids
        blacklisted = api_accessions & self.blacklist_ids
        new_accessions = api_accessions - existing_ids - self.blacklist_ids

        # Rebuild list preserving original order, filtered to new only
        new_items = [i for i in api_items if i['accession_number'] in new_accessions]

        print("\n" + "="*70)
        print("COMPARISON RESULTS (CMA)")
        print("="*70)
        print(f"Total artworks from API:     {len(api_items)}")
        print(f"CMA IDs in collection:       {len(existing_ids)}")
        print(f"Blacklisted IDs:             {len(self.blacklist_ids)}")
        print(f"Overlap (API ∩ Collection):  {len(already_have)}")
        print(f"Blacklisted (API ∩ Skip):    {len(blacklisted)}")
        print(f"New artworks available:      {len(new_items)}")
        print(f"Will download (max):         {min(MAX_NEW_ARTWORKS, len(new_items))}")

        if new_items:
            sample = [i['accession_number'] for i in new_items[:50]]
            print(f"\nNew accession numbers (first {min(50, len(new_items))}):")
            print(sample)
            if len(new_items) > 50:
                print(f"  ... and {len(new_items) - 50} more")

        print("="*70 + "\n")
        return new_items

    # ---------- Metadata + image fetch ----------

    def fetch_artwork_metadata(self, artwork_id: int) -> Optional[Dict]:
        """Fetch full metadata for a single artwork by its numeric Athena id."""
        try:
            url = f"{ARTWORK_ENDPOINT}/{artwork_id}"
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            payload = resp.json()
            return payload.get('data')
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else '?'
            print(f"  ⚠ HTTP {status} fetching artwork {artwork_id}")
            return None
        except Exception as e:
            print(f"  ⚠ Error fetching artwork {artwork_id}: {e}")
            return None

    def download_image(self, image_url: str, accession_number: str) -> Optional[str]:
        if not image_url:
            return None
        try:
            resp = requests.get(image_url, timeout=30, stream=True)
            resp.raise_for_status()
            # Infer extension from Content-Type, default to jpg
            content_type = resp.headers.get('Content-Type', 'image/jpeg')
            ext = 'png' if 'png' in content_type else 'jpg'
            filename = f"{accession_number}.{ext}"
            filepath = IMAGES_OUTPUT_DIR / filename
            with open(filepath, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            generate_thumbnail(filepath, Path(filename).stem)
            print(f"  ✓ Image saved: {filename}")
            return filename
        except requests.exceptions.RequestException as e:
            print(f"  ❌ Image download failed for {accession_number}: {e}")
            return None

    def clean_artist_name(self, creators: list) -> str:
        """Extract display name from creators list.
        creators[0].description is typically 'Name (Nationality, dates)'.
        Strip the parenthetical to return just the name.
        """
        if not creators:
            return ''
        desc = creators[0].get('description', '')
        if not desc:
            return ''
        name = desc.split('(')[0].strip()
        return name

    def format_metadata(self, artwork_data: Dict, local_image_filename: str) -> Dict:
        accession_number = artwork_data.get('accession_number', '')
        creators = artwork_data.get('creators') or []
        culture_list = artwork_data.get('culture') or []
        culture_str = '; '.join(culture_list) if isinstance(culture_list, list) else str(culture_list)

        return {
            'objectID': accession_number,
            'title': artwork_data.get('title', 'Untitled'),
            'artistDisplayName': self.clean_artist_name(creators),
            'objectDate': artwork_data.get('creation_date', ''),
            'medium': (lambda m: m[0].upper() + m[1:] if m else '')(artwork_data.get('technique', '')),
            'dimensions': artwork_data.get('measurements', ''),
            'department': artwork_data.get('department', ''),
            'culture': culture_str,
            'creditLine': 'Cleveland Museum of Art. ' + (artwork_data.get('creditline') or ''),
            'objectURL': artwork_data.get('url', f"https://clevelandart.org/art/{accession_number}"),
            'isPublicDomain': artwork_data.get('share_license_status') == 'CC0',
            'localImage': local_image_filename,
            'tags': artwork_data.get('alternate_titles') or [],
        }

    def save_metadata(self, metadata: Dict, accession_number: str) -> bool:
        try:
            filepath = METADATA_OUTPUT_DIR / f"{accession_number}.json"
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"  ❌ Failed to save metadata for {accession_number}: {e}")
            return False

    def append_to_artworkids(self, accession_number: str) -> bool:
        try:
            if ARTWORKIDS_FILE.exists():
                with open(ARTWORKIDS_FILE, "r") as f:
                    ids = json.load(f)
            else:
                ids = []

            if accession_number not in ids:
                ids.append(accession_number)
                with open(ARTWORKIDS_FILE, "w") as f:
                    json.dump(ids, f, indent=2)
            return True
        except Exception as e:
            print(f"  ❌ Failed to update artworkids.json for {accession_number}: {e}")
            return False

    # ---------- Process single artwork ----------

    def process_artwork(self, item: Dict) -> bool:
        artwork_id = item['id']
        accession_number = item['accession_number']

        artwork_data = self.fetch_artwork_metadata(artwork_id)
        if not artwork_data:
            self.failed_downloads.append({
                'objectID': accession_number,
                'reason': 'Failed to fetch metadata'
            })
            return False

        # Verify CC0 at the individual record level
        if artwork_data.get('share_license_status') != 'CC0':
            self.add_to_blacklist(accession_number, 'Not CC0')
            return False

        time.sleep(RATE_LIMIT_DELAY)

        images = artwork_data.get('images') or {}
        image_url = (images.get('web') or {}).get('url', '')
        if not image_url:
            self.add_to_blacklist(accession_number, 'No web image URL')
            return False

        local_image_filename = self.download_image(image_url, accession_number)
        if not local_image_filename:
            self.failed_downloads.append({
                'objectID': accession_number,
                'reason': 'Image download failed'
            })
            return False

        metadata = self.format_metadata(artwork_data, local_image_filename)

        if not self.save_metadata(metadata, accession_number):
            self.failed_downloads.append({
                'objectID': accession_number,
                'reason': 'Failed to save metadata'
            })
            return False

        if not self.append_to_artworkids(accession_number):
            self.failed_downloads.append({
                'objectID': accession_number,
                'reason': 'Failed to update artworkids.json'
            })
            return False

        self.successful_downloads.append({
            'objectID': accession_number,
            'title': metadata['title'],
            'artist': metadata['artistDisplayName']
        })
        self.downloaded_count += 1
        return True

    # ---------- Run ----------

    def run(self):
        start_time = datetime.now()

        print("\n" + "="*70)
        print("CLEVELAND MUSEUM OF ART ARTWORK DOWNLOADER")
        print("="*70)
        print(f"Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Max new artworks to download: {MAX_NEW_ARTWORKS}")
        print(f"Filters: CC0, type=Painting, has_image=1, currently_on_view")
        print("="*70 + "\n")

        self.existing_ids = self.load_existing_ids()
        self.blacklist_ids = self.load_blacklist()

        print(f"CMA IDs already in collection: {len(self.existing_ids)}")
        print(f"Blacklisted IDs:               {len(self.blacklist_ids)}\n")

        print("Fetching artwork list from CMA API...")
        api_items = self.fetch_available_artworks()
        if not api_items:
            print("❌ No artworks returned from API. Exiting.")
            return

        new_items = self.compare_and_report(api_items, self.existing_ids)
        if not new_items:
            print("✓ Collection is up to date. No new artworks to download.")
            return

        to_download = new_items[:MAX_NEW_ARTWORKS]
        print(f"Starting download of {len(to_download)} artworks...\n")

        for idx, item in enumerate(to_download, 1):
            acc = item['accession_number']
            print(f"[{idx}/{len(to_download)}] Processing {acc}...")
            self.process_artwork(item)

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
        print(f"  - IDs:      {ARTWORKIDS_FILE}")
        print(f"  - Blacklist: {DONTFETCH_FILE}")

        print("\n" + "="*70)
        if self.downloaded_count > 0:
            print(f"✓ Process completed successfully! Downloaded {self.downloaded_count} new artwork(s).")
        else:
            print("⚠ Process completed with no successful downloads.")
        print("="*70 + "\n")


def main():
    downloader = CleveDownloader()
    downloader.run()


if __name__ == "__main__":
    main()
