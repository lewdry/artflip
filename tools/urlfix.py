import os
import json
import logging

# === CONFIG ===
DATA_DIR = "."  # folder where your 100 json files live
LOG_FILE = "update_log.txt"
OLD_PREFIX = "https://api.artic.edu/api/v1/artworks/"
NEW_BASE = "https://www.artic.edu/artworks/"

# === SETUP LOGGING ===
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def process_json_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        object_url = data.get("objectURL", "")
        object_id = data.get("objectID")

        # Check if it matches the target pattern
        if object_url.startswith(OLD_PREFIX):
            if not object_id:
                logging.warning(f"⚠️ Missing objectID in {filepath}, skipping.")
                return False

            new_url = f"{NEW_BASE}{object_id}"
            data["objectURL"] = new_url

            # Write the updated JSON back
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logging.info(f"✅ Updated objectURL in {filepath} → {new_url}")
            return True
        else:
            logging.info(f"— No change needed for {filepath}")
            return False

    except Exception as e:
        logging.error(f"❌ Failed to process {filepath}: {e}")
        return False


def main():
    json_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json")]
    total = len(json_files)
    updated_count = 0

    logging.info(f"Starting update for {total} JSON files in '{DATA_DIR}'...")

    for filename in json_files:
        filepath = os.path.join(DATA_DIR, filename)
        if process_json_file(filepath):
            updated_count += 1

    logging.info(f"🎯 Finished: {updated_count}/{total} files updated successfully.")


if __name__ == "__main__":
    main()