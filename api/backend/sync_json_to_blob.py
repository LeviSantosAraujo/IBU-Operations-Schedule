"""
Sync local JSON files to Vercel Blob storage.
Run this locally to overwrite blob data with the correct local files.
"""
import os
import json
from pathlib import Path

# Add backend to path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from storage import blob_put

DATA_DIR = Path(__file__).parent / "data"

def sync_file(filename, store_id):
    """Sync a single JSON file to blob storage"""
    filepath = DATA_DIR / filename
    if not filepath.exists():
        print(f"Skipping {filename} (not found)")
        return False
    
    with open(filepath, 'r') as f:
        data = f.read()
    
    success = blob_put(filename, data.encode('utf-8'), store_id)
    if success:
        print(f"✓ Synced {filename} ({len(data)} bytes)")
    else:
        print(f"✗ Failed to sync {filename}")
    return success

def main():
    """Sync all JSON data files to blob storage"""
    json_files = [
        "employees.json",
        "availabilities.json",
        "schedules.json",
        "config.json",
        "passwords.json",
        "availability_requests.json",
        "events.json",
        "coverage_requirements.json",
        "notifications.json",
    ]
    
    store_id = os.getenv("BLOB_READ_WRITE_TOKEN_STORE_ID")
    
    print("Syncing local JSON files to Vercel Blob storage...")
    print(f"Data directory: {DATA_DIR}")
    print(f"BLOB_READ_WRITE_TOKEN set: {bool(os.getenv('BLOB_READ_WRITE_TOKEN'))}")
    print(f"BLOB_READ_WRITE_TOKEN_STORE_ID: {store_id}")
    print()
    
    success_count = 0
    for filename in json_files:
        if sync_file(filename, store_id):
            success_count += 1
    
    print()
    print(f"Synced {success_count}/{len(json_files)} files successfully")

if __name__ == "__main__":
    main()
