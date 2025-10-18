#!/usr/bin/env python3
"""
Script to capitalize the first letter of the 'medium' field in all JSON metadata files.
"""

import json
import os
from pathlib import Path

def capitalize_medium_value(medium_value):
    """Capitalize the first letter of the medium value."""
    if not medium_value or not isinstance(medium_value, str):
        return medium_value
    return medium_value[0].upper() + medium_value[1:] if medium_value else medium_value

def process_json_file(filepath):
    """Process a single JSON file to capitalize the medium field."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Check if medium field exists and needs updating
        if 'medium' in data and isinstance(data['medium'], str):
            original = data['medium']
            updated = capitalize_medium_value(original)
            
            if original != updated:
                data['medium'] = updated
                
                # Write back to file
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                return True, original, updated
        
        return False, None, None
    
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False, None, None

def main():
    """Main function to process all JSON files in metadata directories."""
    script_dir = Path(__file__).parent.parent
    
    # Process both metadata directories
    metadata_dirs = [
        script_dir / 'scripts' / 'metadata',
        script_dir / 'public' / 'metadata'
    ]
    
    total_updated = 0
    total_files = 0
    
    for metadata_dir in metadata_dirs:
        if not metadata_dir.exists():
            print(f"Directory not found: {metadata_dir}")
            continue
        
        print(f"\nProcessing directory: {metadata_dir}")
        
        # Process all JSON files in the directory
        for json_file in metadata_dir.glob('*.json'):
            total_files += 1
            updated, original, new = process_json_file(json_file)
            
            if updated:
                total_updated += 1
                print(f"Updated {json_file.name}: '{original}' -> '{new}'")
    
    print(f"\n{'='*60}")
    print(f"Total files processed: {total_files}")
    print(f"Total files updated: {total_updated}")
    print(f"{'='*60}")

if __name__ == '__main__':
    main()
