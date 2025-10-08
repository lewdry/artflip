import os
import json
import glob

def rename_key_in_json_files(directory_path, old_key, new_key):
    """
    Reads all JSON files in a directory, renames a specific key, and
    overwrites the original file with the updated content.

    Args:
        directory_path (str): The path to the directory containing the JSON files.
        old_key (str): The key to be renamed (e.g., 'objectNumber').
        new_key (str): The new name for the key (e.g., 'objectID').
    """
    # Use glob to find all files ending with .json
    json_files = glob.glob(os.path.join(directory_path, '*.json'))
    
    # Counter for tracking changes
    changes_made = 0
    
    print(f"Starting key renaming in directory: {directory_path}")
    print(f"Targeting files: {len(json_files)} found.")

    for filepath in json_files:
        try:
            # 1. Read the JSON file
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 2. Check if the old key exists and rename it
            if old_key in data:
                # Assign the value of the old key to the new key
                data[new_key] = data.pop(old_key) 
                
                # 3. Write the updated data back to the same file
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4) # Use indent for readability
                
                print(f"✅ Successfully updated: {os.path.basename(filepath)}")
                changes_made += 1
            else:
                print(f"🗄️ Key '{old_key}' not found in: {os.path.basename(filepath)}")

        except json.JSONDecodeError:
            print(f"❌ Error: Could not decode JSON in file: {os.path.basename(filepath)}")
        except Exception as e:
            print(f"❌ An unexpected error occurred with file {os.path.basename(filepath)}: {e}")

    print("-" * 30)
    print(f"Processing complete. {changes_made} files were updated.")

# --- Configuration ---
# Set the directory where your 100 JSON files are located.
# Replace '.' with the actual path if the script is not in the same directory
# as your JSON files (e.g., '/path/to/your/json/files').
TARGET_DIRECTORY = '.' 
OLD_KEY_NAME = "objectNumber"
NEW_KEY_NAME = "objectID"

# Run the function
if __name__ == "__main__":
    rename_key_in_json_files(TARGET_DIRECTORY, OLD_KEY_NAME, NEW_KEY_NAME)