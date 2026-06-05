from typing import Optional, Dict
from datetime import datetime, timedelta
from fastapi import HTTPException, Header
import secrets

# Simple session storage (in production, use Redis or database)
sessions: Dict[str, Dict] = {}

class AuthManager:
    SESSION_DURATION_HOURS = 8
    
    @staticmethod
    def login(employee_id: str) -> str:
        """Create a session for an employee and return token"""
        # Lazy import to avoid circular imports
        from data_store import get_all_employees
        employees = get_all_employees()
        employee = next((e for e in employees if e.id == employee_id), None)
        
        if not employee:
            raise HTTPException(status_code=401, detail="Invalid employee")
        
        # Generate secure token
        token = secrets.token_urlsafe(32)
        
        # Store session
        sessions[token] = {
            "employee_id": employee_id,
            "employee_name": employee.name,
            "role": employee.employee_type,
            "expires": datetime.now() + timedelta(hours=AuthManager.SESSION_DURATION_HOURS)
        }
        
        return token
    
    @staticmethod
    def logout(token: str):
        """End a session"""
        if token in sessions:
            del sessions[token]
    
    @staticmethod
    def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[Dict]:
        """Get current user from session token"""
        if not authorization or not authorization.startswith("Bearer "):
            return None
        
        token = authorization.replace("Bearer ", "")
        session = sessions.get(token)
        
        if not session:
            return None
        
        # Check expiration
        if datetime.now() > session["expires"]:
            del sessions[token]
            return None
        
        return session
    
    @staticmethod
    def require_auth(authorization: Optional[str] = Header(None)) -> Dict:
        """Require authentication, raise 401 if not logged in"""
        user = AuthManager.get_current_user(authorization)
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return user
    
    @staticmethod
    def require_manager(authorization: Optional[str] = Header(None)) -> Dict:
        """Require manager role, raise 403 if not manager"""
        user = AuthManager.require_auth(authorization)
        if user["role"] != "manager":
            raise HTTPException(status_code=403, detail="Manager access required")
        return user
    
    @staticmethod
    def can_edit_employee(authorization: Optional[str], target_employee_id: str) -> bool:
        """Check if user can edit/view an employee's data"""
        user = AuthManager.get_current_user(authorization)
        if not user:
            return False
        
        # Managers can edit anyone
        if user["role"] == "manager":
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
    if user["role"] != "manager" and user["employee_id"] != employee_id:
        raise HTTPException(status_code=403, detail="Can only access your own data")
    return user
