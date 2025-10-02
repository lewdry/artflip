import json
import os

print("🔍 Validating artwork files...\n")

# Load object IDs
print("Loading artworkids.json...")
with open('artworkids.json', 'r') as f:
    object_ids = json.load(f)

print(f"Found {len(object_ids)} object IDs to validate\n")

# Track issues
missing_json = []
missing_images = []
invalid_json = []
missing_fields = []
# NEW: List to store paths of all errored files
errored_files = []

# Required fields in each JSON
required_fields = ['objectID', 'title', 'localImage', 'isPublicDomain', 'objectURL']

print("Checking files...")
for i, obj_id in enumerate(object_ids):
    # Progress indicator
    if (i + 1) % 100 == 0:
        print(f"  Checked {i + 1}/{len(object_ids)}...")
    
    errored_in_this_loop = False # Flag to prevent adding the same JSON file multiple times for different errors
    
    # Check JSON file exists
    json_path = f"public/metadata/{obj_id}.json"
    if not os.path.exists(json_path):
        missing_json.append(obj_id)
        errored_files.append(json_path) # Add missing JSON path
        errored_in_this_loop = True
        continue
    
    # Check JSON is valid and has required fields
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Check required fields
        for field in required_fields:
            if field not in data or data[field] is None or data[field] == '':
                missing_fields.append({
                    'objectID': obj_id,
                    'field': field
                })
                if not errored_in_this_loop:
                    errored_files.append(json_path)
                    errored_in_this_loop = True
        
        # Check image file exists
        if 'localImage' in data and data['localImage']:
            image_filename = data['localImage']
            image_path = f"public/images/{image_filename}"
            if not os.path.exists(image_path):
                missing_images.append({
                    'objectID': obj_id,
                    'filename': image_filename
                })
                errored_files.append(image_path) # Add missing image path
    
    except json.JSONDecodeError:
        invalid_json.append(obj_id)
        if not errored_in_this_loop:
            errored_files.append(json_path)
            errored_in_this_loop = True
    except Exception as e:
        print(f"  ⚠️  Error processing {obj_id}: {e}")
        if not errored_in_this_loop:
            errored_files.append(json_path)
            errored_in_this_loop = True

# Get unique and sorted list of errored files
unique_errored_files = sorted(list(set(errored_files)))

# Print results
print(f"\n{'='*60}")
print("VALIDATION RESULTS")
print(f"{'='*60}\n")

total_issues = len(missing_json) + len(invalid_json) + len(missing_fields) + len(missing_images)

if total_issues == 0:
    print("✅ ALL CHECKS PASSED!")
    print(f"   - {len(object_ids)} JSON files validated")
    print(f"   - All image files found") 
    print(f"   - All required fields present")
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

# ---------------------------------------------
## 📝 Errored File List & Log
# ---------------------------------------------

log_filename = 'errored_files_log.txt'
print(f"\nWriting errored file paths to {log_filename}...")

if unique_errored_files:
    # Print list to console
    print(f"\n**Total unique errored files (paths):** **{len(unique_errored_files)}**")
    for path in unique_errored_files[:20]: # Print first 20 to console
        print(f" - {path}")
    if len(unique_errored_files) > 20:
        print(f" - ...and {len(unique_errored_files) - 20} more. See log file for full list.")
        
    # Save full list to log file
    try:
        with open(log_filename, 'w', encoding='utf-8') as log_f:
            log_f.write(f"--- Errored File Paths ({len(unique_errored_files)} total) ---\n")
            log_f.write('\n'.join(unique_errored_files))
        print(f"\n✅ Successfully saved {len(unique_errored_files)} paths to {log_filename}.")
    except Exception as e:
        print(f"\n❌ Failed to save log file: {e}")
else:
    print("No errored files found. Log file will not be created.")


print(f"\n{'='*60}")
print(f"Total validated: {len(object_ids)}")
print(f"Issues found (events): {total_issues}")
print(f"{'='*60}\n")

if total_issues > 0:
    print("⚠️  Fix issues before deploying!")
else:
    print("🚀 Ready to deploy!")