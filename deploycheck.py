import json
import os

print("🔍 Validating artwork files...\n")

# ------------------------------------------------
# Load object IDs
# ------------------------------------------------
print("Loading artworkids.json...")
with open('artworkids.json', 'r') as f:
    object_ids = json.load(f)

object_ids = [str(x).strip() for x in object_ids]
print(f"Found {len(object_ids)} object IDs to validate\n")

# ------------------------------------------------
# Track issues
# ------------------------------------------------
missing_json = []
missing_images = []
invalid_json = []
missing_fields = []
errored_files = []

# For reverse-checks
all_json_files = []
all_image_files = []
used_image_files = []

required_fields = ['objectID', 'title', 'localImage', 'isPublicDomain', 'objectURL']

# ------------------------------------------------
# Validation loop
# ------------------------------------------------
print("Checking files...")
for i, obj_id in enumerate(object_ids):
    if (i + 1) % 100 == 0:
        print(f"  Checked {i + 1}/{len(object_ids)}...")

    errored_in_this_loop = False
    json_path = f"public/metadata/{obj_id}.json"

    # Record all known metadata file paths for later comparison
    if os.path.exists(json_path):
        all_json_files.append(json_path)

    if not os.path.exists(json_path):
        missing_json.append(obj_id)
        errored_files.append(json_path)
        continue

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Check required fields
        for field in required_fields:
            if field not in data or data[field] in (None, ''):
                missing_fields.append({'objectID': obj_id, 'field': field})
                if not errored_in_this_loop:
                    errored_files.append(json_path)
                    errored_in_this_loop = True

        # Check image file exists
        if 'localImage' in data and data['localImage']:
            image_filename = data['localImage']
            image_path = f"public/images/{image_filename}"
            used_image_files.append(image_path)

            if not os.path.exists(image_path):
                missing_images.append({'objectID': obj_id, 'filename': image_filename})
                errored_files.append(image_path)

    except json.JSONDecodeError:
        invalid_json.append(obj_id)
        if not errored_in_this_loop:
            errored_files.append(json_path)
    except Exception as e:
        print(f"  ⚠️  Error processing {obj_id}: {e}")
        if not errored_in_this_loop:
            errored_files.append(json_path)

# ------------------------------------------------
# Reverse Checks: Find extra metadata/images
# ------------------------------------------------
print("\n🔄 Checking for extra files not listed in artworkids.json...")

metadata_dir = "public/metadata"
images_dir = "public/images"

all_metadata_files = [
    f for f in os.listdir(metadata_dir)
    if f.endswith(".json")
]
all_image_files = [
    f for f in os.listdir(images_dir)
    if not f.startswith('.')  # ignore .DS_Store etc.
]

extra_metadata = [
    f for f in all_metadata_files
    if f.replace(".json", "") not in object_ids
]

used_image_names = [os.path.basename(p) for p in used_image_files]
extra_images = [
    f for f in all_image_files
    if f not in used_image_names
]

# ------------------------------------------------
# Print validation summary
# ------------------------------------------------
print(f"\n{'='*60}")
print("VALIDATION RESULTS")
print(f"{'='*60}\n")

total_issues = len(missing_json) + len(invalid_json) + len(missing_fields) + len(missing_images)

if total_issues == 0:
    print("✅ ALL REQUIRED CHECKS PASSED!")
else:
    if missing_json:
        print(f"❌ Missing JSON files: {len(missing_json)}")
        print(f"   First 10 object IDs: {missing_json[:10]}")

    if invalid_json:
        print(f"\n❌ Invalid JSON files (decode error): {len(invalid_json)}")
        print(f"   First 10 object IDs: {invalid_json[:10]}")

    if missing_fields:
        print(f"\n❌ Missing required fields: {len(missing_fields)}")
        print(f"   First 10 issues:")
        for issue in missing_fields[:10]:
            print(f"   - Object {issue['objectID']}: missing '{issue['field']}'")

    if missing_images:
        print(f"\n❌ Missing image files: {len(missing_images)}")
        print(f"   First 10:")
        for issue in missing_images[:10]:
            print(f"   - Object {issue['objectID']}: {issue['filename']}")

# ------------------------------------------------
# Warnings: Extra files not referenced
# ------------------------------------------------
if extra_metadata or extra_images:
    print(f"\n⚠️  WARNING: Unreferenced files found (these won’t block deploy):")

    if extra_metadata:
        print(f"   🗂️  Extra metadata JSONs: {len(extra_metadata)}")
        for f in extra_metadata[:10]:
            print(f"   - {f}")
        if len(extra_metadata) > 10:
            print(f"   - ...and {len(extra_metadata) - 10} more")

    if extra_images:
        print(f"\n   🖼️  Extra image files: {len(extra_images)}")
        for f in extra_images[:10]:
            print(f"   - {f}")
        if len(extra_images) > 10:
            print(f"   - ...and {len(extra_images) - 10} more")

    # ------------------------------------------------
    # Optional cleanup: move extras to trash/
    # ------------------------------------------------
    move_to_trash = input("\n🗑️  Move unreferenced files to trash/? (y/N): ").strip().lower()
    if move_to_trash == 'y':
        trash_metadata_dir = "trash/metadata"
        trash_images_dir = "trash/images"
        os.makedirs(trash_metadata_dir, exist_ok=True)
        os.makedirs(trash_images_dir, exist_ok=True)

        moved_metadata, moved_images = 0, 0

        # Move metadata
        for f in extra_metadata:
            src = os.path.join(metadata_dir, f)
            dest = os.path.join(trash_metadata_dir, f)
            try:
                os.rename(src, dest)
                moved_metadata += 1
            except Exception as e:
                print(f"   ⚠️ Failed to move {f}: {e}")

        # Move images
        for f in extra_images:
            src = os.path.join(images_dir, f)
            dest = os.path.join(trash_images_dir, f)
            try:
                os.rename(src, dest)
                moved_images += 1
            except Exception as e:
                print(f"   ⚠️ Failed to move {f}: {e}")

        print(f"\n✅ Moved {moved_metadata} metadata and {moved_images} images to trash/")
    else:
        print("\nSkipped moving unreferenced files.")

# ------------------------------------------------
# Log errored files
# ------------------------------------------------
log_filename = 'errored_files_log.txt'
print(f"\nWriting errored file paths to {log_filename}...")

unique_errored_files = sorted(set(errored_files))
if unique_errored_files:
    try:
        with open(log_filename, 'w', encoding='utf-8') as log_f:
            log_f.write(f"--- Errored File Paths ({len(unique_errored_files)} total) ---\n")
            log_f.write('\n'.join(unique_errored_files))
        print(f"✅ Saved {len(unique_errored_files)} paths to {log_filename}.")
    except Exception as e:
        print(f"❌ Failed to save log file: {e}")
else:
    print("No errored files found. Log file will not be created.")

# ------------------------------------------------
# Final Summary
# ------------------------------------------------
print(f"\n{'='*60}")
print(f"Total validated: {len(object_ids)}")
print(f"Issues found (errors): {total_issues}")
print(f"Extra metadata files: {len(extra_metadata)}")
print(f"Extra image files: {len(extra_images)}")
print(f"{'='*60}\n")

if total_issues > 0:
    print("⚠️  Fix issues before deploying!")
else:
    print("🚀 Ready to deploy! (with warnings if above)")
