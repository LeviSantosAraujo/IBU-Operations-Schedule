"""
Storage module for Excel files - handles blob, local, and in-memory storage
"""
import os
import io
from typing import Optional, Dict
from openpyxl import Workbook, load_workbook

# Global in-memory storage for production
EXCEL_DATA_STORE: Dict[str, bytes] = {}

# Try to import different blob storage implementations
BLOB_STORAGE = None
BLOB_AVAILABLE = False

def _init_vercel_blob():
    """Initialize Vercel Blob storage"""
    global BLOB_STORAGE, BLOB_AVAILABLE
    print(f"[INIT] BLOB_READ_WRITE_TOKEN set: {bool(os.getenv('BLOB_READ_WRITE_TOKEN'))}")
    print(f"[INIT] BLOB_READ_WRITE_TOKEN_STORE_ID: {os.getenv('BLOB_READ_WRITE_TOKEN_STORE_ID')}")
    # Enable blob storage for persistent Excel storage
    if os.getenv("BLOB_READ_WRITE_TOKEN"):
        try:
            import vercel_blob  # noqa: F401
            BLOB_AVAILABLE = True
            print("[INIT] Vercel Blob storage enabled")
            return True
        except Exception as e:
            print(f"[INIT] Failed to initialize Vercel Blob: {e}")
            import traceback
            traceback.print_exc()
            BLOB_AVAILABLE = False
            BLOB_STORAGE = None
    else:
        print("[INIT] BLOB_READ_WRITE_TOKEN not set, using memory storage")
        BLOB_AVAILABLE = False
        BLOB_STORAGE = None
    return False

def blob_put(key: str, data: bytes, store_id: Optional[str] = None) -> bool:
    """Put data to blob storage using REST API for private stores"""
    if not BLOB_AVAILABLE or not os.getenv("BLOB_READ_WRITE_TOKEN"):
        print(f"blob_put: BLOB_AVAILABLE={BLOB_AVAILABLE}, TOKEN_SET={bool(os.getenv('BLOB_READ_WRITE_TOKEN'))}")
        return False

    try:
        import requests
        token = os.getenv("BLOB_READ_WRITE_TOKEN")
        sid = store_id or os.getenv("BLOB_READ_WRITE_TOKEN_STORE_ID")
        
        print(f"blob_put: Using REST API for private store, store_id={sid}")
        
        # Use Vercel Blob REST API with store_id in URL for private stores
        url = f"https://blob.vercel-storage.com/{sid}/{key}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream"
        }
        
        response = requests.put(url, data=data, headers=headers)
        print(f"blob_put: REST API response status={response.status_code}")
        
        if response.status_code in [200, 201]:
            print(f"blob_put: Success via REST API")
            return True
        else:
            print(f"blob_put: REST API error: {response.text}")
            return False
    except Exception as e:
        print(f"Error putting to blob via REST API: {e}")
        import traceback
        traceback.print_exc()
        # Don't let blob errors block operations
        return False

def blob_get(key: str) -> Optional[bytes]:
    """Get data from blob storage by pathname.

    The vercel_blob package has no direct get-by-key, so we list blobs
    filtered by the key prefix, find the exact pathname match, then
    download the content from its public URL.
    """
    if not BLOB_AVAILABLE or not os.getenv("BLOB_READ_WRITE_TOKEN"):
        print(f"blob_get: BLOB_AVAILABLE={BLOB_AVAILABLE}, TOKEN_SET={bool(os.getenv('BLOB_READ_WRITE_TOKEN'))}")
        return None

    try:
        import vercel_blob
        import requests

        print(f"blob_get: Listing blobs with prefix {key}")
        result = vercel_blob.list({"prefix": key})
        blobs = result.get("blobs", []) if isinstance(result, dict) else []
        print(f"blob_get: Found {len(blobs)} blobs with prefix {key}")

        # Find exact pathname match (prefix could match similar names)
        target = None
        for blob in blobs:
            if blob.get("pathname") == key:
                target = blob
                break
        if target is None:
            print(f"blob_get: No exact match for {key}")
            return None

        url = target.get("downloadUrl") or target.get("url")
        if not url:
            print(f"blob_get: No URL found for {key}")
            return None

        print(f"blob_get: Fetching from {url}")
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            print(f"blob_get: Success, got {len(resp.content)} bytes")
            return resp.content
        print(f"blob_get: HTTP {resp.status_code}")
        return None
    except Exception as e:
        print(f"Error getting from blob: {e}")
        import traceback
        traceback.print_exc()
        # Don't let blob errors block operations
        return None

# Initialize blob storage on module load (after functions are defined)
_init_vercel_blob()

def blob_exists(key: str) -> bool:
    """Check if blob exists"""
    if not BLOB_AVAILABLE or not os.getenv("BLOB_READ_WRITE_TOKEN"):
        return False
    
    try:
        data = blob_get(key)
        return data is not None
    except:
        return False

def store_excel_data(data: bytes, filename: str = "ibu_schedule.xlsx") -> bool:
    """Store Excel data using best available method"""
    # Store in memory first (always works)
    EXCEL_DATA_STORE["current"] = data
    
    # Try blob storage
    if blob_put(filename, data):
        return True
    
    # Try local storage
    try:
        from pathlib import Path
        upload_dir = Path(__file__).parent / "uploads"
        upload_dir.mkdir(exist_ok=True)
        upload_path = upload_dir / filename
        with open(upload_path, "wb") as f:
            f.write(data)
        return True
    except:
        pass
    
    # Memory storage is our fallback
    return True

def get_excel_data(filename: str = "ibu_schedule.xlsx") -> Optional[bytes]:
    """Get Excel data from storage"""
    # Try blob first
    data = blob_get(filename)
    if data:
        EXCEL_DATA_STORE["current"] = data  # Cache in memory
        return data

    # Try memory storage
    if "current" in EXCEL_DATA_STORE:
        return EXCEL_DATA_STORE["current"]

    # Try local storage (bundled with deployment)
    try:
        from pathlib import Path
        upload_path = Path(__file__).parent / "uploads" / filename
        if upload_path.exists():
            with open(upload_path, "rb") as f:
                data = f.read()
                EXCEL_DATA_STORE["current"] = data  # Cache it
                return data
    except:
        pass

    return None

def excel_file_exists(filename: str = "ibu_schedule.xlsx") -> bool:
    """Check if Excel file exists in any storage"""
    if blob_exists(filename):
        return True
    
    try:
        from pathlib import Path
        upload_path = Path(__file__).parent / "uploads" / filename
        if upload_path.exists():
            return True
    except:
        pass
    
    return "current" in EXCEL_DATA_STORE

def get_workbook(filename: str = "ibu_schedule.xlsx") -> Optional[Workbook]:
    """Get workbook from storage"""
    data = get_excel_data(filename)
    if data:
        return load_workbook(io.BytesIO(data))
    return None

def save_workbook(wb: Workbook, filename: str = "ibu_schedule.xlsx") -> bool:
    """Save workbook to storage"""
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return store_excel_data(buffer.read(), filename)

# Initialize on import
_init_vercel_blob()
