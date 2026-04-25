#!/usr/bin/env python3
# =============================================================================
# autometfetch.py — Metropolitan Museum of Art collection fetcher
# =============================================================================
# Built against the Met Museum Open Access Collection API (v1).
#
#   Search endpoint  https://collectionapi.metmuseum.org/public/collection/v1/search
#     - Returns a flat list of `objectIDs` matching query parameters
#     - Filters passed as URL query params: isHighlight, isPublicDomain, isOnView,
#       hasImages, objectName, departmentId, artistOrCulture, medium,
#       geoLocation, dateBegin/dateEnd, q
#     - No pagination: the full matched ID list is returned in one response
#
#   Per-object metadata  https://collectionapi.metmuseum.org/public/collection/v1/objects/{id}
#     - Title in `title`
#     - Artist in `artistDisplayName`
#     - Date in `objectDate`
#     - Medium in `medium`, dimensions in `dimensions`
#     - Public domain flag: `isPublicDomain` (boolean)
#     - Non-public-domain or imageless artworks are blacklisted immediately
#
#   Image  `primaryImageSmall` (web-large JPEG, hosted by the Met)
#     - Extension inferred from Content-Type header (jpg/png)
#
#   ID format  numeric integers; stored as strings in artworkids.json.
#     load_existing_ids() filters to numeric-only entries to avoid
#     collision with Rijksmuseum SK-* IDs in the shared list.
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
# CONFIGURATION - Modify these settings as needed
# ============================================================================

# Number of new artworks to download per run
MAX_NEW_ARTWORKS = 20

# Rate limiting (seconds between API calls)
RATE_LIMIT_DELAY = 1.0

# API Search Parameters - Set to None to ignore, or provide value to filter
# For auto script - looking for all public domain, highlight paintings with images
SEARCH_PARAMS = {
    'isHighlight': True,          # True = only highlights, False = non-highlights, None = all
    'isPublicDomain': True,       # True = public domain only, False = non-public, None = all
    'isOnView': True,          # True = on view only, False = not on view, None = all
    'hasImages': True,            # True = only with images, False = no images, None = all    
    
    # Object type filter - examples: "Paintings", "Sculpture", "Drawings", "Prints", 
    # "Photographs", "Textiles", "Ceramics", "Furniture", "Jewelry", "Vessels", etc.
    # Leave as None to get all types
    'objectName': "Paintings",  # Example: "Paintings" or None,
    
    # Department filter - examples: "American Decorative Arts", "Ancient Near Eastern Art",
    # "Arms and Armor", "Arts of Africa, Oceania, and the Americas", "Asian Art",
    # "The Cloisters", "The Costume Institute", "Drawings and Prints",
    # "Egyptian Art", "European Paintings", "European Sculpture and Decorative Arts",
    # "Greek and Roman Art", "Islamic Art", "The Robert Lehman Collection",
    # "The Libraries", "Medieval Art", "Musical Instruments", "Photographs",
    # "Modern Art", "The American Wing"
    'departmentId': None,         # Example: 11 (for European Paintings) or None
    
    # Artist/Maker filter
    'artistOrCulture': None,      # Example: "Rembrandt" or None
    
    # Medium filter - examples: "Oil on canvas", "Bronze", "Watercolor", etc.
    'medium': None,               # Example: "Oil on canvas" or None
    
    # Geographic location
    'geoLocation': None,          # Example: "France" or None
    
    # Date range (format: year or year-year)
    'dateBegin': None,            # Example: 1800 or None
    'dateEnd': None,              # Example: 1900 or None
    
    # Search query (searches across multiple fields)
    'q': "*",                    # Example: "landscape" or None
}

ARTWORKIDS_FILE = Path(__file__).parent.parent / "public" / "artworkids.json"
METADATA_OUTPUT_DIR = Path(__file__).parent.parent / "public" / "metadata"
IMAGES_OUTPUT_DIR = Path(__file__).parent.parent / "public" / "images"
THUMBS_DIR        = Path(__file__).parent.parent / "public" / "thumbs"
DONTFETCH_FILE = Path(__file__).parent / "metdontfetch.json"


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


