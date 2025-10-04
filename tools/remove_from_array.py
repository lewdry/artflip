import json
import os
from datetime import datetime

# File paths (same directory as script)
artwork_file = "artworkids.json"
non_public_file = "delete.json"
log_file = "deletion_log.txt"

def load_json(file_path):
    with open(file_path, "r") as f:
        data = json.load(f)
    # Normalize all entries: strip whitespace and quotes
    return [str(item).strip().strip('"').strip("'") for item in data]

def save_json(file_path, data):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)

def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(message)

def main():
    if not os.path.exists(artwork_file) or not os.path.exists(non_public_file):
        log("One or both JSON files are missing.")
        return

    artwork_ids = load_json(artwork_file)
    non_public_ids = load_json(non_public_file)

    initial_count = len(artwork_ids)
    removed_ids = [art_id for art_id in artwork_ids if art_id in non_public_ids]

    if removed_ids:
        artwork_ids = [art_id for art_id in artwork_ids if art_id not in non_public_ids]
        save_json(artwork_file, artwork_ids)
        log(f"Removed {len(removed_ids)} IDs from {artwork_file}: {removed_ids}")
    else:
        log("No IDs from non_public_domain_ids.json found in artworkids.json.")

    log(f"Artwork IDs before: {initial_count}, after: {len(artwork_ids)}")

if __name__ == "__main__":
    main()
