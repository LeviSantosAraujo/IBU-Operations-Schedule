"""
Vercel Blob storage configuration and utilities
"""
import os
import io
from typing import Optional, Any
from openpyxl import Workbook

# Try to import different blob storage implementations
BLOB_STORAGE = None
BLOB_AVAILABLE = False

def _init_vercel_blob():
    """Initialize Vercel Blob storage"""
    global BLOB_STORAGE, BLOB_AVAILABLE
    try:
        # Try the newer API first
        import vercel_blob
        BLOB_STORAGE = vercel_blob
        BLOB_AVAILABLE = True
        print("Using Vercel Blob (new API)")
        return True
    except ImportError:
        pass
    
    try:
        # Try the older API
        from vercel_blob import BlobClient
        BLOB_STORAGE = BlobClient
        BLOB_AVAILABLE = True
        print("Using Vercel Blob (BlobClient API)")
        return True
    except ImportError:
        pass
    
    print("Vercel Blob not available")
    return False

def blob_put(key: str, data: bytes) -> bool:
    """Put data to blob storage"""
    if not BLOB_AVAILABLE or not os.getenv("BLOB_READ_WRITE_TOKEN"):
        return False
    
    try:
        if hasattr(BLOB_STORAGE, 'put'):
            # New API
            BLOB_STORAGE.put(key, data)
            return True
        elif hasattr(BLOB_STORAGE, 'from_env'):
            # Old API
            client = BLOB_STORAGE.from_env()
            client.put(key, data)
            return True
    except Exception as e:
        print(f"Error putting to blob: {e}")
    return False

def blob_get(key: str) -> Optional[bytes]:
    """Get data from blob storage"""
    if not BLOB_AVAILABLE or not os.getenv("BLOB_READ_WRITE_TOKEN"):
        return None
    
    try:
        if hasattr(BLOB_STORAGE, 'download_file'):
            # New API
            return BLOB_STORAGE.download_file(key)
        elif hasattr(BLOB_STORAGE, 'from_env'):
            # Old API
            client = BLOB_STORAGE.from_env()
            return client.get(key)
    except Exception as e:
        print(f"Error getting from blob: {e}")
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

# Initialize on import
_init_vercel_blob()
