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

# Initialize blob storage on module load
_init_vercel_blob()

def _init_vercel_blob():
    """Initialize Vercel Blob storage"""
    global BLOB_STORAGE, BLOB_AVAILABLE
    # Enable blob storage for persistent Excel storage
    if os.getenv("BLOB_READ_WRITE_TOKEN"):
        try:
            from vercel_blob import put, get
            BLOB_AVAILABLE = True
            print("Vercel Blob storage enabled")
            return True
        except Exception as e:
            print(f"Failed to initialize Vercel Blob: {e}")
            BLOB_AVAILABLE = False
            BLOB_STORAGE = None
    else:
        print("BLOB_READ_WRITE_TOKEN not set, using memory storage")
        BLOB_AVAILABLE = False
        BLOB_STORAGE = None
    return False

def blob_put(key: str, data: bytes) -> bool:
    """Put data to blob storage"""
    if not BLOB_AVAILABLE or not os.getenv("BLOB_READ_WRITE_TOKEN"):
        return False

    try:
        from vercel_blob import put
        put(key, data, { "addRandomSuffix": "false" })
        return True
    except Exception as e:
        print(f"Error putting to blob: {e}")
        # Don't let blob errors block operations
        return False

def blob_get(key: str) -> Optional[bytes]:
    """Get data from blob storage"""
    if not BLOB_AVAILABLE or not os.getenv("BLOB_READ_WRITE_TOKEN"):
        return None

    try:
        from vercel_blob import get
        return get(key)
    except Exception as e:
        print(f"Error getting from blob: {e}")
        # Don't let blob errors block operations
        return None

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
