import os
import sys
import traceback

# Backend modules live alongside this file in api/backend so the whole
# package is bundled into the serverless function automatically.
backend_path = os.path.join(os.path.dirname(__file__), "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

# Point Excel storage at Vercel Blob when the token is configured.
if os.getenv("BLOB_READ_WRITE_TOKEN"):
    from excel_store import set_blob_key
    set_blob_key("ibu_schedule.xlsx")

from main import app

# Vercel's Python runtime detects the ASGI application named `app`.
