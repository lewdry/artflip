import json
import os
import shutil
from datetime import datetime

# File paths
ids_file = "non_public_domain_ids.json"
images_folder = "images"
metadata_folder = "metadata"
trash_folder = "trash"
log_file = "deletion_log.txt"

# Create trash folder if it doesn't exist
os.makedirs(trash_folder, exist_ok=True)

# Load object IDs
with open(ids_file, "r") as f:
    object_ids = json.load(f)

# Open log file
with open(log_file, "a") as log:

    def log_msg(message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] {message}"
        print(entry)
        log.write(entry + "\n")

    def move_to_trash(folder, extension):
        for obj_id in object_ids:
            file_name = f"{obj_id}.{extension}"
            file_path = os.path.join(folder, file_name)
            if os.path.exists(file_path):
                try:
                    shutil.move(file_path, trash_folder)
                    log_msg(f"Moved to trash: {file_path}")
                except Exception as e:
                    log_msg(f"ERROR moving {file_path}: {e}")
            else:
                log_msg(f"Not found: {file_path}")

    # Process images and metadata
    move_to_trash(images_folder, "jpg")
    move_to_trash(metadata_folder, "json")
