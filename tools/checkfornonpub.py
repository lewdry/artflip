import json
import os

# Path to the folder containing JSON files
json_folder = os.path.join(os.path.dirname(__file__), "metadata")

# List to store objectIDs where isPublicDomain is False
non_public_domain_ids = []

# Loop through all files in the metadata folder
for filename in os.listdir(json_folder):
    if filename.endswith(".json"):
        file_path = os.path.join(json_folder, filename)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not data.get("isPublicDomain", True):
                    non_public_domain_ids.append(data.get("objectID"))
        except Exception as e:
            print(f"Error reading {filename}: {e}")

# Save results to a JSON file
output_file = os.path.join(os.path.dirname(__file__), "non_public_domain_ids.json")
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(non_public_domain_ids, f, indent=2)

print(f"Done! {len(non_public_domain_ids)} non-public-domain objects found.")
print(f"Results saved to {output_file}")
