import json
import os
from pathlib import Path

def main():
    # Get all image files in delete folder
    delete_folder = Path("../public/delete") if Path("tools").exists() else Path("public/delete")
    image_files = list(delete_folder.glob("*.jpg"))

    # Extract object IDs from filenames (remove .jpg extension)
    object_ids_to_delete = []
    for img_file in image_files:
        if img_file.stem not in ['.DS_Store']:
            object_ids_to_delete.append(img_file.stem)

    print(f"Found {len(object_ids_to_delete)} images in delete folder")
    if object_ids_to_delete:
        print(f"Sample IDs: {object_ids_to_delete[:10]}")

    # Load artworkids.json
    artworkids_path = Path("../public/artworkids.json") if Path("tools").exists() else Path("public/artworkids.json")
    with open(artworkids_path, "r") as f:
        artwork_ids = json.load(f)
    original_count = len(artwork_ids)

    # Remove object IDs from artworkids.json
    removed_from_artworks = []
    for obj_id in object_ids_to_delete:
        if obj_id in artwork_ids:
            artwork_ids.remove(obj_id)
            removed_from_artworks.append(obj_id)

    print(f"\nRemoved {len(removed_from_artworks)} IDs from artworkids.json")
    print(f"Original count: {original_count}, New count: {len(artwork_ids)}")

    # Save updated artworkids.json
    with open(artworkids_path, "w") as f:
        json.dump(artwork_ids, f, indent=2)

    # Load dontfetch files
    chic_path = Path("../scripts/chicdontfetch.json") if Path("tools").exists() else Path("scripts/chicdontfetch.json")
    met_path = Path("../scripts/metdontfetch.json") if Path("tools").exists() else Path("scripts/metdontfetch.json")
    rijks_path = Path("../scripts/rijksdontfetch.json") if Path("tools").exists() else Path("scripts/rijksdontfetch.json")

    with open(chic_path, "r") as f:
        chic_dont_fetch = json.load(f)
    with open(met_path, "r") as f:
        met_dont_fetch = json.load(f)
    with open(rijks_path, "r") as f:
        rijks_dont_fetch = json.load(f)

    # Add numeric IDs to chic and met dontfetch, Rijks IDs to rijks
    numeric_ids = [obj_id for obj_id in object_ids_to_delete if obj_id.isdigit()]
    rijks_ids = [obj_id for obj_id in object_ids_to_delete if not obj_id.isdigit()]

    new_chic = 0
    new_met = 0
    new_rijks = 0
    for obj_id in numeric_ids:
        if obj_id not in chic_dont_fetch:
            chic_dont_fetch.append(obj_id)
            new_chic += 1
        if obj_id not in met_dont_fetch:
            met_dont_fetch.append(obj_id)
            new_met += 1
    for obj_id in rijks_ids:
        if obj_id not in rijks_dont_fetch:
            rijks_dont_fetch.append(obj_id)
            new_rijks += 1

    print(f"\nAdded {new_chic} new numeric IDs to chicdontfetch.json (total numeric: {len(numeric_ids)})")
    print(f"Added {new_met} new numeric IDs to metdontfetch.json (total numeric: {len(numeric_ids)})")
    print(f"Added {new_rijks} new Rijks IDs to rijksdontfetch.json (total Rijks: {len(rijks_ids)})")

    # Save updated dontfetch files
    with open(chic_path, "w") as f:
        json.dump(chic_dont_fetch, f, indent=2)
    with open(met_path, "w") as f:
        json.dump(met_dont_fetch, f, indent=2)
    with open(rijks_path, "w") as f:
        json.dump(rijks_dont_fetch, f, indent=2)

    # Delete metadata JSON files
    metadata_folder = Path("../public/metadata") if Path("tools").exists() else Path("public/metadata")
    deleted_json = []
    not_found_json = []
    for obj_id in object_ids_to_delete:
        json_file = metadata_folder / f"{obj_id}.json"
        if json_file.exists():
            json_file.unlink()
            deleted_json.append(obj_id)
        else:
            not_found_json.append(obj_id)

    print(f"\nDeleted {len(deleted_json)} JSON files from metadata folder")
    print(f"Could not find {len(not_found_json)} JSON files (already missing)")
    if not_found_json:
        print(f"\nJSON files not found for these IDs:")
        for obj_id in not_found_json[:20]:
            print(f"  - {obj_id}")
        if len(not_found_json) > 20:
            print(f"  ... and {len(not_found_json) - 20} more")

    not_in_artworks = [obj_id for obj_id in object_ids_to_delete if obj_id not in removed_from_artworks]
    if not_in_artworks:
        print(f"\nThese {len(not_in_artworks)} IDs were in delete folder but not in artworkids.json:")
        for obj_id in not_in_artworks[:30]:
            print(f"  - {obj_id}")
        if len(not_in_artworks) > 30:
            print(f"  ... and {len(not_in_artworks) - 30} more")

    print("\n" + "="*60)
    print("SUMMARY:")
    print("="*60)
    print(f"Total images in delete folder: {len(object_ids_to_delete)}")
    print(f"Removed from artworkids.json: {len(removed_from_artworks)}")
    print(f"Deleted JSON metadata files: {len(deleted_json)}")
    print(f"Added NEW to chicdontfetch.json: {new_chic}")
    print(f"Added NEW to metdontfetch.json: {new_met}")
    print(f"Added NEW to rijksdontfetch.json: {new_rijks}")
    print("="*60)

if __name__ == "__main__":
    main()
