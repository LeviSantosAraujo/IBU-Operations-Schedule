"""
GitHub JSON storage - single source of truth for all data.

Stores each entity type in a separate JSON file on the data branch:
- employees.json
- schedules.json
- availability_requests.json
- availabilities.json
- notifications.json
- system_config.json
- events.json
- coverage_requirements.json

Uses optimistic locking with SHA-based retry for concurrent write safety.
Integrates with cache_manager for performance optimization and rate limit protection.
Exposes the same function names as staging_store for drop-in compatibility.
"""

import os
from dotenv import load_dotenv

# Load environment variables BEFORE importing github_storage
load_dotenv('.env')

import json
import base64
from typing import List, Dict, Any, Optional
from datetime import date, datetime
import github_storage
import flow_storage
import contextvars

# Context variables for flow tracking
_flow_chain_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('flow_chain_id', default=None)
_flow_parent_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('flow_parent_id', default=None)

GITHUB_AVAILABLE = github_storage.GITHUB_AVAILABLE
_API_BASE = "https://api.github.com"


def _headers() -> dict:
    """Get headers for GitHub API requests."""
    return {
        "Authorization": f"Bearer {github_storage.GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _file_url(filename: str) -> str:
    """Get the GitHub Contents API URL for a specific file."""
    return f"{_API_BASE}/repos/{github_storage.GITHUB_REPO}/contents/{filename}?ref={github_storage.GITHUB_DATA_BRANCH}"


def _serialize_dates(obj: Any) -> Any:
    """Convert date/datetime objects to strings for JSON storage."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: _serialize_dates(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_serialize_dates(item) for item in obj]
    return obj


def _deserialize_dates(obj: Any) -> Any:
    """Convert date strings back to date/datetime objects."""
    if isinstance(obj, str):
        try:
            if 'T' in obj:
                return datetime.fromisoformat(obj)
            else:
                return date.fromisoformat(obj)
        except (ValueError, TypeError):
            return obj
    elif isinstance(obj, dict):
        return {k: _deserialize_dates(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_deserialize_dates(item) for item in obj]
    return obj


def _update_rate_limit_from_headers(headers: dict) -> None:
    """Update rate limit information from GitHub API response headers."""
    try:
        import cache_manager
        
        remaining = int(headers.get("X-RateLimit-Remaining", 5000))
        total = int(headers.get("X-RateLimit-Limit", 5000))
        reset_time = headers.get("X-RateLimit-Reset")
        if reset_time:
            reset_time = int(reset_time)
        cache_manager.update_rate_limit(remaining, total, reset_time)
        
        # Alert if rate limit usage is high
        if cache_manager.is_rate_limit_alert():
            print(f"[JSON_STORE] WARNING: Rate limit usage is high!")
    except (ValueError, TypeError) as e:
        print(f"[JSON_STORE] Error parsing rate limit headers: {e}")


def _read_json_file(filename: str, current_sha: Optional[str] = None) -> Any:
    """Read a JSON file from GitHub with caching and SHA-based invalidation. Returns None if not found."""
    import cache_manager
    
    # Track GitHub read operation
    flow = flow_storage.get_flow_storage()
    chain_id = _flow_chain_id.get()
    parent_id = _flow_parent_id.get()
    
    if chain_id:
        op = flow.add_operation(chain_id, "github", f"GET {filename}", parent_id)
        if op:
            _flow_parent_id.set(op.id)
    
    cache = cache_manager.get_cache()
    cache_key = cache_manager.cache_key_for_file(filename)
    
    # Fetch current SHA from GitHub for cache invalidation
    if not current_sha and GITHUB_AVAILABLE:
        try:
            url = _file_url(filename)
            head_resp = github_storage.requests.head(url, headers=_headers(), timeout=5)
            if head_resp.status_code == 200:
                current_sha = head_resp.headers.get("X-GitHub-Sha") or head_resp.headers.get("ETag", "").strip('"')
        except:
            pass  # If HEAD fails, fall back to cache without SHA
    
    # Check cache first with SHA for invalidation
    cached_value = cache.get(cache_key, current_sha)
    if cached_value is not None:
        print(f"[JSON_STORE] Cache hit for {filename}")
        if chain_id and op:
            flow.complete_operation(chain_id, op.id, "success", {"cached": True})
        return cached_value
    
    # Cache miss - get per-key lock to prevent stampede
    key_lock = cache._get_key_lock(cache_key)
    
    # Double-check cache after acquiring lock (another thread may have populated it)
    with key_lock:
        cached_value = cache.get(cache_key, current_sha)
        if cached_value is not None:
            print(f"[JSON_STORE] Cache hit after lock for {filename}")
            if chain_id and op:
                flow.complete_operation(chain_id, op.id, "success", {"cached": True})
            return cached_value
        
        # Still a miss - read from GitHub
        if not GITHUB_AVAILABLE:
            print(f"[JSON_STORE] GitHub not available, cannot read {filename}")
            return None
        
        try:
            url = _file_url(filename)
            print(f"[JSON_STORE] Reading {filename} from GitHub (cache miss)")
            resp = github_storage.requests.get(url, headers=_headers(), timeout=10)
            
            # Update rate limit info from headers
            _update_rate_limit_from_headers(resp.headers)
            
            if resp.status_code == 404:
                print(f"[JSON_STORE] {filename} not found (first run)")
                if chain_id and op:
                    flow.complete_operation(chain_id, op.id, "error", {"status_code": 404})
                return None
            
            if resp.status_code != 200:
                print(f"[JSON_STORE] Failed to read {filename}: HTTP {resp.status_code}")
                if chain_id and op:
                    flow.complete_operation(chain_id, op.id, "error", {"status_code": resp.status_code})
                return None
            
            data = resp.json()
            content = data.get("content")
            sha = data.get("sha")
            
            if content:
                decoded = base64.b64decode(content)
                parsed = json.loads(decoded.decode("utf-8"))
                deserialized = _deserialize_dates(parsed)
                
                # Cache the result with SHA for invalidation
                cache.set(cache_key, deserialized, sha)
                print(f"[JSON_STORE] Cached {filename} with SHA {sha[:8] if sha else 'unknown'}")
                
                if chain_id and op:
                    flow.complete_operation(chain_id, op.id, "success", {"cached": False, "sha": sha[:8] if sha else 'unknown'})
                return deserialized
            
            # Large files (>1MB) come back without inline content; use download_url
            download_url = data.get("download_url")
            if download_url:
                print(f"[JSON_STORE] Using download_url for large file {filename}")
                dl = github_storage.requests.get(download_url, timeout=20)
                if dl.status_code == 200:
                    parsed = json.loads(dl.content.decode("utf-8"))
                    deserialized = _deserialize_dates(parsed)
                    
                    # Cache the result with SHA for invalidation
                    cache.set(cache_key, deserialized, sha)
                    print(f"[JSON_STORE] Cached {filename} with SHA {sha[:8] if sha else 'unknown'}")
                    
                    if chain_id and op:
                        flow.complete_operation(chain_id, op.id, "success", {"cached": False, "sha": sha[:8] if sha else 'unknown', "large_file": True})
                    return deserialized
                else:
                    print(f"[JSON_STORE] Failed to download {filename}: HTTP {dl.status_code}")
                    if chain_id and op:
                        flow.complete_operation(chain_id, op.id, "error", {"status_code": dl.status_code})
            
            print(f"[JSON_STORE] No content in {filename}")
            if chain_id and op:
                flow.complete_operation(chain_id, op.id, "error", {"reason": "no_content"})
            return None
        except Exception as e:
            print(f"[JSON_STORE] Error reading {filename}: {e}")
            return None


def _execute_write(filename: str, data: Any, user_id: Optional[str] = None) -> bool:
    """Execute the actual write to GitHub (called after debounce)."""
    import cache_manager
    
    cache = cache_manager.get_cache()
    cache_key = cache_manager.cache_key_for_file(filename)
    
    if not GITHUB_AVAILABLE:
        print(f"[JSON_STORE] GitHub not available, cannot write {filename}")
        return False
    
    try:
        # Serialize data
        serialized = _serialize_dates(data)
        json_str = json.dumps(serialized)
        
        # Get current SHA
        url = _file_url(filename)
        resp = github_storage.requests.get(url, headers=_headers(), timeout=10)
        sha = None
        if resp.status_code == 200:
            sha = resp.json().get("sha")
        
        # Prepare payload
        payload = {
            "message": f"Update {filename}",
            "content": base64.b64encode(json_str.encode("utf-8")).decode("utf-8"),
            "branch": github_storage.GITHUB_DATA_BRANCH,
        }
        if sha:
            payload["sha"] = sha
        
        print(f"[JSON_STORE] Writing {filename} to GitHub ({len(json_str)} bytes)")
        resp = github_storage.requests.put(url, headers=_headers(), json=payload, timeout=20)
        
        # Update rate limit info from headers
        _update_rate_limit_from_headers(resp.headers)
        
        if resp.status_code in (200, 201):
            print(f"[JSON_STORE] {filename} written successfully")
            # Update cache with new data and new SHA instead of invalidating
            response_data = resp.json()
            new_sha = response_data.get("sha") or response_data.get("content", {}).get("sha")
            cache.set(cache_key, data, new_sha)
            return True
        
        # Stale sha -> refetch and retry once
        if resp.status_code == 409:
            print(f"[JSON_STORE] 409 conflict on {filename}, refetching sha and retrying")
            fresh_resp = github_storage.requests.get(url, headers=_headers(), timeout=10)
            if fresh_resp.status_code == 200:
                fresh_sha = fresh_resp.json().get("sha")
                if fresh_sha:
                    payload["sha"] = fresh_sha
                    retry = github_storage.requests.put(url, headers=_headers(), json=payload, timeout=20)
                    # Update rate limit info from headers
                    _update_rate_limit_from_headers(retry.headers)
                    if retry.status_code in (200, 201):
                        print(f"[JSON_STORE] {filename} written successfully on retry")
                        # Update cache with new data and new SHA instead of invalidating
                        retry_sha = retry.json().get("sha")
                        cache.set(cache_key, data, retry_sha)
                        return True
        
        print(f"[JSON_STORE] Failed to write {filename}: HTTP {resp.status_code}")
        return False
    except Exception as e:
        print(f"[JSON_STORE] Error writing {filename}: {e}")
        return False


def _write_json_file(filename: str, data: Any, user_id: Optional[str] = None, immediate: bool = False) -> bool:
    """Write a JSON file to GitHub with optimistic locking, retry, and cache invalidation.
    
    In serverless environments, all writes must be immediate to prevent data loss.
    The 'immediate' parameter is kept for API compatibility but is ignored.
    
    Args:
        filename: Name of the file to write
        data: Data to write
        user_id: Optional user ID for audit logging
        immediate: Ignored - all writes are immediate in serverless
    """
    print(f"[JSON_STORE] Immediate write for {filename}")
    return _execute_write(filename, data, user_id)


def get_employees() -> List[Dict]:
    """Get employees from employees.json."""
    data = _read_json_file("employees.json")
    return data if data else []


def get_employee_by_id(employee_id: str) -> Optional[Dict]:
    """Get a specific employee by ID from employees.json."""
    employees = get_employees()
    for emp in employees:
        if emp.get("id") == employee_id:
            return emp
    return None


def set_employees(employees: List[Dict], user_id: Optional[str] = None, immediate: bool = False) -> bool:
    """Set employees in employees.json with audit logging.
    
    Args:
        employees: List of employee dictionaries
        user_id: Optional user ID for audit logging
        immediate: If True, bypass debouncing and write immediately
    """
    result = _write_json_file("employees.json", employees, user_id=user_id, immediate=immediate)
    if result and user_id:
        import audit_logger
        audit_logger.log_write_operation("employee", "update", None, user_id, {"count": len(employees)})
    return result


def get_schedules() -> List[Dict]:
    """Get schedules from schedules.json."""
    data = _read_json_file("schedules.json")
    return data if data else []


def set_schedules(schedules: List[Dict], user_id: Optional[str] = None, immediate: bool = False) -> bool:
    """Set schedules in schedules.json with audit logging.
    
    Args:
        schedules: List of schedule dictionaries
        user_id: Optional user ID for audit logging
        immediate: If True, bypass debouncing and write immediately
    """
    result = _write_json_file("schedules.json", schedules, user_id=user_id, immediate=immediate)
    if result and user_id:
        import audit_logger
        audit_logger.log_write_operation("schedule", "update", None, user_id, {"count": len(schedules)})
    return result


def get_availability_requests() -> List[Dict]:
    """Get availability requests from availability_requests.json."""
    data = _read_json_file("availability_requests.json")
    return data if data else []


def set_availability_requests(requests: List[Dict], user_id: Optional[str] = None, immediate: bool = False) -> bool:
    """Set availability requests in availability_requests.json with audit logging.
    
    Args:
        requests: List of availability request dictionaries
        user_id: Optional user ID for audit logging
        immediate: If True, bypass debouncing and write immediately
    """
    result = _write_json_file("availability_requests.json", requests, user_id=user_id, immediate=immediate)
    if result and user_id:
        import audit_logger
        audit_logger.log_write_operation("availability_request", "update", None, user_id, {"count": len(requests)})
    return result


def get_notifications() -> List[Dict]:
    """Get notifications from notifications.json."""
    data = _read_json_file("notifications.json")
    return data if data else []


def set_notifications(notifications: List[Dict], user_id: Optional[str] = None, immediate: bool = False) -> bool:
    """Set notifications in notifications.json with audit logging.
    
    Args:
        notifications: List of notification dictionaries
        user_id: Optional user ID for audit logging
        immediate: If True, bypass debouncing and write immediately
    """
    result = _write_json_file("notifications.json", notifications, user_id=user_id, immediate=immediate)
    if result and user_id:
        import audit_logger
        audit_logger.log_write_operation("notification", "update", None, user_id, {"count": len(notifications)})
    return result


def get_system_config() -> Dict:
    """Get system config from system_config.json (fallback to config.json)."""
    data = _read_json_file("system_config.json")
    if data:
        return data
    # Fallback to config.json for backward compatibility
    data = _read_json_file("config.json")
    return data if data else {}


def set_system_config(config: Dict, user_id: Optional[str] = None, immediate: bool = False) -> bool:
    """Set system config in system_config.json with audit logging.
    
    Args:
        config: System configuration dictionary
        user_id: Optional user ID for audit logging
        immediate: If True, bypass debouncing and write immediately
    """
    result = _write_json_file("system_config.json", config, user_id=user_id, immediate=immediate)
    if result and user_id:
        import audit_logger
        audit_logger.log_write_operation("system_config", "update", None, user_id, {"keys": list(config.keys())})
    return result


def get_events() -> List[Dict]:
    """Get events from events.json."""
    data = _read_json_file("events.json")
    return data if data else []


def set_events(events: List[Dict], user_id: Optional[str] = None) -> bool:
    """Set events in events.json with audit logging."""
    result = _write_json_file("events.json", events)
    if result and user_id:
        import audit_logger
        audit_logger.log_write_operation("event", "update", None, user_id, {"count": len(events)})
    return result


def get_coverage_requirements() -> List[Dict]:
    """Get coverage requirements from coverage_requirements.json."""
    data = _read_json_file("coverage_requirements.json")
    return data if data else []


# ============ In-Memory Locked Shifts Cache ============

def set_coverage_requirements(requirements: List[Dict], user_id: Optional[str] = None) -> bool:
    """Set coverage requirements in coverage_requirements.json with audit logging."""
    result = _write_json_file("coverage_requirements.json", requirements)
    if result and user_id:
        import audit_logger
        audit_logger.log_write_operation("coverage_requirement", "update", None, user_id, {"count": len(requirements)})
    return result


# ============ Password Management ============

def get_passwords() -> List[Dict]:
    """Get passwords from passwords.json."""
    data = _read_json_file("passwords.json")
    return data if data else []


def set_passwords(passwords: List[Dict], user_id: Optional[str] = None, immediate: bool = False) -> bool:
    """Set passwords in passwords.json with audit logging.

    Args:
        passwords: List of password dictionaries (employee_id, password_hash)
        user_id: Optional user ID for audit logging
        immediate: If True, bypass debouncing and write immediately
    """
    result = _write_json_file("passwords.json", passwords, user_id=user_id, immediate=immediate)
    if result and user_id:
        import audit_logger
        audit_logger.log_write_operation("password", "update", None, user_id, {"count": len(passwords)})
    return result
