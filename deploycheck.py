import json
import os

print("🔍 Validating artwork files...\n")

# Load object IDs
print("Loading object_ids.json...")
with open('object_ids.json', 'r') as f:
    object_ids = json.load(f)

print(f"Found {len(object_ids)} object IDs to validate\n")

# Track issues
missing_json = []
missing_images = []
invalid_json = []
missing_fields = []

# Required fields in each JSON
required_fields = ['objectID', 'title', 'localImage', 'isPublicDomain', 'objectURL']

print("Checking files...")
for i, obj_id in enumerate(object_ids):
    # Progress indicator
    if (i + 1) % 100 == 0:
        print(f"  Checked {i + 1}/{len(object_ids)}...")
    
    # Check JSON file exists
    json_path = f"public/metadata/{obj_id}.json"
    if not os.path.exists(json_path):
        missing_json.append(obj_id)
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
        
        # Check image file exists
        if 'localImage' in data and data['localImage']:
            image_path = f"public/images/{data['localImage']}"
            if not os.path.exists(image_path):
                missing_images.append({
                    'objectID': obj_id,
                    'filename': data['localImage']
                })
    
    except json.JSONDecodeError:
        invalid_json.append(obj_id)
    except Exception as e:
        print(f"  ⚠️  Error processing {obj_id}: {e}")

# Print results
print(f"\n{'='*60}")
print("VALIDATION RESULTS")
print(f"{'='*60}\n")

if not missing_json and not missing_images and not invalid_json and not missing_fields:
    print("✅ ALL CHECKS PASSED!")
    print(f"   - {len(object_ids)} JSON files validated")
    print(f"   - {len(object_ids)} image files found")
    print(f"   - All required fields present")
else:
    if missing_json:
        print(f"❌ Missing JSON files: {len(missing_json)}")
        print(f"   First 10: {missing_json[:10]}")
    
    if invalid_json:
        print(f"\n❌ Invalid JSON files: {len(invalid_json)}")
        print(f"   Object IDs: {invalid_json[:10]}")
    
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

print(f"\n{'='*60}")
print(f"Total validated: {len(object_ids)}")
print(f"Issues found: {len(missing_json) + len(invalid_json) + len(missing_fields) + len(missing_images)}")
print(f"{'='*60}\n")

if missing_json or missing_images or invalid_json or missing_fields:
    print("⚠️  Fix issues before deploying!")
else:
    print("🚀 Ready to deploy!")