class MetDownloader:
    def __init__(self):
        self.base_search_url = "https://collectionapi.metmuseum.org/public/collection/v1/search"
        self.base_object_url = "https://collectionapi.metmuseum.org/public/collection/v1/objects"
        self.existing_ids: Set[str] = set()  # Changed to string set to handle alphanumeric IDs
        self.blacklist_ids: Set[str] = set()  # IDs to skip
        self.downloaded_count = 0
        self.failed_downloads = []
        self.successful_downloads = []
        self.newly_blacklisted = []  # Track IDs added to blacklist this session
        
        # Create output directories if they don't exist
        METADATA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        IMAGES_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        THUMBS_DIR.mkdir(parents=True, exist_ok=True)
        
    def load_existing_ids(self) -> Set[str]:
        """Load existing artwork IDs from artworkids.json and filter for Met IDs only"""
        try:
            if ARTWORKIDS_FILE.exists():
                with open(ARTWORKIDS_FILE, 'r') as f:
                    data = json.load(f)
                    # Filter to only numeric IDs (Met Museum IDs)
                    # Rijksmuseum IDs start with "SK-" so we exclude those
                    met_ids = {str(id_val) for id_val in data if str(id_val).isdigit()}
                    return met_ids
            else:
                return set()
        except Exception as e:
            return set()
    
    def load_blacklist(self) -> Set[str]:
        """Load blacklisted IDs from metdontfetch.json"""
        try:
            if DONTFETCH_FILE.exists():
                with open(DONTFETCH_FILE, 'r') as f:
                    data = json.load(f)
                    blacklist = {str(id_val) for id_val in data}
                    return blacklist
            else:
                return set()
        except Exception as e:
            return set()
    
    def add_to_blacklist(self, object_id: int, reason: str = ""):
        """Add an ID to the blacklist file"""
        try:
            # Load current blacklist
            if DONTFETCH_FILE.exists():
                with open(DONTFETCH_FILE, 'r') as f:
                    blacklist = json.load(f)
            else:
                blacklist = []
            
            # Add new ID if not already there
            id_str = str(object_id)
            if id_str not in blacklist:
                blacklist.append(id_str)
                blacklist.sort(key=int)  # Keep sorted numerically
                
                # Save back
                with open(DONTFETCH_FILE, 'w') as f:
                    json.dump(blacklist, f, indent=2)
                
                self.newly_blacklisted.append({'objectID': object_id, 'reason': reason})
                return True
            
            return False
            
        except Exception as e:
            return False
    
    def build_search_url(self) -> str:
        """Build search URL from configured parameters"""
        params = []
        for key, value in SEARCH_PARAMS.items():
            if value is not None:
                if isinstance(value, bool):
                    params.append(f"{key}={str(value).lower()}")
                else:
                    params.append(f"{key}={value}")
        
        if params:
            return f"{self.base_search_url}?{'&'.join(params)}"
        else:
            # Default to highlights and public domain if no params
            return f"{self.base_search_url}?isHighlight=true&isPublicDomain=true"
    
    def fetch_available_artworks(self) -> List[int]:
        """Fetch list of artwork IDs from Met API based on search parameters"""
        try:
            url = self.build_search_url()
            response = requests.get(url, timeout=30)
            
            # Check for 502 Bad Gateway or other server errors
            if response.status_code == 502:
                print("\n❌ Met API is currently unavailable (502 error).")
                print("   This is a temporary server issue. Please try again in a few minutes.")
                return []
            
            response.raise_for_status()
            
            # Try to parse JSON, catch HTML responses from server errors
            try:
                data = response.json()
            except json.JSONDecodeError:
                print("\n❌ Met API returned an unexpected response format.")
                print("   The server may be experiencing issues. Please try again later.")
                return []
            
            object_ids = data.get("objectIDs", [])
            if not object_ids:
                return []
            
            return object_ids
            
        except requests.exceptions.RequestException as e:
            print(f"\n❌ Network error: {e}")
            return []
    
    def compare_and_report(self, api_ids: List[int], existing_ids: Set[str]) -> List[int]:
        """Compare API results with existing IDs and blacklist, report new ones"""
        # Convert API IDs to strings for comparison with existing IDs
        api_ids_str = {str(id_val) for id_val in api_ids}
        
        # Find IDs that are already downloaded OR blacklisted
        already_have = api_ids_str & existing_ids
        blacklisted = api_ids_str & self.blacklist_ids
        
        # Find new IDs: those in API results but NOT in existing collection AND NOT blacklisted
        new_ids_str = api_ids_str - existing_ids - self.blacklist_ids
        
        # Convert back to integers for API calls (API IDs are always numeric)
        new_ids = sorted([int(id_val) for id_val in new_ids_str])
        
        print("\n" + "="*70)
        print("COMPARISON RESULTS")
        print("="*70)
        print(f"Total artworks from API:     {len(api_ids)}")
        print(f"Met IDs in collection:       {len(existing_ids)}")
        print(f"Blacklisted IDs:             {len(self.blacklist_ids)}")
        print(f"Overlap (API ∩ Collection):  {len(already_have)}")
        print(f"Blacklisted (API ∩ Skip):    {len(blacklisted)}")
        print(f"New artworks available:      {len(new_ids)}")
        print(f"Will download (max):         {min(MAX_NEW_ARTWORKS, len(new_ids))}")
        
        if new_ids:
            new_ids_list = new_ids[:50]  # Show first 50
            print(f"\nNew artwork IDs (showing first {min(50, len(new_ids))}):")
            print(new_ids_list)
            if len(new_ids) > 50:
                print(f"... and {len(new_ids) - 50} more")
        
        print("="*70 + "\n")
        
        return new_ids
    
    def fetch_artwork_metadata(self, object_id: int) -> Optional[Dict]:
        """Fetch full metadata for a single artwork"""
        try:
            url = f"{self.base_object_url}/{object_id}"
            response = requests.get(url, timeout=15)
            response.raise_for_status() # Raises HTTPError for 4xx/5xx responses
            data = response.json()
            
            # Verify it's public domain and has an image
            if not data.get('isPublicDomain'):
                self.add_to_blacklist(object_id, "Not public domain")
                return None
            
            if not data.get('primaryImageSmall'):
                self.add_to_blacklist(object_id, "No image available")
                return None
            
            return data
            
        except requests.exceptions.HTTPError as e:
            # Specifically handle 404 and 502 errors by blacklisting the ID
            if e.response.status_code in [404, 502]:
                reason = f"HTTP {e.response.status_code} Error on fetch"
                self.add_to_blacklist(object_id, reason)
            return None # Fail this download
        
        except requests.exceptions.RequestException as e:
            return None # Fail this download
    
    def download_image(self, image_url: str, object_id: int) -> Optional[str]:
        """Download image from primaryImageSmall URL and save to images directory"""
        if not image_url:
            return None
        
        try:
            response = requests.get(image_url, timeout=30, stream=True)
            response.raise_for_status()
            
            # Determine file extension
            content_type = response.headers.get('content-type', '')
            if 'png' in content_type or image_url.endswith('.png'):
                ext = '.png'
            else:
                ext = '.jpg'  # default to jpg
            
            filename = f"{object_id}{ext}"
            filepath = IMAGES_OUTPUT_DIR / filename
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            generate_thumbnail(filepath, Path(filename).stem)
            return filename
            
        except requests.exceptions.RequestException as e:
            return None
    
    def format_metadata(self, artwork_data: Dict, local_image_filename: str) -> Dict:
        """Format metadata according to desired structure"""
        return {
            'objectID': artwork_data.get('objectID'),
            'title': artwork_data.get('title', 'Untitled'),
            'artistDisplayName': artwork_data.get('artistDisplayName', ''),
            'objectDate': artwork_data.get('objectDate', ''),
            'medium': (lambda m: m[0].upper() + m[1:] if m else '')(artwork_data.get('medium', '')),
            'dimensions': artwork_data.get('dimensions', ''),
            'department': artwork_data.get('department', ''),
            'culture': artwork_data.get('culture', ''),
            'creditLine': 'Metropolitan Museum of Art. ' + artwork_data.get('creditLine', ''),
            'objectURL': artwork_data.get('objectURL', ''),
            'isPublicDomain': artwork_data.get('isPublicDomain', False),
            'primaryImage': artwork_data.get('primaryImage', ''),  # Original URL
            'primaryImageSmall': artwork_data.get('primaryImageSmall', ''),  # Web-large URL
            'localImage': local_image_filename,  # Just the filename (e.g. "11865.jpg")
            'tags': artwork_data.get('tags', [])
        }
    
    def save_metadata(self, metadata: Dict, object_id: int) -> bool:
        """Save metadata to individual JSON file"""
        try:
            filepath = METADATA_OUTPUT_DIR / f"{object_id}.json"
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            return False
    
    def append_to_artworkids(self, object_id: int) -> bool:
        """Append new object ID to artworkids.json"""
        try:
            if ARTWORKIDS_FILE.exists():
                with open(ARTWORKIDS_FILE, 'r') as f:
                    ids = json.load(f)
            else:
                ids = []
            
            ids.append(str(object_id))
            
            with open(ARTWORKIDS_FILE, 'w') as f:
                json.dump(ids, f, indent=2)
            
            return True
            
        except Exception as e:
            return False
    
    def process_artwork(self, object_id: int) -> bool:
        """Process a single artwork: fetch metadata, download image, save both"""
        # Fetch metadata
        artwork_data = self.fetch_artwork_metadata(object_id)
        if not artwork_data:
            # The reason for failure (including blacklisting) is logged inside fetch_artwork_metadata
            self.failed_downloads.append({'objectID': object_id, 'reason': 'Failed to fetch or process metadata'})
            return False
        
        time.sleep(RATE_LIMIT_DELAY)  # Rate limiting
        
        # Download image from primaryImageSmall URL (web-large)
        image_url = artwork_data.get('primaryImageSmall', '')
        local_image_filename = self.download_image(image_url, object_id)
        if not local_image_filename:
            self.failed_downloads.append({'objectID': object_id, 'reason': 'Failed to download image'})
            return False
        
        # Format and save metadata
        metadata = self.format_metadata(artwork_data, local_image_filename)
        if not self.save_metadata(metadata, object_id):
            self.failed_downloads.append({'objectID': object_id, 'reason': 'Failed to save metadata'})
            return False
        
        # Update artworkids.json only if both metadata and image succeeded
        if not self.append_to_artworkids(object_id):
            self.failed_downloads.append({'objectID': object_id, 'reason': 'Failed to update artworkids.json'})
            return False
        
        # Success!
        self.successful_downloads.append({
            'objectID': object_id,
            'title': metadata['title'],
            'artist': metadata['artistDisplayName']
        })
        self.downloaded_count += 1
        
        return True
    
    def run(self):
        """Main execution flow"""
        start_time = datetime.now()
        
        print("\n" + "="*70)
        print("MET MUSEUM ARTWORK DOWNLOADER")
        print("="*70)
        print(f"Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Max new artworks to download: {MAX_NEW_ARTWORKS}")
        print("="*70 + "\n")
        
        # Load existing IDs
        self.existing_ids = self.load_existing_ids()
        
        # Load blacklist
        self.blacklist_ids = self.load_blacklist()
        
        # Fetch available artworks from API
        api_ids = self.fetch_available_artworks()
        if not api_ids:
            print("❌ No artworks found from API. Exiting.")
            return
        
        # Compare and identify new artworks
        new_ids = self.compare_and_report(api_ids, self.existing_ids)
        
        if not new_ids:
            print("✓ No new artworks to download. Collection is up to date!")
            return
        
        # Download first N new artworks
        artworks_to_download = new_ids[:MAX_NEW_ARTWORKS]
        
        print(f"\nStarting download of {len(artworks_to_download)} artworks...\n")
        
        for idx, object_id in enumerate(artworks_to_download, 1):
            print(f"[{idx}/{len(artworks_to_download)}] Processing artwork {object_id}...")
            self.process_artwork(object_id)
            time.sleep(RATE_LIMIT_DELAY)  # Rate limiting between artworks
        
        # Final summary
        self.print_summary(start_time)
    
    def print_summary(self, start_time: datetime):
        """Print final summary of download session"""
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
            print("\n🚫 Added to blacklist (metdontfetch.json):")
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
    downloader = MetDownloader()
    downloader.run()


if __name__ == "__main__":
    main()