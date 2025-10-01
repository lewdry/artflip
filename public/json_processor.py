import json
import os
import glob
from datetime import datetime

# --- Configuration ---
# Set the directory where your JSON files are located. 
# 
# SCENARIO 1 (Recommended): If the script is placed directly inside the folder 
# with your 2000 JSON files, set this to '.':
# JSON_DIRECTORY = '.' 
#
# SCENARIO 2: If the JSON files are in a subdirectory named 'metadata':
JSON_DIRECTORY = './metadata'
#
LOG_FILE = 'processing_log.txt'
PREFIX_TO_ADD = "Metropolitan Museum of Art. "
# ---------------------


def prepend_credit_line(file_path: str, prefix: str) -> dict:
    """
    Reads a single JSON file, prepends the required prefix to the 'creditLine' 
    field, and overwrites the original file.
    
    Returns a dictionary containing the status and a detailed message.
    """
    filename = os.path.basename(file_path)
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        # 1. Read the JSON file
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
    except FileNotFoundError:
        return {
            "time": timestamp,
            "status": "ERROR",
            "file": filename,
            "message": "File not found."
        }
    except json.JSONDecodeError:
        return {
            "time": timestamp,
            "status": "ERROR",
            "file": filename,
            "message": "Failed to decode JSON (File contents are invalid)."
        }
    except Exception as e:
        return {
            "time": timestamp,
            "status": "ERROR",
            "file": filename,
            "message": f"Unexpected error during read: {e}"
        }

    # 2. Modify the 'creditLine' field
    if 'creditLine' in data and isinstance(data['creditLine'], str):
        current_credit_line = data['creditLine'].strip()
        
        # Safety check: prevent double-prepending
        if current_credit_line.startswith(prefix):
            return {
                "time": timestamp,
                "status": "SKIP",
                "file": filename,
                "message": "Credit line already contains the prefix. No change made."
            }
        
        data['creditLine'] = prefix + current_credit_line
        
        # 3. Write the modified data back
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                # Use indent=2 for human-readable output, ensure_ascii=False for proper characters
                json.dump(data, f, indent=2, ensure_ascii=False)
                
            return {
                "time": timestamp,
                "status": "SUCCESS",
                "file": filename,
                "message": "Credit line successfully updated."
            }
            
        except Exception as e:
            return {
                "time": timestamp,
                "status": "ERROR",
                "file": filename,
                "message": f"Unexpected error during write: {e}"
            }
    else:
        return {
            "time": timestamp,
            "status": "FAIL",
            "file": filename,
            "message": "Credit line key not found or is not a string."
        }


def process_all_files(directory_path: str, log_file_path: str, prefix: str):
    """
    Main function to find all JSON files and process them, writing results to a log file.
    """
    # Use glob to find all files ending in .json in the specified directory
    search_pattern = os.path.join(directory_path, '*.json')
    json_files = glob.glob(search_pattern)
    
    if not json_files:
        print(f"--- No JSON files found in directory: {directory_path} ---")
        return

    print(f"--- Found {len(json_files)} JSON files. Starting processing... ---")
    
    # Open the log file once for writing all results
    with open(log_file_path, 'w', encoding='utf-8') as log_f:
        log_f.write(f"--- JSON Processing Log Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        log_f.write("Time | Status | File Name | Message\n")
        log_f.write("------------------------------------------------------------------------\n")
        
        for i, file_path in enumerate(json_files, 1):
            # Process the file and get the result dictionary
            result = prepend_credit_line(file_path, prefix)
            
            # Format the log line
            log_line = f"{result['time']} | {result['status']:<6} | {result['file']:<30} | {result['message']}\n"
            
            # Write to the log file
            log_f.write(log_line)
            
            # Provide console feedback every 100 files
            if i % 100 == 0 or i == len(json_files):
                print(f"Processed {i}/{len(json_files)} files. Last status: {result['status']}")

    print(f"--- Processing complete. Total files: {len(json_files)} ---")
    print(f"Detailed log written to: {os.path.abspath(log_file_path)}")


if __name__ == "__main__":
    # Ensure the directory exists before starting
    if not os.path.isdir(JSON_DIRECTORY):
        print(f"FATAL ERROR: The specified directory '{JSON_DIRECTORY}' does not exist.")
        print("Please update the 'JSON_DIRECTORY' variable at the top of the script.")
    else:
        process_all_files(JSON_DIRECTORY, LOG_FILE, PREFIX_TO_ADD)
