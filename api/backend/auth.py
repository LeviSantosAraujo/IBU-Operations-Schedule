from typing import Optional, Dict, Callable
from datetime import datetime, timedelta
from fastapi import HTTPException, Header
import secrets
import base64
import json
import os

# JWT-based authentication (stateless, works with Vercel serverless)
class AuthManager:
    SESSION_DURATION_HOURS = 24
    JWT_SECRET = os.getenv("JWT_SECRET", "ibu-schedule-secret-key-change-in-production")

    @staticmethod
    def _encode_jwt(payload: Dict) -> str:
        """Simple JWT-like encoding (base64) - for production use proper JWT library"""
        payload_str = json.dumps(payload)
        encoded = base64.b64encode(payload_str.encode()).decode()
        return encoded

    @staticmethod
    def _decode_jwt(token: str) -> Optional[Dict]:
        """Simple JWT-like decoding"""
        try:
            decoded = base64.b64decode(token).decode()
            return json.loads(decoded)
        except:
            return None

    @staticmethod
    def login(employee_id: str, password: Optional[str] = None, get_employee_func: Optional[Callable] = None) -> str:
        """Create a JWT token for an employee"""
        # Use Excel-based employee lookup for all users
        if get_employee_func:
            employee = get_employee_func(employee_id)
        else:
            raise HTTPException(status_code=500, detail="Employee lookup function not provided")

        if not employee:
            raise HTTPException(status_code=401, detail="Invalid employee")

        # Create JWT payload
        payload = {
            "employee_id": employee_id,
            "employee_name": employee.name,
            "role": employee.employee_type,
            "expires": (datetime.now() + timedelta(hours=AuthManager.SESSION_DURATION_HOURS)).isoformat()
        }

        # Encode as token
        token = AuthManager._encode_jwt(payload)

        return token

    @staticmethod
    def logout(token: str):
        """JWT tokens are stateless - no server-side logout needed"""
        # Client should simply discard the token
        pass

    @staticmethod
    def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[Dict]:
        """Get current user from JWT token"""
        if not authorization or not authorization.startswith("Bearer "):
            return None

        token = authorization.replace("Bearer ", "")
        payload = AuthManager._decode_jwt(token)

        if not payload:
            return None

        # Check expiration
        expires = datetime.fromisoformat(payload["expires"])
        if datetime.now() > expires:
            return None

        return payload

    @staticmethod
    def require_auth(authorization: Optional[str] = Header(None)) -> Dict:
        """Require authentication, raise 401 if not logged in"""
        user = AuthManager.get_current_user(authorization)
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return user

    @staticmethod
    def require_manager(authorization: Optional[str] = Header(None)) -> Dict:
        """Require manager or admin role, raise 403 if not manager/admin"""
        user = AuthManager.require_auth(authorization)
        if user["role"] not in ["manager", "admin"]:
            raise HTTPException(status_code=403, detail="Manager access required")
        return user

    @staticmethod
    def can_edit_employee(authorization: Optional[str], target_employee_id: str) -> bool:
        """Check if user can edit/view an employee's data"""
        user = AuthManager.get_current_user(authorization)
        if not user:
            return False

        # Managers and admins can edit anyone
        if user["role"] in ["manager", "admin"]:
            return True

        # Employees can only edit themselves
        return user["employee_id"] == target_employee_id

# Convenience functions for endpoints
def get_current_user(auth: Optional[str] = Header(None, alias="Authorization")) -> Optional[Dict]:
    return AuthManager.get_current_user(auth)

def require_auth(auth: Optional[str] = Header(None, alias="Authorization")) -> Dict:
    return AuthManager.require_auth(auth)

def require_manager(auth: Optional[str] = Header(None, alias="Authorization")) -> Dict:
    return AuthManager.require_manager(auth)

def require_self_or_manager(employee_id: str, auth: Optional[str] = Header(None, alias="Authorization")):
    user = require_auth(auth)
    if user["role"] not in ["manager", "admin"] and user["employee_id"] != employee_id:
        raise HTTPException(status_code=403, detail="Can only access your own data")
    return user
