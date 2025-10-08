import json
from pathlib import Path
from collections import Counter

# Folder containing your JSON files
JSON_FOLDER = Path('../public/metadata/')  # current folder, change if needed

# Known institution prefixes
INSTITUTIONS = [
    "Metropolitan Museum of Art",
    "Rijksmuseum",
    "Art Institute of Chicago"
]

# Counter to store totals
totals = Counter()

# List to store unrecognized files
unrecognized_files = []

# Loop through all JSON files in the folder
for json_file in JSON_FOLDER.glob('*.json'):
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            credit = data.get('creditLine', '')
            matched = False
            for inst in INSTITUTIONS:
                if credit.startswith(inst):
                    totals[inst] += 1
                    matched = True
                    break
            if not matched:
                unrecognized_files.append(json_file.name)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Skipping {json_file}: {e}")

# Print totals
print("Totals:")
for institution, count in totals.most_common():
    print(f"{institution} {count}")

# Print unrecognized files
if unrecognized_files:
    print("\nFiles with unrecognized creditLine prefixes:")
    for filename in unrecognized_files:
        print(filename)
