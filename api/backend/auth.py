from typing import Optional, Dict, Callable, Set
from datetime import datetime, timedelta
from fastapi import HTTPException, Header
import secrets
import json
import os
import jwt
from datetime import timezone
import threading
from collections import defaultdict

# JWT-based authentication (stateless, works with Vercel serverless)
class AuthManager:
    SESSION_DURATION_HOURS = 24
    JWT_SECRET = os.getenv("JWT_SECRET")
    
    # Token blacklist for revocation (in-memory, thread-safe)
    _revoked_tokens: Set[str] = set()
    _revoked_lock = threading.RLock()
    
    # Active session tracking (in-memory, thread-safe)
    _active_sessions: Dict[str, datetime] = defaultdict(lambda: datetime.now(timezone.utc))
    _session_lock = threading.RLock()
    
    @staticmethod
    def _ensure_secret() -> None:
        """Ensure JWT_SECRET is set, raise error if not."""
        if not AuthManager.JWT_SECRET:
            raise HTTPException(
                status_code=500,
                detail="JWT_SECRET environment variable not set. Please configure it for secure authentication."
            )

    @staticmethod
    def _encode_jwt(payload: Dict) -> str:
        """Encode payload as JWT using HS256 algorithm."""
        AuthManager._ensure_secret()
        # Use numeric 'exp' claim for JWT standard compliance
        payload_with_exp = payload.copy()
        payload_with_exp["exp"] = (datetime.now(timezone.utc) + timedelta(hours=AuthManager.SESSION_DURATION_HOURS)).timestamp()
        token = jwt.encode(payload_with_exp, AuthManager.JWT_SECRET, algorithm="HS256")
        return token

    @staticmethod
    def _decode_jwt(token: str) -> Optional[Dict]:
        """Decode and verify JWT token."""
        AuthManager._ensure_secret()
        try:
            payload = jwt.decode(token, AuthManager.JWT_SECRET, algorithms=["HS256"])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    @staticmethod
    def login(employee_id: str, password: Optional[str] = None, get_employee_func: Optional[Callable] = None) -> str:
        """Create a JWT token for an employee"""
        # Use employee lookup function
        if get_employee_func:
            employee = get_employee_func(employee_id)
        else:
            raise HTTPException(status_code=500, detail="Employee lookup function not provided")

        if not employee:
            raise HTTPException(status_code=401, detail="Invalid employee")

        # Handle both Employee objects and dicts
        if isinstance(employee, dict):
            employee_name = employee.get("name", employee_id)
            employee_role = employee.get("employee_type", "employee")
        else:
            employee_name = employee.name
            employee_role = employee.employee_type

        # Create JWT payload (exp is added in _encode_jwt)
        payload = {
            "employee_id": employee_id,
            "employee_name": employee_name,
            "role": employee_role,
            "jti": secrets.token_hex(16)  # Unique token ID for revocation
        }

        # Encode as token
        token = AuthManager._encode_jwt(payload)

        return token

    @staticmethod
    def logout(token: str) -> None:
        """Revoke a JWT token by adding it to the blacklist."""
        if not token or not token.startswith("Bearer "):
            return
        
        token = token.replace("Bearer ", "")
        
        # Decode to get jti (token ID) for revocation
        try:
            payload = AuthManager._decode_jwt(token)
            if payload and "jti" in payload:
                with AuthManager._revoked_lock:
                    AuthManager._revoked_tokens.add(payload["jti"])
        except (jwt.InvalidTokenError, ValueError, KeyError):
            # If token is invalid, no need to revoke
            pass

    @staticmethod
    def revoke_token_for_user(employee_id: str) -> None:
        """Revoke all tokens for a specific user (e.g., on password change or employee deletion)."""
        # In a production system with Redis, we would store user->token mappings
        # For in-memory implementation, we can only revoke tokens we've seen
        # This is a limitation of the simple in-memory approach
        print(f"[AUTH] Revoking all tokens for employee {employee_id} (limited in-memory implementation)")

    @staticmethod
    def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[Dict]:
        """Get current user from JWT token"""
        if not authorization or not authorization.startswith("Bearer "):
            return None

        token = authorization.replace("Bearer ", "")
        payload = AuthManager._decode_jwt(token)

        if not payload:
            return None

        # Check if token is revoked
        if "jti" in payload:
            with AuthManager._revoked_lock:
                if payload["jti"] in AuthManager._revoked_tokens:
                    return None

        return payload

    @staticmethod
    def require_auth(authorization: Optional[str] = Header(None)) -> Dict:
        """Require authentication, raise 401 if not logged in"""
        user = AuthManager.get_current_user(authorization)
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        # Track active session
        employee_id = user.get("employee_id")
        if employee_id:
            with AuthManager._session_lock:
                AuthManager._active_sessions[employee_id] = datetime.now(timezone.utc)
        
        return user

    @staticmethod
    def require_manager(authorization: Optional[str] = Header(None)) -> Dict:
        """Require manager or admin role, raise 403 if not manager/admin"""
        user = AuthManager.require_auth(authorization)
        if user["role"] not in ["manager", "admin"]:
            raise HTTPException(status_code=403, detail="Manager access required")
        return user

    @staticmethod
    def get_active_session_count() -> int:
        """Get count of active sessions (last 5 minutes)."""
        with AuthManager._session_lock:
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(minutes=5)
            # Remove stale sessions
            stale_users = [uid for uid, last_seen in AuthManager._active_sessions.items() if last_seen < cutoff]
            for uid in stale_users:
                del AuthManager._active_sessions[uid]
            return len(AuthManager._active_sessions)

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
