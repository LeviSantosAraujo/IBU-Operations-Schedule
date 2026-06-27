"""
Utility functions for the IBU Operations Schedule API.

These are pure helper functions that don't depend on any specific data storage layer.
"""

import hashlib
from typing import Optional


def hash_password(password: str) -> str:
    """Hash password using SHA-256 (first 16 chars for storage).

    Simple hash for demo - use bcrypt in production.
    """
    return hashlib.sha256(password.encode()).hexdigest()[:16]


def get_location_color(location: Optional[str]) -> Optional[str]:
    """Get color code for a location.

    2nd Floor → green (#90EE90)
    Ground Floor → grey (#D3D3D3)
    6th Floor → blue (#87CEEB)
    Working from Home → red (#FF6B6B)
    80 Bloor → purple (#DDA0DD)
    Call Center → orange (#FFB347)
    Other → None (use Excel cell color)
    """
    if not location:
        return None

    location_lower = location.lower()

    if '2nd floor' in location_lower or 'f2' in location_lower:
        return '#90EE90'  # Light green
    elif 'ground floor' in location_lower or 'ground' in location_lower or 'gf' in location_lower or 'gr' in location_lower:
        return '#D3D3D3'  # Light grey
    elif '6th floor' in location_lower or 'f6' in location_lower:
        return '#87CEEB'  # Sky blue
    elif 'working from home' in location_lower or 'wfh' in location_lower:
        return '#FF6B6B'  # Light red
    elif '80 bloor' in location_lower or 'bloor' in location_lower:
        return '#DDA0DD'  # Plum purple
    elif 'call center' in location_lower or 'cc' in location_lower:
        return '#FFB347'  # Light orange

    return None
