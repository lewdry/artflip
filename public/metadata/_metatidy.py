import json
import os
from pathlib import Path
from datetime import datetime

def capitalize_first_letter(text):
    """Capitalize only the first letter of a string."""
    if not text or not isinstance(text, str):
        return text
    return text[0].upper() + text[1:] if len(text) > 0 else text

def clean_json_file(file_path, log_file):
    """Clean a single JSON file according to specified rules."""
    try:
        # Read the JSON file
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        changes = []
        file_name = os.path.basename(file_path)
        
        # Rule 1: Clean title - remove \n and everything after it
        if 'title' in data and isinstance(data['title'], str):
            original_title = data['title']
            if '\n' in original_title:
                data['title'] = original_title.split('\n')[0]
                changes.append(f"  - Cleaned title: '{original_title}' → '{data['title']}'")
        
        # Also clean artistDisplayName of \n
        if 'artistDisplayName' in data and isinstance(data['artistDisplayName'], str):
            original_artist = data['artistDisplayName']
            if '\n' in original_artist:
                data['artistDisplayName'] = original_artist.split('\n')[0]
                changes.append(f"  - Cleaned artistDisplayName: '{original_artist}' → '{data['artistDisplayName']}'")
        
        # Rule 2: Delete unwanted fields
        fields_to_delete = ['artistDisplayBio', 'title_source']
        for field in fields_to_delete:
            if field in data:
                changes.append(f"  - Deleted field: '{field}'")
                del data[field]
        
        # Rule 3: Capitalize first letter of specified fields
        fields_to_capitalize = ['title', 'artistDisplayName', 'objectName', 'medium', 'culture', 'dynasty', 'period']
        
        for field in fields_to_capitalize:
            if field in data and isinstance(data[field], str) and data[field]:
                original_value = data[field]
                new_value = capitalize_first_letter(original_value)
                if original_value != new_value:
                    data[field] = new_value
                    changes.append(f"  - Capitalized {field}: '{original_value}' → '{new_value}'")
        
        # Write the cleaned data back to the file
        if changes:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Log the changes
            log_file.write(f"\n{file_name}:\n")
            for change in changes:
                log_file.write(f"{change}\n")
            
            return True, len(changes)
        
        return False, 0
    
    except Exception as e:
        log_file.write(f"\nERROR processing {file_name}: {str(e)}\n")
        return False, 0

def main():
    # Configuration
    json_directory = input("Enter the directory path containing JSON files (or press Enter for current directory): ").strip()
    if not json_directory:
        json_directory = "."
    
    json_directory = Path(json_directory)
    
    if not json_directory.exists():
        print(f"Error: Directory '{json_directory}' does not exist.")
        return
    
    # Create log file
    log_filename = f"metadata_cleanup_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    print(f"\nStarting metadata cleanup...")
    print(f"Directory: {json_directory}")
    print(f"Log file: {log_filename}\n")
    
    # Find all JSON files
    json_files = list(json_directory.glob("*.json"))
    
    if not json_files:
        print("No JSON files found in the directory.")
        return
    
    print(f"Found {len(json_files)} JSON files.")
    
    # Process files
    files_modified = 0
    total_changes = 0
    
    with open(log_filename, 'w', encoding='utf-8') as log_file:
        log_file.write(f"Metadata Cleanup Log\n")
        log_file.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_file.write(f"Directory: {json_directory}\n")
        log_file.write(f"=" * 80 + "\n")
        
        for i, json_file in enumerate(json_files, 1):
            modified, change_count = clean_json_file(json_file, log_file)
            if modified:
                files_modified += 1
                total_changes += change_count
            
            # Progress indicator
            if i % 100 == 0:
                print(f"Processed {i}/{len(json_files)} files...")
        
        # Write summary
        log_file.write(f"\n{'=' * 80}\n")
        log_file.write(f"SUMMARY\n")
        log_file.write(f"Total files processed: {len(json_files)}\n")
        log_file.write(f"Files modified: {files_modified}\n")
        log_file.write(f"Total changes made: {total_changes}\n")
        log_file.write(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Print summary
    print(f"\n{'=' * 60}")
    print(f"Cleanup complete!")
    print(f"Total files processed: {len(json_files)}")
    print(f"Files modified: {files_modified}")
    print(f"Total changes made: {total_changes}")
    print(f"Log file created: {log_filename}")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()