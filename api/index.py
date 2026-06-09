import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

# Blob token configured in Vercel environment variables
from main import app

