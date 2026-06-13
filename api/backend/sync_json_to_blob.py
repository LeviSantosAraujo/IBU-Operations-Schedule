"""
Sync local JSON files to Vercel Blob storage.
Run this locally to overwrite blob data with the correct local files.
"""
import os
import json
import requests
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

def sync_file(filename, token, store_id):
    """Sync a single JSON file to blob storage using REST API"""
    filepath = DATA_DIR / filename
    if not filepath.exists():
        print(f"Skipping {filename} (not found)")
        return False
    
    with open(filepath, 'r') as f:
        data = f.read()
    
    try:
        url = f"https://blob.vercel-storage.com/{filename}"
        headers = {
            "Authorization": f"Bearer {token}",
            "x-store-id": store_id,
            "x-allow-overwrite": "true",
        }
        response = requests.put(url, data=data.encode('utf-8'), headers=headers)
        if response.status_code in (200, 201):
            print(f"✓ Synced {filename} ({len(data)} bytes)")
            return True
        else:
            print(f"✗ Failed to sync {filename}: HTTP {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"✗ Failed to sync {filename}: {e}")
        return False

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
    
    token = os.getenv("BLOB_READ_WRITE_TOKEN")
    store_id = os.getenv("BLOB_READ_WRITE_TOKEN_STORE_ID")
    
    print("Syncing local JSON files to Vercel Blob storage...")
    print(f"Data directory: {DATA_DIR}")
    print(f"BLOB_READ_WRITE_TOKEN set: {bool(token)}")
    print(f"BLOB_READ_WRITE_TOKEN_STORE_ID: {store_id}")
    print()
    
    success_count = 0
    for filename in json_files:
        if sync_file(filename, token, store_id):
            success_count += 1
    
    print()
    print(f"Synced {success_count}/{len(json_files)} files successfully")

if __name__ == "__main__":
    main()
