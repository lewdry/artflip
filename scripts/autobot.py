import json
import random
import requests
import os
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ================= CONFIG =================
# Get secrets from environment variables
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")

BASE_RAW_URL = "https://raw.githubusercontent.com/lewdry/artflip/main/public"
ARTWORK_IDS_URL = f"{BASE_RAW_URL}/artworkids.json"
METADATA_BASE_URL = f"{BASE_RAW_URL}/metadata"
IMAGES_DIR = "images"

GRAPH_API_BASE = "https://graph.facebook.com/v18.0"
# ==========================================


# ------------------ Helper Functions ------------------

def pick_random_artwork():
    """Pick a random objectID from the JSON list via URL."""
    resp = requests.get(ARTWORK_IDS_URL)
    resp.raise_for_status()
    artwork_ids = resp.json()
    return random.choice(artwork_ids)

def get_metadata(object_id):
    """Load metadata JSON for a given objectID via URL."""
    url = f"{METADATA_BASE_URL}/{object_id}.json"
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()

def format_caption(metadata):
    """Build the caption according to your formatting rules."""
    lines = []

    title = metadata.get("title")
    if title:
        lines.append(title)

    artist = metadata.get("artistDisplayName")
    date = metadata.get("objectDate")
    artist_line = ""
    if artist and date:
        artist_line = f"{artist}, {date}"
    elif artist:
        artist_line = artist
    elif date:
        artist_line = date
    if artist_line:
        lines.append(artist_line)

    medium = metadata.get("medium")
    if medium:
        lines.append(medium)

    culture = metadata.get("culture")
    if culture:
        lines.append(culture)

    credit = metadata.get("creditLine")
    if credit:
        credit_first_part = credit.split(".")[0]
        if credit_first_part:
            lines.append(credit_first_part)

    return "\n".join(lines)

def create_media_container(image_url, caption):
    """Create a media container for the image and caption."""
    url = f"{GRAPH_API_BASE}/{IG_USER_ID}/media"
    payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": ACCESS_TOKEN
    }
    resp = requests.post(url, data=payload)
    resp.raise_for_status()
    return resp.json()["id"]

def check_media_status(creation_id):
    """Check the status of the media container until it's ready."""
    url = f"{GRAPH_API_BASE}/{creation_id}"
    params = {
        "fields": "status_code",
        "access_token": ACCESS_TOKEN
    }
    
    # Check status up to 10 times, waiting 3 seconds between checks
    for _ in range(10): 
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        status = resp.json().get("status_code")
        
        print(f"Current media status: {status}")
        
        if status == "FINISHED":
            return True
        elif status == "ERROR":
            print("Media container processing failed.")
            return False
            
        # Wait before checking again
        time.sleep(3)
        
    print("Media container did not become ready in time.")
    return False


def publish_media(creation_id):
    """Publish the media using its creation ID."""
    url = f"{GRAPH_API_BASE}/{IG_USER_ID}/media_publish"
    payload = {
        "creation_id": creation_id,
        "access_token": ACCESS_TOKEN
    }
    resp = requests.post(url, data=payload)
    resp.raise_for_status()
    return resp.json()

# ------------------ Main Script ------------------

def main():
    # Check if secrets are loaded
    if not ACCESS_TOKEN or not IG_USER_ID:
        print("Error: ACCESS_TOKEN or IG_USER_ID not found in environment variables.")
        return

    try:
        object_id = pick_random_artwork()
        metadata = get_metadata(object_id)
    except Exception as e:
        print("Error picking artwork or loading metadata:", e)
        return

    caption = format_caption(metadata)
    image_url = f"{BASE_RAW_URL}/{IMAGES_DIR}/{object_id}.jpg"

    print(f"Posting artwork {object_id} with caption:\n{caption}")

    try:
        creation_id = create_media_container(image_url, caption)
        
        # NEW: Wait for media to be ready before publishing
        if check_media_status(creation_id):
            result = publish_media(creation_id)
            print("Post published successfully:", result)
        else:
            print("Failed to publish media because it was not ready.")

    except requests.HTTPError as e:
        print("Error posting to Instagram:", e.response.text)
    except Exception as e:
        print("Unexpected error:", e)

if __name__ == "__main__":
    main()
