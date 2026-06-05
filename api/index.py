from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

# Initialize blob storage before importing main
if os.getenv("BLOB_READ_WRITE_TOKEN"):
    from excel_store import set_blob_key
    set_blob_key("ibu_schedule.xlsx")

from main import app

# Configure CORS for Vercel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Export for Vercel serverless function
# FastAPI app is automatically handled by Vercel Python runtime
