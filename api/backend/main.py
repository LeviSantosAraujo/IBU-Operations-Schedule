# IBU Operations Schedule API
# GitHub persistence enabled - data stored in data branch
import os
from dotenv import load_dotenv

# Load environment variables from .env for local development BEFORE any imports
load_dotenv('.env')

# Import log_storage first for print override
import log_storage
from datetime import datetime, timezone
from collections import defaultdict
import threading
from datetime import timedelta

# Custom print function to capture logs for monitoring dashboard
_original_print = print

def custom_print(*args, **kwargs):
    """Custom print that logs to storage and calls original print."""
    # Log to storage
    message = ' '.join(str(arg) for arg in args)
    level = "INFO"
    if "[ERROR]" in message or "Error" in message or "error" in message:
        level = "ERROR"
    elif "[WARNING]" in message or "Warning" in message:
        level = "WARNING"
    elif "[CRITICAL]" in message:
        level = "CRITICAL"
    
    log_storage.get_log_storage().add_backend_log(message, level)
    
    # Call original print
    _original_print(*args, **kwargs)

# Override print globally BEFORE any other imports
print = custom_print

# In-memory session tracking
_active_sessions = defaultdict(lambda: datetime.now(timezone.utc))
_session_lock = threading.Lock()

def track_session(user_id: str):
    """Track a user session."""
    with _session_lock:
        _active_sessions[user_id] = datetime.now(timezone.utc)

def get_active_session_count() -> int:
    """Get count of active sessions (last 5 minutes)."""
    with _session_lock:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=5)
        # Remove stale sessions
        stale_users = [uid for uid, last_seen in _active_sessions.items() if last_seen < cutoff]
        for uid in stale_users:
            del _active_sessions[uid]
        return len(_active_sessions)

# Now import all other modules (they will use custom print)
from fastapi import FastAPI, HTTPException, Query, Header, Depends, UploadFile, File, Form, Cookie
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from contextlib import asynccontextmanager
from typing import List, Optional, Dict
from datetime import date
import uuid
import queue
import time
import shutil
import io
import re
from pathlib import Path
from pydantic import BaseModel
import sys

from models import (
    Employee, EmployeeUpdate, Availability, WeeklySchedule, Shift, JobType, Floor,
    AvailabilityType, EmployeeType, FloorCoverageQuery, FloorCoverageResponse,
    AVAILABILITY_COLORS, HourlyCoverageRequirement,
    AvailabilityRequest, AvailabilityRequestStatus, Notification, NotificationType, Event
)

from excel_store import (
    set_blob_key, _clear_workbook_cache
)
from data_store_excel import (
    save_employee, delete_employee,
    get_availabilities, get_availability_for_week, save_availability,
    get_all_schedules, get_schedule_by_week, save_schedule, delete_schedule,
    get_floor_coverage, get_system_config, save_system_config,
    get_availability_requests, save_availability_request,
    get_events, save_event, delete_event,
    get_all_week_schedule_dates,
    set_manager_password, verify_manager_password, manager_has_password,
    get_coverage_requirements, save_coverage_requirement,
    get_notifications, save_notification, mark_notification_read,
    initialize_sample_data,
)
import json_store as staging_store
from storage import store_excel_data, excel_file_exists, get_excel_data
from scheduler import SchedulingEngine, generate_schedule
from auth import AuthManager, require_auth, require_manager, require_self_or_manager
from openpyxl import load_workbook

# Background sync queue for GitHub writes
_sync_queue: queue.Queue = queue.Queue()
_sync_worker_thread: Optional[threading.Thread] = None
_sync_worker_running = False

# Pydantic models for requests
class LoginRequest(BaseModel):
    employee_id: str
    password: Optional[str] = None

class AdminLoginRequest(BaseModel):
    employee_id: str
    password: Optional[str] = None
    secret_key: str

class SetPasswordRequest(BaseModel):
    employee_id: str
    password: str

# Sync status tracking
_sync_status: Dict[str, str] = {}  # request_id -> "syncing", "synced", "failed"
_sync_status_lock = threading.RLock()


def _sync_worker():
    """Background worker to process sync queue with retry logic."""
    global _sync_worker_running
    _sync_worker_running = True
    print("[SYNC] Background sync worker started")
    
    while _sync_worker_running:
        try:
            # Get task from queue with timeout
            task = _sync_queue.get(timeout=1.0)
            if task is None:  # Poison pill to stop worker
                break
            
            request_id = task.get('request_id')
            sync_func = task.get('sync_func')
            retry_count = task.get('retry_count', 0)
            max_retries = 3
            
            try:
                # Update status to syncing
                with _sync_status_lock:
                    _sync_status[request_id] = "syncing"
                
                # Execute sync function
                success = sync_func()
                
                if success:
                    with _sync_status_lock:
                        _sync_status[request_id] = "synced"
                    print(f"[SYNC] Successfully synced request {request_id}")
                else:
                    if retry_count < max_retries:
                        # Retry with exponential backoff
                        retry_count += 1
                        backoff = min(2 ** retry_count, 10)  # Max 10 seconds
                        print(f"[SYNC] Retry {retry_count}/{max_retries} for request {request_id} in {backoff}s")
                        time.sleep(backoff)
                        task['retry_count'] = retry_count
                        _sync_queue.put(task)
                    else:
                        with _sync_status_lock:
                            _sync_status[request_id] = "failed"
                        print(f"[SYNC] Failed to sync request {request_id} after {max_retries} retries")
                
            except Exception as e:
                print(f"[SYNC] Error processing sync for request {request_id}: {e}")
                import traceback
                traceback.print_exc()
                
                if retry_count < max_retries:
                    retry_count += 1
                    backoff = min(2 ** retry_count, 10)
                    print(f"[SYNC] Retry {retry_count}/{max_retries} for request {request_id} in {backoff}s")
                    time.sleep(backoff)
                    task['retry_count'] = retry_count
                    _sync_queue.put(task)
                else:
                    with _sync_status_lock:
                        _sync_status[request_id] = "failed"
            
            _sync_queue.task_done()
            
        except queue.Empty:
            continue
        except Exception as e:
            print(f"[SYNC] Worker error: {e}")
            time.sleep(1)
    
    print("[SYNC] Background sync worker stopped")


def start_sync_worker():
    """Start the background sync worker thread."""
    global _sync_worker_thread
    if _sync_worker_thread is None or not _sync_worker_thread.is_alive():
        _sync_worker_thread = threading.Thread(target=_sync_worker, daemon=True)
        _sync_worker_thread.start()
        print("[SYNC] Started background sync worker thread")


def stop_sync_worker():
    """Stop the background sync worker thread."""
    global _sync_worker_running
    _sync_worker_running = False
    _sync_queue.put(None)  # Poison pill
    if _sync_worker_thread:
        _sync_worker_thread.join(timeout=5)
        print("[SYNC] Stopped background sync worker thread")


def add_sync_task(request_id: str, sync_func):
    """Add a sync task to the background queue."""
    _sync_queue.put({
        'request_id': request_id,
        'sync_func': sync_func,
        'retry_count': 0
    })
    print(f"[SYNC] Added sync task for request {request_id}")


def get_sync_status(request_id: str) -> Optional[str]:
    """Get the sync status for a request."""
    with _sync_status_lock:
        return _sync_status.get(request_id)


def time_ranges_overlap(start_a: str, end_a: str, start_b: str, end_b: str) -> bool:
    """Check if two time ranges overlap. Returns True if they overlap."""
    try:
        from datetime import datetime
        a_start = datetime.strptime(start_a, "%H:%M")
        a_end = datetime.strptime(end_a, "%H:%M")
        b_start = datetime.strptime(start_b, "%H:%M")
        b_end = datetime.strptime(end_b, "%H:%M")
        
        # Handle overnight shifts (e.g., 22:00 to 02:00)
        if a_end <= a_start:
            a_end += timedelta(days=1)
        if b_end <= b_start:
            b_end += timedelta(days=1)
        
        # Check for overlap
        return a_start < b_end and b_start < a_end
    except Exception as e:
        print(f"[ERROR] Failed to parse time ranges for overlap check: {e}")
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: do not load Excel file - all data is served from JSON/blob storage"""
    _clear_workbook_cache()
    print("[STARTUP] Server starting - using JSON/blob storage for all data")
    print("[STARTUP] Initializing log storage for monitoring dashboard")
    print("[STARTUP] Starting background sync worker")
    
    # GitHub JSON is the single source of truth - no Excel fallback needed
    print(f"[STARTUP] Using GitHub JSON as single source of truth")
    
    # Start background sync worker
    start_sync_worker()
    
    print("[STARTUP] Server ready - monitoring dashboard available at /admin/dashboard")
    
    # Load and check data
    print("[STARTUP] Loading employee data...")
    try:
        employees_dicts = staging_store.get_employees()
        print(f"[STARTUP] Loaded {len(employees_dicts)} employees")
        employees = [Employee(**e) for e in employees_dicts]
        employee_ids = {e.id for e in employees}
    except Exception as e:
        print(f"[STARTUP] Error loading employees: {e}")
        employees = []
        employee_ids = set()
    
    print("[STARTUP] Loading availability data...")
    try:
        staging_availabilities = staging_store.get_availabilities()
        print(f"[STARTUP] Loaded {len(staging_availabilities) if staging_availabilities else 0} availability records")
    except Exception as e:
        print(f"[STARTUP] Error loading availabilities: {e}")
        staging_availabilities = []
    
    print("[STARTUP] Loading schedule data...")
    try:
        staging_schedules = staging_store.get_schedules()
        print(f"[STARTUP] Loaded {len(staging_schedules) if staging_schedules else 0} schedule records")
    except Exception as e:
        print(f"[STARTUP] Error loading schedules: {e}")
    
    print("[STARTUP] Checking GitHub configuration...")
    try:
        github_repo = os.getenv("GITHUB_REPO", "Not configured")
        github_branch = os.getenv("GITHUB_DATA_BRANCH", "Not configured")
        print(f"[STARTUP] GitHub repository: {github_repo}")
        print(f"[STARTUP] GitHub data branch: {github_branch}")
    except Exception as e:
        print(f"[STARTUP] Error checking GitHub config: {e}")
    
    # Cleanup orphaned availability records
    try:
        if staging_availabilities:
            orphaned_count = 0
            valid_availabilities = []
            for avail in staging_availabilities:
                if avail.get('employee_id') in employee_ids:
                    valid_availabilities.append(avail)
                else:
                    orphaned_count += 1
                    print(f"[STARTUP] Removing orphaned availability for employee {avail.get('employee_id')}")
            
            if orphaned_count > 0:
                print(f"[STARTUP] Found {orphaned_count} orphaned availability records, cleaning up...")
                staging_store.set_availabilities(valid_availabilities, user_id="system")
                print(f"[STARTUP] Cleaned up {orphaned_count} orphaned availability records")
        
        # Cleanup orphaned availability requests
        staging_requests = staging_store.get_availability_requests()
        if staging_requests:
            orphaned_requests = 0
            valid_requests = []
            for req in staging_requests:
                if req.get('employee_id') in employee_ids:
                    valid_requests.append(req)
                else:
                    orphaned_requests += 1
                    print(f"[STARTUP] Removing orphaned request for employee {req.get('employee_id')}")
            
            if orphaned_requests > 0:
                print(f"[STARTUP] Found {orphaned_requests} orphaned availability requests, cleaning up...")
                staging_store.set_availability_requests(valid_requests, user_id="system")
                print(f"[STARTUP] Cleaned up {orphaned_requests} orphaned availability requests")
    except Exception as e:
        print(f"[STARTUP] Error cleaning up orphaned records: {e}")
    
    yield
    _clear_workbook_cache()

class ExcelPathRequest(BaseModel):
    file_path: str

# Global state
CURRENT_EXCEL_FILE: Optional[str] = None

def is_manager_user(user: Optional[Dict]) -> bool:
    if not user:
        return False
    return str(user.get('employee_type') or user.get('role') or '').lower() == EmployeeType.MANAGER.value

UPLOAD_DIR = Path(__file__).parent / "uploads"
try:
    UPLOAD_DIR.mkdir(exist_ok=True)
except OSError:
    # In Vercel serverless, the filesystem is read-only at /var/task
    # We'll use Vercel Blob storage instead
    pass

app = FastAPI(title="IBU Operations team schedule", version="2.0.0", lifespan=lifespan)

# Enable CORS for frontend
# Note: allow_credentials=True is incompatible with allow_origins=["*"]
# We use allow_credentials=False and handle auth via Bearer token headers instead
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",
        "https://ibu-operations-schedule-frontend-2dbzrj86d.vercel.app",
        "https://ibu-operations-schedule-frontend-ju3it15eq.vercel.app",
        "https://ibu-operations-schedule-frontend-jcrrl3bmx.vercel.app",
        "https://ibu-operations-schedule-frontend-rbrfsfadd.vercel.app",
        "https://ibu-operations-schedule.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000"
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ Health Check ============

@app.get("/")
async def root():
    return {
        "status": "running",
        "message": "IBU Operations Schedule API is running",
        "health": "/api/health",
    }

# ============ Excel File Management ============

@app.get("/api/excel/status")
async def excel_status():
    """Check if system is configured (using JSON/blob storage)"""
    try:
        employees = staging_store.get_employees()
        has_employees = len(employees) > 0
        from storage import BLOB_AVAILABLE
        return {
            "configured": has_employees,
            "file_path": "json_blob_storage" if has_employees else None,
            "file_exists": has_employees,
            "storage_type": "json_blob" if BLOB_AVAILABLE else "json_memory"
        }
    except Exception as e:
        return {
            "configured": False,
            "file_path": None,
            "file_exists": False
        }

@app.get("/api/excel/download")
async def download_excel():
    """Export current GitHub JSON data to Excel file for download"""
    from fastapi.responses import StreamingResponse
    import io
    from openpyxl import Workbook

    # Create Excel workbook
    wb = Workbook()
    
    # Employees sheet - read from GitHub JSON
    emp_sheet = wb.active
    emp_sheet.title = "Employees"
    emp_sheet.append(["ID", "Name", "Email", "Type", "Max Hours", "Active", "Created At"])
    employees = staging_store.get_employees()
    for emp in employees:
        emp_sheet.append([
            emp.get('id'), emp.get('name'), emp.get('email') or "", emp.get('employee_type'),
            emp.get('max_hours_per_week'), emp.get('active'), emp.get('created_at')
        ])
    
    # Schedules sheet - read from GitHub JSON
    schedules = staging_store.get_schedules()
    if schedules:
        sched_sheet = wb.create_sheet("Schedules")
        sched_sheet.append(["Week Start", "Schedule ID", "Employee ID", "Day", "Location", "Start Time", "End Time", "Hours", "Break Provided"])
        for schedule in schedules:
            for shift in schedule.get('shifts', []):
                sched_sheet.append([
                    schedule.get('week_start_date'), schedule.get('id'), shift.get('employee_id'), shift.get('day_of_week'),
                    shift.get('floor'), shift.get('start_time'), shift.get('end_time'), shift.get('hours'), shift.get('break_provided')
                ])
    
    # Availabilities sheet - read from GitHub JSON
    availabilities = staging_store.get_availabilities()
    if availabilities:
        avail_sheet = wb.create_sheet("Availabilities")
        avail_sheet.append(["ID", "Employee ID", "Week Start", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "Approved", "Submitted At"])
        for avail in availabilities:
            avail_sheet.append([
                avail.get('id'), avail.get('employee_id'), avail.get('week_start_date'),
                avail.get('monday'), avail.get('tuesday'), avail.get('wednesday'), avail.get('thursday'),
                avail.get('friday'), avail.get('saturday'), avail.get('sunday'),
                avail.get('approved'), avail.get('submitted_at')
            ])
    
    # Availability Requests sheet - read from GitHub JSON
    requests = staging_store.get_availability_requests()
    if requests:
        req_sheet = wb.create_sheet("Availability Requests")
        req_sheet.append(["ID", "Employee ID", "Request Type", "Start Date", "End Date", "Days of Week", "Start Time", "End Time", "Status", "Created At"])
        for req in requests:
            req_sheet.append([
                req.get('id'), req.get('employee_id'), req.get('request_type'),
                req.get('start_date'), req.get('end_date'), ', '.join(req.get('days_of_week', [])),
                req.get('start_time'), req.get('end_time'), req.get('status'), req.get('created_at')
            ])
    
    # Notifications sheet - read from GitHub JSON
    notifications = staging_store.get_notifications()
    if notifications:
        notif_sheet = wb.create_sheet("Notifications")
        notif_sheet.append(["ID", "Employee ID", "Type", "Message", "Read", "Created At"])
        for notif in notifications:
            notif_sheet.append([
                notif.get('id'), notif.get('employee_id'), notif.get('type'),
                notif.get('message'), notif.get('read'), notif.get('created_at')
            ])
    
    # Config sheet - read from GitHub JSON
    config_sheet = wb.create_sheet("Config")
    config = staging_store.get_system_config()
    config_sheet.append(["Setting", "Value"])
    for key, value in config.items():
        config_sheet.append([key, str(value)])
    
    # Events sheet - read from GitHub JSON
    events = config.get('events', [])
    if events:
        event_sheet = wb.create_sheet("Events")
        event_sheet.append(["ID", "Name", "Week Start Date", "Date", "Start Time", "End Time", "Location", "People Needed", "Description", "Created By"])
        for event in events:
            event_sheet.append([
                event.get('id'), event.get('name'), event.get('week_start_date'),
                event.get('date'), event.get('start_time'), event.get('end_time'),
                event.get('location'), event.get('people_needed'), event.get('description'),
                event.get('created_by')
            ])
    
    # Save to buffer
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=IBU_Schedule.xlsx"}
    )

@app.post("/api/excel/create-new")
async def create_new_excel(authorization: Optional[str] = Header(None)):
    """Create a new Excel database with sample employees - managers only, or anyone if no database exists"""
    # Allow creation if no database exists (initial setup)
    if not excel_file_exists():
        pass  # Initial setup
    else:
        user = require_manager(authorization)
    import io
    from openpyxl import Workbook
    
    try:
        # Create workbook in memory
        wb = Workbook()
        
        # Remove default sheet
        if 'Sheet' in wb.sheetnames:
            wb.remove(wb['Sheet'])
        
        # Create basic tabs
        wb.create_sheet('Config', 0)
        wb.create_sheet('PWDs', 1)
        wb.create_sheet('Employees', 2)
        wb.create_sheet('Availability', 3)
        
        # Save to bytes
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        
        # Try to store using storage module
        try:
            from storage import store_excel_data
            store_excel_data(buffer.read(), "ibu_schedule.xlsx")
        except:
            # If storage fails, continue anyway
            pass
        
        return {
            "message": "New Excel database created successfully",
            "employees_added": 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create Excel database: {str(e)}")

# ============ Password Management ============

@app.post("/api/managers/set-password")
async def set_manager_password_endpoint(request: SetPasswordRequest):
    """Set password for a manager (only if not already set)"""
    employee_dict = staging_store.get_employee_by_id(request.employee_id)
    if not employee_dict:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    employee = Employee(**employee_dict)
    if employee.employee_type != EmployeeType.MANAGER:
        raise HTTPException(status_code=403, detail="Only managers can have passwords")
    
    # Check if password already exists
    if manager_has_password(request.employee_id):
        raise HTTPException(status_code=400, detail="Password already set. Use update-password to change it.")
    
    set_manager_password(request.employee_id, employee.name, request.password)
    
    return {"message": "Password set successfully"}

@app.put("/api/managers/update-password")
async def update_manager_password_endpoint(request: SetPasswordRequest, authorization: Optional[str] = Header(None, alias="Authorization")):
    """Update password for a manager (managers can update their own, or managers can update others)"""
    # Auth check
    user = require_auth(authorization)
    if user["role"] not in ["manager", "admin"] and user["employee_id"] != request.employee_id:
        raise HTTPException(status_code=403, detail="Can only update your own password")
    
    employee_dict = staging_store.get_employee_by_id(request.employee_id)
    if not employee_dict:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    employee = Employee(**employee_dict)
    if employee.employee_type != EmployeeType.MANAGER:
        raise HTTPException(status_code=403, detail="Only managers can have passwords")
    
    set_manager_password(request.employee_id, employee.name, request.password)
    
    return {"message": "Password updated successfully"}

@app.post("/api/managers/verify-password")
async def verify_password_endpoint(request: SetPasswordRequest):
    """Verify manager password"""
    if not manager_has_password(request.employee_id):
        raise HTTPException(status_code=400, detail="Password not set")
    
    is_valid = verify_manager_password(request.employee_id, request.password)
    
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid password")
    
    return {"valid": True}

@app.get("/api/managers/has-password/{employee_id}")
async def check_has_password(employee_id: str):
    """Check if manager has password set"""
    return {"has_password": manager_has_password(employee_id)}

# ============ Auth Endpoints ============

@app.post("/api/login")
async def login(request: LoginRequest):
    """Login as an employee with optional password for managers"""

    # Check if system has employees configured (using JSON/blob storage)
    employees = staging_store.get_employees()
    has_employees = len(employees) > 0
    if not has_employees:
        raise HTTPException(status_code=400, detail="No employees configured. Please initialize the system first.")

    employee_dict = staging_store.get_employee_by_id(request.employee_id)
    if not employee_dict:
        raise HTTPException(status_code=404, detail="Employee not found")

    employee = Employee(**employee_dict)

    # Managers need password verification
    if employee.employee_type == EmployeeType.MANAGER:
        if manager_has_password(request.employee_id):
            if not request.password:
                raise HTTPException(status_code=401, detail="Password required for managers")
            if not verify_manager_password(request.employee_id, request.password):
                raise HTTPException(status_code=401, detail="Invalid password")
        # If no password set yet, allow login (first time setup)

    token = AuthManager.login(request.employee_id, request.password, staging_store.get_employee_by_id)

    return {
        "token": token,
        "employee": employee,
        "role": employee.employee_type,
        "requires_password_setup": employee.employee_type == EmployeeType.MANAGER and not manager_has_password(request.employee_id)
    }

@app.post("/api/admin-login")
async def admin_login(request: AdminLoginRequest):
    """Secret admin login endpoint - requires secret key"""
    ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "ibu-admin-secret-2026")

    if request.secret_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Invalid secret key")

    # Check if system has employees configured
    employees = staging_store.get_employees()
    has_employees = len(employees) > 0
    if not has_employees:
        raise HTTPException(status_code=400, detail="No employees configured. Please initialize the system first.")

    employee_dict = staging_store.get_employee_by_id(request.employee_id)
    if not employee_dict:
        raise HTTPException(status_code=404, detail="Employee not found")

    employee = Employee(**employee_dict)

    # Force manager role for admin login
    if employee.employee_type != EmployeeType.MANAGER:
        raise HTTPException(status_code=403, detail="Admin login only available for managers")

    # Bypass password verification for admin login
    token = AuthManager.login(request.employee_id, request.password, staging_store.get_employee_by_id)

    return {
        "token": token,
        "employee": employee,
        "role": "admin",  # Force admin role
        "requires_password_setup": False
    }

@app.post("/api/logout")
async def logout(authorization: Optional[str] = Header(None)):
    """Logout and end session"""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
        AuthManager.logout(token)
    return {"message": "Logged out"}

@app.get("/api/me")
async def get_me(authorization: Optional[str] = Header(None)):
    """Get current logged-in user info"""
    user = AuthManager.get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

# ============ Employee Endpoints ============

@app.post("/api/staging/cleanup-orphaned-records")
async def cleanup_orphaned_records(authorization: str = Header(None)):
    """Remove availability records for non-existent employees"""
    try:
        user = require_manager(authorization)

        # Get all current employees
        employees_dicts = staging_store.get_employees()
        employees = [Employee(**e) for e in employees_dicts]
        employee_ids = {e.id for e in employees}
        
        # Clean up staging availabilities
        staging_availabilities = staging_store.get_availabilities()
        orphaned_count = 0
        valid_availabilities = []
        for avail in staging_availabilities:
            if avail.get('employee_id') in employee_ids:
                valid_availabilities.append(avail)
            else:
                orphaned_count += 1
                print(f"[CLEANUP] Removing orphaned availability for employee {avail.get('employee_id')}")
        
        if orphaned_count > 0:
            print(f"[CLEANUP] Found {orphaned_count} orphaned availability records")
            staging_store.set_availabilities(valid_availabilities, user_id="system")
        
        # Clean up staging availability requests
        staging_requests = staging_store.get_availability_requests()
        orphaned_requests = 0
        valid_requests = []
        for req in staging_requests:
            if req.get('employee_id') in employee_ids:
                valid_requests.append(req)
            else:
                orphaned_requests += 1
                print(f"[CLEANUP] Removing orphaned request for employee {req.get('employee_id')}")
        
        if orphaned_requests > 0:
            print(f"[CLEANUP] Found {orphaned_requests} orphaned availability requests")
            staging_store.set_availability_requests(valid_requests, user_id="system")
        
        total_cleaned = orphaned_count + orphaned_requests
        if total_cleaned > 0:
            return {"message": f"Cleaned up {total_cleaned} orphaned records ({orphaned_count} availabilities, {orphaned_requests} requests)"}
        else:
            return {"message": "No orphaned records found"}
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to cleanup orphaned records: {str(e)}")

@app.post("/api/staging/reset-from-excel")
async def reset_staging_from_excel(authorization: str = Header(None)):
    """Reset staging data from Excel (managers only)"""
    user = require_manager(authorization)
    
    try:
        # Load all employees from Excel (intentional Excel read for this utility)
        from data_store_excel import get_all_employees
        all_employees = get_all_employees()
        employees_data = [e.model_dump() for e in all_employees]
        
        # Update staging with all employees
        staging_store.set_employees(employees_data, user_id="system")
        
        return {"message": f"Reset staging with {len(employees_data)} employees from Excel"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to reset staging: {str(e)}")

@app.get("/api/employees", response_model=List[Employee])
async def list_employees(active_only: bool = False, authorization: str = Header(None)):
    """List all employees (managers see manager_preferences, employees do not)"""
    try:
        # Read from GitHub JSON (single source of truth)
        staging_employees = staging_store.get_employees()
        employees = [Employee(**e) for e in staging_employees]
        
        print(f"[DEBUG] Loaded {len(employees)} employees")
        if active_only:
            employees = [e for e in employees if e.active]
        
        # Hide manager_preferences from non-managers
        user = None
        if authorization:
            try:
                user = require_auth(authorization)
            except:
                pass  # If auth fails, just return employees without manager_preferences
        
        # Hide manager_preferences if user is not a manager (or if auth failed)
        if not is_manager_user(user):
            for emp in employees:
                emp.manager_preferences = {}
        
        return employees
    except Exception as e:
        print(f"Error loading employees: {e}")
        raise HTTPException(status_code=500, detail=f"Error loading employees: {str(e)}")

@app.get("/api/employees/{employee_id}", response_model=Employee)
async def get_employee(employee_id: str):
    """Get a specific employee"""
    employee_dict = staging_store.get_employee_by_id(employee_id)
    if not employee_dict:
        raise HTTPException(status_code=404, detail="Employee not found")
    return Employee(**employee_dict)

@app.post("/api/employees", response_model=Employee)
async def create_employee(
    employee: Employee,
    user: Dict = Depends(require_manager)
):
    """Create a new employee (managers only)"""
    if not employee.id:
        employee.id = f"emp_{uuid.uuid4().hex[:8]}"
    
    # Update staging layer first (fast)
    employees = staging_store.get_employees()
    employees.append(employee.model_dump())
    staging_store.set_employees(employees, user_id=user.get('employee_id'))
    
    # No action queue needed - GitHub JSON is single source of truth
    
    return employee

@app.put("/api/employees/{employee_id}", response_model=Employee)
async def update_employee(
    employee_id: str,
    employee_update: EmployeeUpdate,
    user: Dict = Depends(require_self_or_manager)
):
    """Update an employee (managers can edit anyone, employees can edit themselves)"""
    existing_dict = staging_store.get_employee_by_id(employee_id)
    if not existing_dict:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    existing = Employee(**existing_dict)
    
    # Build updated employee by merging existing with new values
    update_data = employee_update.model_dump(exclude_unset=True)
    
    # Only managers can update manager_preferences
    if not is_manager_user(user) and 'manager_preferences' in update_data:
        del update_data['manager_preferences']
    
    # Create updated employee object
    updated_employee = Employee(
        id=employee_id,
        name=update_data.get("name", existing.name),
        email=update_data.get("email", existing.email),
        employee_type=update_data.get("employee_type", existing.employee_type),
        max_hours_per_week=update_data.get("max_hours_per_week", existing.max_hours_per_week),
        preferences=update_data.get("preferences", existing.preferences),
        manager_preferences=update_data.get("manager_preferences", existing.manager_preferences),
        active=update_data.get("active", existing.active),
        created_at=existing.created_at
    )
    
    # Update staging layer first (fast)
    employees = staging_store.get_employees()
    employees = [e if e["id"] != employee_id else updated_employee.model_dump() for e in employees]
    staging_store.set_employees(employees, user_id=user.get('employee_id'))
    
    # Add to action queue for Excel sync (async, no blocking)
    # No action queue needed - GitHub JSON is single source of truth
    
    return updated_employee

@app.delete("/api/employees/{employee_id}")
async def remove_employee(
    employee_id: str,
    user: Dict = Depends(require_manager)
):
    """Delete an employee (managers only)"""
    # Update staging layer first (fast)
    employees = staging_store.get_employees()
    was_in_staging = any(e["id"] == employee_id for e in employees)
    employees = [e for e in employees if e["id"] != employee_id]
    staging_store.set_employees(employees, user_id=user.get('employee_id'))
    
    # Clean up availability records for deleted employee
    availabilities = staging_store.get_availabilities()
    cleaned_availabilities = [a for a in availabilities if a.get("employee_id") != employee_id]
    if len(cleaned_availabilities) != len(availabilities):
        print(f"[DELETE] Cleaning up {len(availabilities) - len(cleaned_availabilities)} availability records for deleted employee {employee_id}")
        staging_store.set_availabilities(cleaned_availabilities, user_id=user.get('employee_id'))
    
    # Clean up availability requests for deleted employee
    requests = staging_store.get_availability_requests()
    cleaned_requests = [r for r in requests if r.get("employee_id") != employee_id]
    if len(cleaned_requests) != len(requests):
        print(f"[DELETE] Cleaning up {len(requests) - len(cleaned_requests)} availability requests for deleted employee {employee_id}")
        staging_store.set_availability_requests(cleaned_requests, user_id=user.get('employee_id'))
    
    # Clean up notifications for deleted employee
    notifications = staging_store.get_notifications()
    cleaned_notifications = [n for n in notifications if n.get("employee_id") != employee_id]
    if len(cleaned_notifications) != len(notifications):
        print(f"[DELETE] Cleaning up {len(notifications) - len(cleaned_notifications)} notifications for deleted employee {employee_id}")
        staging_store.set_notifications(cleaned_notifications, user_id=user.get('employee_id'))
    
    # Note: Excel cleanup removed - GitHub JSON is now the single source of truth
    
    # Return success if employee was in staging
    if was_in_staging:
        return {"message": "Employee deleted"}
    
    raise HTTPException(status_code=404, detail="Employee not found")

# ============ Availability Endpoints ============

@app.get("/api/availability", response_model=List[Availability])
async def list_availabilities(
    week_start_date: Optional[date] = None,
    employee_id: Optional[str] = None,
    authorization: Optional[str] = Header(None)
):
    """List availabilities - employees see only their own, managers see all"""
    user = require_auth(authorization)
    
    # Employees can only see their own availability
    if user["role"] != "manager":
        employee_id = user["employee_id"]
    
    # Read from GitHub JSON (single source of truth)
    staging_availabilities = staging_store.get_availabilities()
    availabilities = [Availability(**a) for a in staging_availabilities]
    
    # Filter by week_start_date if provided
    if week_start_date:
        availabilities = [a for a in availabilities if a.week_start_date == week_start_date]
    
    # Filter by employee_id if provided
    if employee_id:
        availabilities = [a for a in availabilities if a.employee_id == employee_id]
    
    return availabilities

@app.get("/api/availability/{employee_id}/{week_start_date}", response_model=Availability)
async def get_employee_availability(
    employee_id: str,
    week_start_date: date,
    authorization: Optional[str] = Header(None)
):
    """Get availability for a specific employee and week"""
    # Check permissions
    require_self_or_manager(employee_id, authorization)
    
    availability = get_availability_for_week(employee_id, week_start_date)
    if not availability:
        # Return default availability
        return Availability(
            id=str(uuid.uuid4()),
            employee_id=employee_id,
            week_start_date=week_start_date
        )
    return availability

@app.post("/api/availability", response_model=Availability)
async def submit_availability(
    availability: Availability,
    authorization: Optional[str] = Header(None)
):
    """Submit or update availability - employees can only submit their own"""
    user = require_auth(authorization)
    
    # Auto-generate ID if not provided
    if not availability.id:
        availability.id = f"avail_{availability.employee_id}_{availability.week_start_date}"
    
    # Employees can only submit their own availability
    if user["role"] != "manager" and availability.employee_id != user["employee_id"]:
        raise HTTPException(status_code=403, detail="Can only submit your own availability")
    
    # 24-hour cutoff check for employees (not managers)
    if user["role"] != "manager":
        # Calculate the first day of the week being submitted
        week_start = availability.week_start_date
        today = date.today()
        
        # Check if any day in the week is within 24 hours of now
        # The week starts on Monday, so we check each day
        days_offset = 0  # Monday
        current_day_of_week = today.weekday()  # 0=Monday, 6=Sunday
        
        # If the week being submitted is the current week or a past week
        if week_start <= today:
            # Calculate which day of the week today is relative to the week start
            days_since_week_start = (today - week_start).days
            
            # If today is within the week being submitted, check if it's too late to change
            if 0 <= days_since_week_start <= 6:
                # The week includes today or past days - cannot change
                raise HTTPException(
                    status_code=403, 
                    detail=f"Cannot change availability for week that includes today or past days. Changes must be made at least 24 hours before the week starts."
                )
        
        # If the week starts within 24 hours from now, also block
        hours_until_week_start = (week_start - today).days * 24
        if hours_until_week_start < 24:
            raise HTTPException(
                status_code=403,
                detail=f"Cannot change availability for week starting in less than 24 hours. Changes must be made at least 24 hours before the week starts."
            )
    
    if not availability.id:
        availability.id = f"avail_{uuid.uuid4().hex[:8]}"
    availability.submitted_at = datetime.now()
    # Reset approval status when availability is modified
    availability.approved = False
    availability.approved_by = None
    availability.approved_at = None
    
    # Update staging layer first (fast)
    config = staging_store.get_system_config()
    if 'availabilities' not in config:
        config['availabilities'] = []
    config['availabilities'] = [a if a['id'] != availability.id else availability.model_dump() for a in config['availabilities']]
    if not any(a['id'] == availability.id for a in config['availabilities']):
        config['availabilities'].append(availability.model_dump())
    staging_store.set_system_config(config, user_id=user.get('employee_id'))
    
    # Add to action queue for Excel sync (async, no blocking)
    # No action queue needed - GitHub JSON is single source of truth
    
    return availability

@app.get("/api/availability/colors")
async def get_availability_colors():
    """Get color mapping for availability types"""
    return AVAILABILITY_COLORS

@app.post("/api/availability/{availability_id}/approve")
async def approve_availability(
    availability_id: str,
    authorization: Optional[str] = Header(None)
):
    """Approve availability (managers only)"""
    user = require_manager(authorization)
    
    # Get all availabilities and find the one to approve
    availabilities = get_availabilities()
    availability = None
    for avail in availabilities:
        if avail.id == availability_id:
            availability = avail
            break
    
    if not availability:
        raise HTTPException(status_code=404, detail="Availability not found")
    
    # Update approval status
    availability.approved = True
    availability.approved_by = user["employee_id"]
    availability.approved_at = datetime.now()
    
    # Update staging layer first (fast)
    config = staging_store.get_system_config()
    if 'availabilities' not in config:
        config['availabilities'] = []
    config['availabilities'] = [a if a['id'] != availability.id else availability.model_dump() for a in config['availabilities']]
    staging_store.set_system_config(config, user_id=user.get('employee_id'))
    
    # Add to action queue for Excel sync (async, no blocking)
    # No action queue needed - GitHub JSON is single source of truth
    
    return availability

@app.get("/api/availability/pending")
async def get_pending_availabilities(user: Dict = Depends(require_manager)):
    """Get all pending (unapproved) availabilities (managers only)"""
    all_availabilities = get_availabilities()
    pending = [avail for avail in all_availabilities if not avail.approved]
    return pending

# ============ Hourly Coverage Requirements Endpoints ============

@app.get("/api/coverage-requirements/{week_start_date}")
async def get_coverage_requirements(
    week_start_date: date,
    authorization: Optional[str] = Header(None)
):
    """Get hourly coverage requirements for a week (managers only)"""
    user = require_manager(authorization)
    requirements = get_coverage_requirements(week_start_date)
    return {"week_start_date": week_start_date, "requirements": requirements}

@app.post("/api/coverage-requirements")
async def set_coverage_requirements(
    requirements: List[HourlyCoverageRequirement],
    authorization: Optional[str] = Header(None)
):
    """Set hourly coverage requirements for a week (managers only)"""
    user = require_manager(authorization)
    for req in requirements:
        req.created_by = user["employee_id"]
        save_coverage_requirement(req)
    return {"message": f"Saved {len(requirements)} coverage requirements"}

# ============ Schedule Endpoints ============

@app.get("/api/schedules", response_model=List[WeeklySchedule])
async def list_schedules(authorization: Optional[str] = Header(None)):
    """List all schedules (all authenticated users)"""
    require_auth(authorization)
    
    # Try to read from staging first
    staging_schedules = staging_store.get_schedules()
    return [WeeklySchedule(**s) for s in staging_schedules]

@app.get("/api/schedules/{week_start_date}", response_model=WeeklySchedule)
async def get_schedule(
    week_start_date: date,
    authorization: Optional[str] = Header(None)
):
    """Get schedule for a specific week (all authenticated users)"""
    user = require_auth(authorization)
    
    print(f"[SCHEDULE] Getting schedule for week {week_start_date}, user: {user.get('employee_id')}, is_manager: {is_manager_user(user)}")
    
    # Try to read from staging first
    staging_schedules = staging_store.get_schedules()
    schedule = None
    if staging_schedules:
        for s in staging_schedules:
            # Handle both string and date objects
            week_start = s.get('week_start_date')
            if isinstance(week_start, date):
                week_start_str = str(week_start)
            else:
                week_start_str = week_start
            
            if week_start_str == str(week_start_date):
                schedule = WeeklySchedule(**s)
                print(f"[SCHEDULE] Found schedule in staging with {len(schedule.shifts)} shifts")
                # Log locked shifts
                locked_shifts = [s for s in schedule.shifts if s.locked]
                print(f"[SCHEDULE] Locked shifts in schedule: {len(locked_shifts)}")
                for ls in locked_shifts:
                    print(f"[SCHEDULE]   - {ls.id}: emp={ls.employee_id}, day={ls.day_of_week}, locked={ls.locked}, type={ls.locked_availability_type}")
                break
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    # Recreate pending locked shifts if they're missing but the request still exists
    all_requests = staging_store.get_availability_requests()
    week_end_date = week_start_date + timedelta(days=6)
    day_map = {0: 'monday', 1: 'tuesday', 2: 'wednesday', 3: 'thursday', 4: 'friday', 5: 'saturday', 6: 'sunday'}
    
    for req in all_requests:
        if req.get('status') != 'pending':
            continue
        
        emp_id = req.get('employee_id')
        if not emp_id:
            continue
        
        # Check if request overlaps with the current week
        if req.get('start_date') and req.get('end_date'):
            try:
                req_start = date.fromisoformat(str(req['start_date'])[:10])
                req_end = date.fromisoformat(str(req['end_date'])[:10])
                if req_end < week_start_date or req_start > week_end_date:
                    continue
                
                req_days = req.get('days_of_week', [])
                request_type = req.get('request_type', 'availability')
                
                # For each day in the week that matches the request's days_of_week
                current_date = week_start_date
                while current_date <= week_end_date:
                    day_name = day_map[current_date.weekday()]
                    if day_name in req_days and current_date >= req_start and current_date <= req_end:
                        # Check if a pending locked shift already exists for this employee/day
                        existing_pending = next(
                            (s for s in schedule.shifts 
                             if s.employee_id == emp_id and s.day_of_week == day_name and s.locked and s.id.startswith(f"pending_{req['id']}")),
                            None
                        )
                        
                        if not existing_pending:
                            # Create pending locked shift
                            if request_type == 'day_off':
                                shift_start = '00:00'
                                shift_end = '23:59'
                                shift_location = 'day off'
                                shift_hours = 0
                                locked_type = 'Day Off'
                            else:
                                shift_start = req.get('start_time', '00:00')
                                shift_end = req.get('end_time', '23:59')
                                shift_location = None
                                shift_hours = 0
                                locked_type = request_type.capitalize()
                            
                            pending_shift = Shift(
                                id=f"pending_{req['id']}_{day_name}_{emp_id}",
                                employee_id=emp_id,
                                day_of_week=day_name,
                                start_time=shift_start,
                                end_time=shift_end,
                                job_type=JobType.IBU_OPS,
                                location=shift_location,
                                hours=shift_hours,
                                locked=True,
                                locked_availability_type=locked_type,
                                is_event=False
                            )
                            schedule.shifts.append(pending_shift)
                            print(f"[SCHEDULE] Recreated pending locked shift for {emp_id} on {day_name}")
                    
                    current_date += timedelta(days=1)
            except Exception as e:
                print(f"[SCHEDULE] Warning: could not recreate pending locked shift: {e}")
                continue
    
    # Recreate approved locked shifts if they're missing but the request still exists
    for req in all_requests:
        if req.get('status') not in ['approved', 'AvailabilityRequestStatus.APPROVED']:
            continue
        
        emp_id = req.get('employee_id')
        if not emp_id:
            continue
        
        # Check if request overlaps with the current week
        if req.get('start_date') and req.get('end_date'):
            try:
                req_start = date.fromisoformat(str(req['start_date'])[:10])
                req_end = date.fromisoformat(str(req['end_date'])[:10])
                if req_end < week_start_date or req_start > week_end_date:
                    continue
                
                req_days = req.get('days_of_week', [])
                request_type = req.get('request_type', 'availability')
                
                # For each day in the week that matches the request's days_of_week
                current_date = week_start_date
                while current_date <= week_end_date:
                    day_name = day_map[current_date.weekday()]
                    if day_name in req_days and current_date >= req_start and current_date <= req_end:
                        # Check if an approved locked shift already exists for this employee/day
                        existing_approved = next(
                            (s for s in schedule.shifts 
                             if s.employee_id == emp_id and s.day_of_week == day_name and s.locked and s.id.startswith(f"locked_{req['id']}")),
                            None
                        )
                        
                        if not existing_approved:
                            # Create approved locked shift
                            if request_type == 'day_off':
                                shift_start = '00:00'
                                shift_end = '23:59'
                                shift_location = 'day off'
                                shift_hours = 0
                                locked_type = 'Day Off'
                            else:
                                shift_start = req.get('start_time', '00:00')
                                shift_end = req.get('end_time', '23:59')
                                shift_location = None
                                shift_hours = 0
                                locked_type = request_type.capitalize()
                            
                            approved_shift = Shift(
                                id=f"locked_{req['id']}_{day_name}_{emp_id}",
                                employee_id=emp_id,
                                day_of_week=day_name,
                                start_time=shift_start,
                                end_time=shift_end,
                                job_type=JobType.IBU_OPS,
                                location=shift_location,
                                hours=shift_hours,
                                locked=True,
                                locked_availability_type=locked_type,
                                is_event=False
                            )
                            schedule.shifts.append(approved_shift)
                            print(f"[SCHEDULE] Recreated approved locked shift for {emp_id} on {day_name}")
                    
                    current_date += timedelta(days=1)
            except Exception as e:
                print(f"[SCHEDULE] Warning: could not recreate approved locked shift: {e}")
                continue
    
    # Derive approved availability markers from approved requests
    # This replaces the old locked-shift mechanism
    approved_markers = []
    
    for req in all_requests:
        if req.get('status') not in ['approved', 'AvailabilityRequestStatus.APPROVED']:
            continue
        
        emp_id = req.get('employee_id')
        if not emp_id:
            continue
        
        # Filter: employees see only their own
        if not is_manager_user(user) and emp_id != user.get('employee_id'):
            continue
        
        # Handle new date range model
        if req.get('start_date') and req.get('end_date'):
            try:
                req_start = date.fromisoformat(str(req['start_date'])[:10])
                req_end = date.fromisoformat(str(req['end_date'])[:10])
                req_days = req.get('days_of_week', [])
                request_type = req.get('request_type', 'availability')
                
                # Check if this request overlaps with the current week
                if req_end < week_start_date or req_start > week_end_date:
                    continue
                
                # For each day in the week that matches the request's days_of_week
                current_date = week_start_date
                while current_date <= week_end_date:
                    day_name = day_map[current_date.weekday()]
                    if day_name in req_days and current_date >= req_start and current_date <= req_end:
                        # Check if a real shift exists for this employee/day with overlapping time
                        has_overlapping_shift = False
                        for shift in schedule.shifts:
                            if shift.employee_id == emp_id and shift.day_of_week == day_name:
                                # For day-off requests, any shift overlaps
                                if request_type == 'day_off':
                                    has_overlapping_shift = True
                                    break
                                # For time-range requests, check time overlap
                                elif req.get('start_time') and req.get('end_time'):
                                    if time_ranges_overlap(
                                        req.get('start_time'), req.get('end_time'),
                                        shift.start_time, shift.end_time
                                    ):
                                        has_overlapping_shift = True
                                        break
                        
                        # Only add marker if no overlapping real shift exists
                        if not has_overlapping_shift:
                            marker = {
                                'employee_id': emp_id,
                                'day_of_week': day_name,
                                'date': current_date.isoformat(),
                                'request_type': request_type,
                                'start_time': req.get('start_time'),
                                'end_time': req.get('end_time'),
                                'employee_comment': req.get('employee_comment'),
                                'request_id': req.get('id')
                            }
                            approved_markers.append(marker)
                    
                    current_date += timedelta(days=1)
            except Exception as e:
                print(f"[SCHEDULE] Warning: could not parse approved request: {e}")
                continue
    
    # Add availability requests to the schedule response (pending requests only for managers)
    week_requests = []
    for req in all_requests:
        if req.get('status') == 'pending':
            # Check if request overlaps with the current week
            if req.get('start_date') and req.get('end_date'):
                try:
                    req_start = date.fromisoformat(str(req['start_date'])[:10])
                    req_end = date.fromisoformat(str(req['end_date'])[:10])
                    if req_end < week_start_date or req_start > week_end_date:
                        continue
                    week_requests.append(req)
                except:
                    continue
            elif req.get('week_start_date'):
                # Legacy model
                if str(req.get('week_start_date')) == str(week_start_date):
                    week_requests.append(req)
    
    # Filter: employees see only their own
    if not is_manager_user(user):
        week_requests = [r for r in week_requests if r.get('employee_id') == user.get('employee_id')]
    
    # Add availabilities and requests to schedule (this is a dynamic field, not in the model)
    schedule_data = schedule.model_dump()
    schedule_data['approved_availabilities'] = approved_markers
    schedule_data['availability_requests'] = week_requests
    
    return schedule_data

@app.post("/api/schedules/generate/{week_start_date}", response_model=WeeklySchedule)
async def auto_generate_schedule(
    week_start_date: date,
    user: Dict = Depends(require_manager)
):
    """Auto-generate a schedule for a week (managers only)"""
    from scheduler import SchedulingEngine

    try:
        # Get staffing targets from config
        config = get_system_config()
        # SystemConfig is a Pydantic model, access attributes directly
        staffing_targets = getattr(config, 'staffing_targets', None) or getattr(config, 'floor_requirements', {}) or {}
        print(f"[API] Staffing targets: {staffing_targets}")

        # Convert staffing targets to location_requirements format
        # staffing_targets is simple dict like {'ground_floor': 2, 'call_center': 4}
        # location_requirements needs to be {'location': {'monday': 2, 'tuesday': 2, ...}}
        location_requirements = {}
        event_staffing = {}  # event_id -> people_needed
        call_center_target = 0  # Number of people to assign call center role for the week
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']  # Sunday excluded - only for events

        # Map staffing target keys to location names
        # Note: call_center is now a role/flag, not a physical location
        location_map = {
            'ground_floor': 'ground floor',
            'second_floor': '2nd floor',
            'sixth_floor': '6th floor',
            '80_bloor': '80 bloor',
            'working_from_home': 'working from home'
        }

        for key, target in staffing_targets.items():
            if key.startswith('event_'):
                # Event staffing target - handle both old (event_event_...) and new (event_...) formats
                # Strip double prefix if present
                event_id = key.replace('event_event_', 'event_')
                event_staffing[event_id] = target
                print(f"[API] Event staffing: {key} -> {event_id} = {target}")
            elif key == 'call_center':
                # Call center is now a role/flag, not a location - pass separately to scheduler
                # Target is people per day (applies to every day)
                call_center_target = target
                print(f"[API] Call center role target: {target} people per day")
            else:
                # Regular location staffing target - target is people per day (applies to every day)
                # Skip working_from_home - manager assigns manually on-demand
                if key == 'working_from_home':
                    continue
                location_name = location_map.get(key, key.replace('_', ' '))
                location_requirements[location_name] = {day: target for day in days}
                print(f"[API] Location staffing: {key} -> {location_name} = {target} people per day")

        print(f"[API] Total event staffing entries: {len(event_staffing)}")
        print(f"[API] Event staffing dict: {event_staffing}")
        print(f"[API] Call center target: {call_center_target}")
        print(f"[API] Location requirements passed to scheduler: {location_requirements}")
        
        # Preserve locked shifts from existing schedule before generating new one
        staging_schedules = staging_store.get_schedules()
        existing_schedule = None
        for s in staging_schedules:
            if str(s.get('week_start_date')) == str(week_start_date):
                existing_schedule = WeeklySchedule(**s)
                break
        
        # Recreate locked shifts from approved availability requests before generating
        # This ensures locked shifts are preserved even if they were only recreated in get_schedule
        all_requests = staging_store.get_availability_requests()
        week_end_date = week_start_date + timedelta(days=6)
        day_map = {0: 'monday', 1: 'tuesday', 2: 'wednesday', 3: 'thursday', 4: 'friday', 5: 'saturday', 6: 'sunday'}
        
        # If existing schedule exists, use it as base; otherwise start with empty schedule
        if existing_schedule:
            schedule_for_locked = existing_schedule
        else:
            schedule_for_locked = WeeklySchedule(week_start_date=week_start_date, shifts=[])
        
        # Recreate approved locked shifts if they're missing but the request still exists
        for req in all_requests:
            if req.get('status') not in ['approved', 'AvailabilityRequestStatus.APPROVED']:
                continue
            
            emp_id = req.get('employee_id')
            if not emp_id:
                continue
            
            # Check if request overlaps with the current week
            if req.get('start_date') and req.get('end_date'):
                try:
                    req_start = date.fromisoformat(str(req['start_date'])[:10])
                    req_end = date.fromisoformat(str(req['end_date'])[:10])
                    if req_end < week_start_date or req_start > week_end_date:
                        continue
                    
                    req_days = req.get('days_of_week', [])
                    request_type = req.get('request_type', 'availability')
                    
                    # For each day in the week that matches the request's days_of_week
                    current_date = week_start_date
                    while current_date <= week_end_date:
                        day_name = day_map[current_date.weekday()]
                        if day_name in req_days and current_date >= req_start and current_date <= req_end:
                            # Check if an approved locked shift already exists for this employee/day
                            existing_approved = next(
                                (s for s in schedule_for_locked.shifts 
                                 if s.employee_id == emp_id and s.day_of_week == day_name and s.locked and s.id.startswith(f"locked_{req['id']}")),
                                None
                            )
                            
                            if not existing_approved:
                                # Create approved locked shift
                                if request_type == 'day_off':
                                    shift_start = '00:00'
                                    shift_end = '23:59'
                                    shift_location = 'day off'
                                    shift_hours = 0
                                    locked_type = 'Day Off'
                                else:
                                    shift_start = req.get('start_time', '00:00')
                                    shift_end = req.get('end_time', '23:59')
                                    shift_location = None
                                    shift_hours = 0
                                    locked_type = request_type.capitalize()
                                
                                approved_shift = Shift(
                                    id=f"locked_{req['id']}_{day_name}_{emp_id}",
                                    employee_id=emp_id,
                                    day_of_week=day_name,
                                    start_time=shift_start,
                                    end_time=shift_end,
                                    job_type=JobType.IBU_OPS,
                                    location=shift_location,
                                    hours=shift_hours,
                                    locked=True,
                                    locked_availability_type=locked_type,
                                    is_event=False
                                )
                                schedule_for_locked.shifts.append(approved_shift)
                                print(f"[API] Recreated approved locked shift for {emp_id} on {day_name}")
                        
                        current_date += timedelta(days=1)
                except Exception as e:
                    print(f"[API] Warning: could not recreate approved locked shift: {e}")
                    continue
        
        # Now preserve all locked shifts (including recreated ones)
        preserved_locked_shifts = [s for s in schedule_for_locked.shifts if s.locked]
        print(f"[API] Preserving {len(preserved_locked_shifts)} locked shifts")
        
        engine = SchedulingEngine()
        schedule = engine.generate_auto_schedule(week_start_date, location_requirements, event_staffing, call_center_target)
        
        # Add preserved locked shifts back to the new schedule
        for locked_shift in preserved_locked_shifts:
            schedule.shifts.append(locked_shift)
            print(f"[API] Restored locked shift: {locked_shift.id}")
        
        # Update staging layer first (fast) - remove all schedules with this week_start_date to prevent duplicates
        schedules = staging_store.get_schedules()
        schedules = [s for s in schedules if str(s.get('week_start_date')) != str(week_start_date)]
        schedules.append(schedule.model_dump())
        staging_store.set_schedules(schedules, user_id=user.get('employee_id'))
        
        # Add to action queue for Excel sync (async, no blocking)
        # No action queue needed - GitHub JSON is single source of truth
        
        return schedule
    except Exception as e:
        import traceback
        print(f"[API] Error in auto_generate_schedule: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Schedule generation failed: {str(e)}")

@app.post("/api/schedules", response_model=WeeklySchedule)
async def create_or_update_schedule(
    schedule: WeeklySchedule,
    user: Dict = Depends(require_manager)
):
    """Save a schedule (manual editing) (managers only)"""
    schedule.updated_at = datetime.now()
    
    # Update staging layer first (fast)
    schedules = staging_store.get_schedules()
    schedules = [s if s['id'] != schedule.id else schedule.model_dump() for s in schedules]
    if not any(s['id'] == schedule.id for s in schedules):
        schedules.append(schedule.model_dump())
    staging_store.set_schedules(schedules, user_id=user.get('employee_id'))
    
    # Add to action queue for Excel sync (async, no blocking)
    # No action queue needed - GitHub JSON is single source of truth
    
    return schedule

@app.put("/api/schedules/{week_start_date}/shifts", response_model=WeeklySchedule)
async def update_schedule_shifts(
    week_start_date: date,
    shifts: List[Shift],
    user: Dict = Depends(require_manager)
):
    """Update shifts for a schedule (drag-drop saves here) (managers only)"""
    # Try staging first for speed
    staging_schedules = staging_store.get_schedules()
    schedule = None
    for s in staging_schedules:
        # Handle both string and date objects
        week_start = s.get('week_start_date')
        if isinstance(week_start, date):
            week_start_str = str(week_start)
        else:
            week_start_str = week_start
        
        if week_start_str == str(week_start_date):
            schedule = WeeklySchedule(**s)
            break
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    schedule.shifts = shifts
    # Recalculate total hours
    total_hours = {}
    for shift in shifts:
        # Skip day off shifts when calculating total hours
        if shift.location == 'day off' or shift.locked_availability_type == 'Day Off':
            continue
        current = total_hours.get(shift.employee_id, 0)
        total_hours[shift.employee_id] = current + shift.hours
    schedule.total_hours = total_hours
    schedule.updated_at = datetime.now()
    
    # Update staging layer first (fast)
    schedules = staging_store.get_schedules()
    schedules = [s if s['id'] != schedule.id else schedule.model_dump() for s in schedules]
    staging_store.set_schedules(schedules, user_id=user.get('employee_id'))
    
    # Add to action queue for Excel sync (async, no blocking)
    # No action queue needed - GitHub JSON is single source of truth
    
    return schedule

@app.put("/api/schedules/{week_start_date}/shifts/{shift_id}/break")
async def mark_break_provided(
    week_start_date: date,
    shift_id: str,
    break_provided: bool = True,
    user: Dict = Depends(require_manager)
):
    """Mark a shift's break as provided (managers only)"""
    # Try staging first for speed
    staging_schedules = staging_store.get_schedules()
    schedule = None
    for s in staging_schedules:
        # Handle both string and date objects
        week_start = s.get('week_start_date')
        if isinstance(week_start, date):
            week_start_str = str(week_start)
        else:
            week_start_str = week_start
        
        if week_start_str == str(week_start_date):
            schedule = WeeklySchedule(**s)
            break
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    shift = next((s for s in schedule.shifts if s.id == shift_id), None)
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    
    shift.break_provided = break_provided
    schedule.updated_at = datetime.now()
    
    # Update staging layer first (fast)
    schedules = staging_store.get_schedules()
    schedules = [s if s['id'] != schedule.id else schedule.model_dump() for s in schedules]
    staging_store.set_schedules(schedules, user_id=user.get('employee_id'))
    
    # Add to action queue for Excel sync (async, no blocking)
    # No action queue needed - GitHub JSON is single source of truth
    
    return schedule

@app.post("/api/schedules/{week_start_date}/publish")
async def publish_schedule(
    week_start_date: date,
    user: Dict = Depends(require_manager)
):
    """Publish a schedule (finalize it) (managers only)"""
    # Try staging first for speed
    staging_schedules = staging_store.get_schedules()
    schedule = None
    for s in staging_schedules:
        # Handle both string and date objects
        week_start = s.get('week_start_date')
        if isinstance(week_start, date):
            week_start_str = str(week_start)
        else:
            week_start_str = week_start
        
        if week_start_str == str(week_start_date):
            schedule = WeeklySchedule(**s)
            break
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    schedule.status = "published"
    
    # Update staging layer first (fast)
    schedules = staging_store.get_schedules()
    schedules = [s if s['id'] != schedule.id else schedule.model_dump() for s in schedules]
    staging_store.set_schedules(schedules, user_id=user.get('employee_id'))
    
    # Add to action queue for Excel sync (async, no blocking)
    # No action queue needed - GitHub JSON is single source of truth
    
    return {"message": "Schedule published"}

@app.delete("/api/schedules/{week_start_date}")
async def remove_schedule(
    week_start_date: date,
    user: Dict = Depends(require_manager)
):
    """Delete a schedule (managers only)"""
    # Update staging layer first (fast)
    staging_schedules = staging_store.get_schedules()
    initial_count = len(staging_schedules)
    staging_schedules = [s for s in staging_schedules if str(s.get('week_start_date')) != str(week_start_date)]
    
    if len(staging_schedules) < initial_count:
        # Schedule was in staging, update staging
        staging_store.set_schedules(staging_schedules, user_id=user.get('employee_id'))
        return {"message": "Schedule deleted"}
    
    raise HTTPException(status_code=404, detail="Schedule not found")

@app.get("/api/schedules/weeks/available")
async def get_available_weeks(user: Dict = Depends(require_manager)):
    """Get list of all weeks that have schedule data (managers only)"""
    weeks = get_all_week_schedule_dates()
    return {
        "weeks": [w.isoformat() for w in weeks],
        "count": len(weeks)
    }

@app.post("/api/schedules/{week_start_date}/clear")
async def clear_schedule_shifts(
    week_start_date: date,
    user: Dict = Depends(require_manager)
):
    """Clear all shifts from a schedule while preserving events (managers only)"""
    print(f"[CLEAR SCHEDULE] Starting clear for week {week_start_date} by user {user.get('employee_id')}")
    
    # Try to read from staging first
    staging_schedules = staging_store.get_schedules()
    print(f"[CLEAR SCHEDULE] Found {len(staging_schedules)} schedules in staging")
    
    schedule = None
    for s in staging_schedules:
        # Handle both string and date objects
        week_start = s.get('week_start_date')
        if isinstance(week_start, date):
            week_start_str = str(week_start)
        else:
            week_start_str = week_start
        
        if week_start_str == str(week_start_date):
            schedule = WeeklySchedule(**s)
            print(f"[CLEAR SCHEDULE] Found schedule for week {week_start_date} with {len(schedule.shifts)} shifts")
            break
    
    if not schedule:
        print(f"[CLEAR SCHEDULE] Schedule not found for week {week_start_date}")
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    # Clear all shifts - approved/pending availability markers are derived from requests
    schedule.shifts = []
    schedule.total_hours = {}
    print(f"[CLEAR SCHEDULE] Cleared shifts from schedule")
    
    # Force cache invalidation to ensure fresh data
    import cache_manager
    cache_manager.clear_cache()
    print(f"[CLEAR SCHEDULE] Cleared cache")
    
    # Update staging layer with immediate write (bypass debouncing)
    schedules = staging_store.get_schedules()
    schedules = [s for s in schedules if str(s.get('week_start_date')) != str(week_start_date)]
    schedules.append(schedule.model_dump())
    print(f"[CLEAR SCHEDULE] Updating staging with {len(schedules)} schedules")
    
    result = staging_store.set_schedules(schedules, user_id=user.get('employee_id'), immediate=True)
    print(f"[CLEAR SCHEDULE] set_schedules returned: {result}")
    
    return schedule

# ============ Floor Coverage & Queries ============

@app.get("/api/floor-coverage/{floor}/{day_of_week}/{time_slot}")
async def query_floor_coverage(
    floor: Floor,
    day_of_week: str,
    time_slot: str,
    week_start_date: date = Query(...),
    user: Dict = Depends(require_manager)
):
    """Query how many employees are on a floor at a given time (managers only)"""
    result = get_floor_coverage(floor.value, day_of_week, time_slot, week_start_date)
    return result

@app.get("/api/floor-coverage/summary/{week_start_date}")
async def get_weekly_floor_summary(
    week_start_date: date,
    user: Dict = Depends(require_manager)
):
    """Get floor coverage summary for entire week (managers only)"""
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    time_slots = ["morning", "afternoon", "evening"]
    floors = [Floor.GROUND, Floor.SECOND, Floor.SIXTH]
    
    summary = {}
    for floor in floors:
        summary[floor.value] = {}
        for day in days:
            summary[floor.value][day] = {}
            for slot in time_slots:
                result = get_floor_coverage(floor.value, day, slot, week_start_date)
                summary[floor.value][day][slot] = result["employee_count"]
    
    return summary

# ============ Analytics & Reporting ============

@app.get("/api/analytics/employee-hours/{week_start_date}")
async def get_employee_hours_summary(
    week_start_date: date,
    user: Dict = Depends(require_manager)
):
    """Get hours summary for all employees for a week (managers only)"""
    staging_schedules = staging_store.get_schedules()
    schedule = None
    for s in staging_schedules:
        if s.get('week_start_date') == str(week_start_date):
            schedule = WeeklySchedule(**s)
            break
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    employees_dicts = staging_store.get_employees()
    employees = [Employee(**e) for e in employees_dicts]
    
    summary = []
    for emp in employees:
        hours = schedule.total_hours.get(emp.id, 0) if schedule else 0
        remaining = emp.max_hours_per_week - hours
        summary.append({
            "employee_id": emp.id,
            "name": emp.name,
            "type": emp.employee_type,
            "scheduled_hours": hours,
            "max_hours": emp.max_hours_per_week,
            "remaining_hours": remaining,
            "utilization": round(hours / emp.max_hours_per_week * 100, 1) if emp.max_hours_per_week > 0 else 0
        })
    
    return summary

# ============ Configuration ============

@app.get("/api/config")
async def get_config():
    """Get system configuration"""
    # Try to read from staging first
    return staging_store.get_system_config()

@app.put("/api/config")
async def update_config(config: Dict):
    """Update system configuration"""
    result = save_system_config(config)
    
    # Update staging layer
    staging_store.set_system_config(result.model_dump(), user_id="system")
    
    # Add to action queue for Excel sync
    # No action queue needed - GitHub JSON is single source of truth
    
    return result

@app.get("/api/staffing-targets")
async def get_staffing_targets():
    """Get staffing targets for all locations"""
    config = get_system_config()
    targets = config.staffing_targets
    
    # Normalize keys: strip double event_ prefix
    cleaned_targets = {}
    for key, value in targets.items():
        # Always strip double event_ prefix if present
        normalized_key = key.replace('event_event_', 'event_')
        cleaned_targets[normalized_key] = value
    
    # Remove working_from_home from targets (manager assigns manually)
    if 'working_from_home' in cleaned_targets:
        del cleaned_targets['working_from_home']
    
    return cleaned_targets

@app.put("/api/staffing-targets")
async def update_staffing_targets(targets: Dict[str, int], user: Dict = Depends(require_manager)):
    """Update staffing targets for locations"""
    config = get_system_config()
    
    # Normalize keys: strip double event_ prefix
    cleaned_targets = {}
    for key, value in targets.items():
        # Always strip double event_ prefix if present
        normalized_key = key.replace('event_event_', 'event_')
        # Remove working_from_home from targets (manager assigns manually)
        if normalized_key == 'working_from_home':
            continue
        cleaned_targets[normalized_key] = value
    
    config.staffing_targets = cleaned_targets
    result = save_system_config(config)
    
    if result:
        # Update staging layer
        staging_store.set_system_config(result.model_dump(), user_id="system")
        
        # Add to action queue for Excel sync
        # No action queue needed - GitHub JSON is single source of truth
    
    return result

# ============ Availability Requests ============

@app.get("/api/availability-requests")
async def get_all_availability_requests(authorization: str = Header(None)):
    """Get all availability requests (managers only)"""
    user = AuthManager.get_current_user(authorization)
    if not user or user.get('role') not in ['manager', 'admin']:
        raise HTTPException(status_code=403, detail="Manager access required")
    
    # Read from GitHub JSON (single source of truth)
    staging_requests = staging_store.get_availability_requests()
    # Add employee names to requests
    all_employees_dicts = staging_store.get_employees()
    all_employees = [Employee(**e) for e in all_employees_dicts]
    employee_map = {e.id: e.name for e in all_employees}
    for request in staging_requests:
        request['employee_name'] = employee_map.get(request.get('employee_id'), 'Unknown')
    return staging_requests

@app.get("/api/availability-requests/my")
async def get_my_availability_requests(authorization: str = Header(None)):
    """Get current user's availability requests"""
    user = AuthManager.get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Read from GitHub JSON (single source of truth)
    staging_requests = staging_store.get_availability_requests()
    my_requests = [r for r in staging_requests if r.get('employee_id') == user.get('employee_id')]
    return my_requests

@app.post("/api/availability-requests")
async def create_availability_request(request: Dict, authorization: str = Header(None)):
    """Create an availability request"""
    try:
        user = AuthManager.get_current_user(authorization)
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorized")

        request['id'] = str(uuid.uuid4())
        request['employee_id'] = user['employee_id']
        request['status'] = AvailabilityRequestStatus.PENDING
        request['created_at'] = datetime.now()

        # Update staging layer first (fast)
        requests = staging_store.get_availability_requests()
        requests.append(request)
        staging_store.set_availability_requests(requests, user_id=user.get('employee_id'))
        
        # Add to action queue for Excel sync (async, no blocking)
        # No action queue needed - GitHub JSON is single source of truth

        # Create locked shifts for pending availability request
        try:
            request_type = request.get('request_type', 'availability')
            start_date_str = request.get('start_date', request.get('week_start_date', ''))
            end_date_str = request.get('end_date', start_date_str)
            days_of_week = request.get('days_of_week', [])
            employee_id = request.get('employee_id')
            
            if start_date_str and end_date_str and days_of_week:
                try:
                    start_date = date.fromisoformat(str(start_date_str)[:10])
                    end_date = date.fromisoformat(str(end_date_str)[:10])
                    day_map = {0: 'monday', 1: 'tuesday', 2: 'wednesday', 3: 'thursday', 4: 'friday', 5: 'saturday', 6: 'sunday'}
                    
                    # Process each week in the date range
                    current_week_start = start_date - timedelta(days=start_date.weekday())
                    while current_week_start <= end_date:
                        week_end = current_week_start + timedelta(days=6)
                        
                        # Get or create schedule for this week
                        staging_schedules = staging_store.get_schedules()
                        schedule = None
                        for s in staging_schedules:
                            week_start = s.get('week_start_date')
                            if isinstance(week_start, date):
                                week_start_str = str(week_start)
                            else:
                                week_start_str = week_start
                            if week_start_str == str(current_week_start):
                                schedule = WeeklySchedule(**s)
                                break
                        
                        if not schedule:
                            # Create new schedule
                            schedule = WeeklySchedule(
                                id=f"schedule_{current_week_start.isoformat()}",
                                week_start_date=current_week_start,
                                shifts=[],
                                total_hours={},
                                created_by=user.get('employee_id')
                            )
                        
                        # Create locked shifts for each matching day in this week
                        current_date = max(current_week_start, start_date)
                        while current_date <= min(week_end, end_date):
                            day_name = day_map[current_date.weekday()]
                            if day_name in days_of_week:
                                # Check if a locked shift already exists for this employee/day
                                existing_locked = next(
                                    (s for s in schedule.shifts 
                                     if s.employee_id == employee_id and s.day_of_week == day_name and s.locked),
                                    None
                                )
                                
                                if not existing_locked:
                                    # Create locked shift
                                    if request_type == 'day_off':
                                        shift_start = '00:00'
                                        shift_end = '23:59'
                                        shift_location = 'day off'
                                        shift_hours = 0
                                        locked_type = 'Day Off'
                                    else:
                                        shift_start = request.get('start_time', '00:00')
                                        shift_end = request.get('end_time', '23:59')
                                        shift_location = None  # Placeholder, manager will assign
                                        shift_hours = 0  # Don't count toward total
                                        locked_type = request_type.capitalize()
                                    
                                    locked_shift = Shift(
                                        id=f"pending_{request['id']}_{day_name}_{employee_id}",
                                        employee_id=employee_id,
                                        day_of_week=day_name,
                                        start_time=shift_start,
                                        end_time=shift_end,
                                        job_type=JobType.IBU_OPS,  # Placeholder
                                        location=shift_location,
                                        hours=shift_hours,
                                        locked=True,
                                        locked_availability_type=locked_type,
                                        is_event=False
                                    )
                                    schedule.shifts.append(locked_shift)
                                    print(f"[CREATION] Created pending locked shift for {employee_id} on {day_name}")
                            
                            current_date += timedelta(days=1)
                        
                        # Save the updated schedule
                        staging_schedules = [s for s in staging_schedules if str(s.get('week_start_date')) != str(current_week_start)]
                        staging_schedules.append(schedule.model_dump())
                        staging_store.set_schedules(staging_schedules, user_id=user.get('employee_id'))
                        
                        current_week_start += timedelta(days=7)
                        
                except Exception as e:
                    print(f"[CREATION] Warning: could not create pending locked shifts: {e}")
                    import traceback
                    traceback.print_exc()
        except Exception as e:
            print(f"[CREATION] Warning: error in pending locked shift creation: {e}")
            import traceback
            traceback.print_exc()
        
        # Send notification to managers
        try:
            employee_dict = staging_store.get_employee_by_id(user['employee_id'])
            employee = Employee(**employee_dict) if employee_dict else None
            employee_name = employee.name if employee else user['employee_id']
            
            request_type = request.get('request_type', 'availability')
            days_str = ', '.join(request.get('days_of_week', [])) if request.get('days_of_week') else 'All days'
            time_str = f"{request.get('start_time', '00:00')} - {request.get('end_time', '23:59')}" if request.get('start_time') else 'All day'
            
            # Get all managers
            all_employees_dicts = staging_store.get_employees()
            all_employees = [Employee(**e) for e in all_employees_dicts]
            managers = [e for e in all_employees if e.employee_type in ['manager', 'admin']]
            
            # Create all notifications first, then save once to avoid duplicates
            notifications = staging_store.get_notifications()
            for manager in managers:
                notification = {
                    'id': str(uuid.uuid4()),
                    'employee_id': manager.id,
                    'type': NotificationType.AVAILABILITY_REQUEST,
                    'message': f"{employee_name} submitted a {request_type} request for {days_str} ({time_str})",
                    'details': {
                        'request_id': request['id'],
                        'employee_id': user['employee_id'],
                        'employee_name': employee_name,
                        'request_type': request_type,
                        'days_of_week': days_str,
                        'time_range': time_str,
                        'start_date': request.get('start_date'),
                        'end_date': request.get('end_date'),
                        'employee_comment': request.get('employee_comment', '')
                    },
                    'created_at': datetime.now(),
                    'read': False
                }
                notifications.append(notification)
            
            # Save all notifications at once to avoid duplicate writes
            staging_store.set_notifications(notifications, user_id=user.get('employee_id'))
            print(f"[API] Created {len(managers)} manager notifications for request {request['id']}")
                
        except Exception as e:
            print(f"[API] Warning: could not send manager notification: {e}")
            import traceback
            traceback.print_exc()
        
        # Ensure response is JSON-serializable
        try:
            response = dict(request)  # Create a proper dict copy
            if isinstance(response.get('created_at'), datetime):
                response['created_at'] = response['created_at'].isoformat()
            if isinstance(response.get('updated_at'), datetime):
                response['updated_at'] = response['updated_at'].isoformat()
            if isinstance(response.get('approved_at'), datetime):
                response['approved_at'] = response['approved_at'].isoformat()
            print(f"[API] Returning response with keys: {list(response.keys())}")
            return response
        except Exception as e:
            import traceback
            print(f"[API] Error serializing response: {e}")
            traceback.print_exc()
            # Return a minimal response if serialization fails
            return {
                'id': request.get('id'),
                'status': str(request.get('status')),
                'employee_id': request.get('employee_id')
            }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[API] Error creating availability request: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error creating request: {str(e)}")

@app.put("/api/availability-requests/{request_id}/approve")
async def approve_availability_request(request_id: str, body: Dict = {}, authorization: str = Header(None)):
    """Approve an availability request"""
    try:
        user = AuthManager.get_current_user(authorization)
        if not user or user.get('role') not in ['manager', 'admin']:
            raise HTTPException(status_code=403, detail="Manager access required")

        # Read from GitHub JSON (single source of truth)
        staging_requests = staging_store.get_availability_requests()
        requests = staging_requests
        
        request_data = next((r for r in requests if r['id'] == request_id), None)

        if not request_data:
            raise HTTPException(status_code=404, detail="Request not found")

        # Update status to APPROVED immediately
        request_data['status'] = AvailabilityRequestStatus.APPROVED
        request_data['manager_comment'] = body.get('comment')
        request_data['updated_at'] = datetime.now()
        request_data['approved_by'] = user.get('employee_id')
        request_data['approved_at'] = datetime.now()

        # Update staging layer first (fast)
        requests = staging_store.get_availability_requests()
        requests = [r if r['id'] != request_id else request_data for r in requests]
        staging_store.set_availability_requests(requests, user_id=user.get('employee_id'))
        
        # Add to action queue for Excel sync (async, no blocking)
        # No action queue needed - GitHub JSON is single source of truth

        # Update pending locked shifts to approved locked shifts
        try:
            start_date_str = request_data.get('start_date', request_data.get('week_start_date', ''))
            end_date_str = request_data.get('end_date', start_date_str)
            days_of_week = request_data.get('days_of_week', [])
            employee_id = request_data.get('employee_id')
            request_type = request_data.get('request_type', 'availability')
            
            if start_date_str and end_date_str and days_of_week:
                try:
                    start_date = date.fromisoformat(str(start_date_str)[:10])
                    end_date = date.fromisoformat(str(end_date_str)[:10])
                    day_map = {0: 'monday', 1: 'tuesday', 2: 'wednesday', 3: 'thursday', 4: 'friday', 5: 'saturday', 6: 'sunday'}
                    
                    # Process each week in the date range
                    current_week_start = start_date - timedelta(days=start_date.weekday())
                    while current_week_start <= end_date:
                        # Get schedule for this week
                        staging_schedules = staging_store.get_schedules()
                        schedule = None
                        for s in staging_schedules:
                            week_start = s.get('week_start_date')
                            if isinstance(week_start, date):
                                week_start_str = str(week_start)
                            else:
                                week_start_str = week_start
                            if week_start_str == str(current_week_start):
                                schedule = WeeklySchedule(**s)
                                break
                        
                        if not schedule:
                            # Create new empty schedule for this week
                            schedule = WeeklySchedule(
                                id=f"schedule_{current_week_start.isoformat()}",
                                week_start_date=current_week_start,
                                shifts=[],
                                total_hours={},
                                created_by=user.get('employee_id')
                            )
                        
                        if schedule:
                            request_type = request_data.get('request_type', 'availability')
                            
                            # Convert pending locked shifts to approved, or create new approved shifts if none exist
                            updated_shifts = []
                            converted_days = set()
                            for shift in schedule.shifts:
                                if shift.id.startswith(f"pending_{request_id}_"):
                                    # Convert to approved locked shift
                                    updated_shift = Shift(
                                        id=shift.id.replace(f"pending_{request_id}_", f"locked_{request_id}_"),
                                        employee_id=shift.employee_id,
                                        day_of_week=shift.day_of_week,
                                        start_time=shift.start_time,
                                        end_time=shift.end_time,
                                        job_type=shift.job_type,
                                        location=shift.location,
                                        hours=shift.hours,
                                        locked=True,
                                        locked_availability_type=shift.locked_availability_type,
                                        is_event=shift.is_event
                                    )
                                    updated_shifts.append(updated_shift)
                                    converted_days.add(shift.day_of_week)
                                    print(f"[APPROVAL] Converted pending locked shift to approved for {employee_id} on {shift.day_of_week}")
                                else:
                                    updated_shifts.append(shift)
                            
                            schedule.shifts = updated_shifts
                            
                            # If no pending shifts were converted, create new locked shifts directly
                            week_end = current_week_start + timedelta(days=6)
                            current_date = max(current_week_start, start_date)
                            while current_date <= min(week_end, end_date):
                                day_name = day_map[current_date.weekday()]
                                if day_name in days_of_week and day_name not in converted_days:
                                    # Check if a locked shift already exists for this employee/day
                                    existing_locked = next(
                                        (s for s in schedule.shifts 
                                         if s.employee_id == employee_id and s.day_of_week == day_name and s.locked),
                                        None
                                    )
                                    if not existing_locked:
                                        if request_type == 'day_off':
                                            shift_start = '00:00'
                                            shift_end = '23:59'
                                            shift_location = 'day off'
                                            shift_hours = 0
                                            locked_type = 'Day Off'
                                        else:
                                            shift_start = request_data.get('start_time', '00:00')
                                            shift_end = request_data.get('end_time', '23:59')
                                            shift_location = None
                                            shift_hours = 0
                                            locked_type = request_type.capitalize()
                                        
                                        locked_shift = Shift(
                                            id=f"locked_{request_id}_{day_name}_{employee_id}",
                                            employee_id=employee_id,
                                            day_of_week=day_name,
                                            start_time=shift_start,
                                            end_time=shift_end,
                                            job_type=JobType.IBU_OPS,
                                            location=shift_location,
                                            hours=shift_hours,
                                            locked=True,
                                            locked_availability_type=locked_type,
                                            is_event=False
                                        )
                                        schedule.shifts.append(locked_shift)
                                        print(f"[APPROVAL] Created locked shift directly for {employee_id} on {day_name}")
                                current_date += timedelta(days=1)
                            
                            # Save the updated schedule
                            staging_schedules = [s for s in staging_schedules if str(s.get('week_start_date')) != str(current_week_start)]
                            staging_schedules.append(schedule.model_dump())
                            staging_store.set_schedules(staging_schedules, user_id=user.get('employee_id'))
                        
                        current_week_start += timedelta(days=7)
                        
                except Exception as e:
                    print(f"[APPROVAL] Warning: could not update pending locked shifts: {e}")
                    import traceback
                    traceback.print_exc()
        except Exception as e:
            print(f"[APPROVAL] Warning: error in pending locked shift update: {e}")
            import traceback
            traceback.print_exc()

        # Remove manager notifications for this request after approval
        try:
            notifications = staging_store.get_notifications()
            cleaned = [
                n for n in notifications
                if not (
                    n.get('type') == NotificationType.AVAILABILITY_REQUEST and
                    n.get('details', {}).get('request_id') == request_id
                )
            ]
            if len(cleaned) < len(notifications):
                staging_store.set_notifications(cleaned, user_id=user.get('employee_id'))
        except Exception as e:
            print(f"[APPROVAL] Warning: could not clean up manager notifications: {e}")

        # Send notification to employee
        try:
            employee_dict = staging_store.get_employee_by_id(request_data['employee_id'])
            employee = Employee(**employee_dict) if employee_dict else None
            employee_name = employee.name if employee else request_data['employee_id']
            
            # Support both old and new model for notification message
            request_type = request_data.get('request_type', 'availability')
            start_date = request_data.get('start_date', request_data.get('week_start_date', ''))
            end_date = request_data.get('end_date', start_date)
            
            comment_part = f" Manager note: {body.get('comment')}" if body.get('comment') else ""
            days_str = ', '.join(request_data.get('days_of_week', [])) if request_data.get('days_of_week') else 'All days'
            time_str = f"{request_data.get('start_time', '00:00')} - {request_data.get('end_time', '23:59')}" if request_data.get('start_time') else 'All day'
            notification = {
                'id': str(uuid.uuid4()),
                'employee_id': request_data['employee_id'],
                'type': NotificationType.AVAILABILITY_APPROVED,
                'message': f"Your {request_type} request ({start_date} to {end_date}) has been approved.{comment_part}",
                'details': {
                    'request_type': request_type,
                    'start_date': start_date,
                    'end_date': end_date,
                    'days_of_week': days_str,
                    'time_range': time_str,
                    'employee_comment': request_data.get('employee_comment', '')
                },
                'created_at': datetime.now(),
                'read': False
            }
            # Update staging layer
            notifications = staging_store.get_notifications()
            notifications.append(notification)
            staging_store.set_notifications(notifications, user_id=user.get('employee_id'))
            
            # Add to action queue for Excel sync (async, no blocking)
            # No action queue needed - GitHub JSON is single source of truth
        except Exception as e:
            import traceback
            print(f"[API] Warning: could not send notification: {e}")
            traceback.print_exc()

        # Ensure response is JSON-serializable
        response = request_data.copy()
        if isinstance(response.get('created_at'), datetime):
            response['created_at'] = response['created_at'].isoformat()
        if isinstance(response.get('updated_at'), datetime):
            response['updated_at'] = response['updated_at'].isoformat()
        if isinstance(response.get('approved_at'), datetime):
            response['approved_at'] = response['approved_at'].isoformat()
        return response

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[API] Error approving availability request: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error approving request: {str(e)}")

@app.put("/api/availability-requests/{request_id}/reject")
async def reject_availability_request(request_id: str, body: Dict = {}, authorization: str = Header(None)):
    """Reject an availability request"""
    try:
        user = AuthManager.get_current_user(authorization)
        if not user or user.get('role') not in ['manager', 'admin']:
            raise HTTPException(status_code=403, detail="Manager access required")

        # Read from GitHub JSON (single source of truth)
        staging_requests = staging_store.get_availability_requests()
        requests = staging_requests
        
        request_data = next((r for r in requests if r['id'] == request_id), None)

        if not request_data:
            raise HTTPException(status_code=404, detail="Request not found")

        request_data['status'] = AvailabilityRequestStatus.REJECTED
        request_data['manager_comment'] = body.get('comment', '')
        request_data['updated_at'] = datetime.now()

        # Update staging layer first (fast)
        requests = staging_store.get_availability_requests()
        requests = [r if r['id'] != request_id else request_data for r in requests]
        staging_store.set_availability_requests(requests, user_id=user.get('employee_id'))

        # Remove locked shifts for this request (cleanup if it was previously approved)
        try:
            start_date_str = request_data.get('start_date', request_data.get('week_start_date', ''))
            end_date_str = request_data.get('end_date', start_date_str)
            days_of_week = request_data.get('days_of_week', [])
            employee_id = request_data.get('employee_id')
            
            if start_date_str and end_date_str and days_of_week:
                try:
                    start_date = date.fromisoformat(str(start_date_str)[:10])
                    end_date = date.fromisoformat(str(end_date_str)[:10])
                    day_map = {0: 'monday', 1: 'tuesday', 2: 'wednesday', 3: 'thursday', 4: 'friday', 5: 'saturday', 6: 'sunday'}
                    
                    # Process each week in the date range
                    current_week_start = start_date - timedelta(days=start_date.weekday())
                    while current_week_start <= end_date:
                        # Get schedule for this week
                        staging_schedules = staging_store.get_schedules()
                        schedule = None
                        for s in staging_schedules:
                            week_start = s.get('week_start_date')
                            if isinstance(week_start, date):
                                week_start_str = str(week_start)
                            else:
                                week_start_str = week_start
                            if week_start_str == str(current_week_start):
                                schedule = WeeklySchedule(**s)
                                break
                        
                        if schedule:
                            # Remove locked shifts for this request (both pending and approved)
                            original_count = len(schedule.shifts)
                            schedule.shifts = [
                                s for s in schedule.shifts
                                if not (s.locked and (s.id.startswith(f"locked_{request_id}_") or s.id.startswith(f"pending_{request_id}_")))
                            ]
                            removed_count = original_count - len(schedule.shifts)
                            
                            if removed_count > 0:
                                # Save the updated schedule
                                staging_schedules = [s for s in staging_schedules if str(s.get('week_start_date')) != str(current_week_start)]
                                staging_schedules.append(schedule.model_dump())
                                staging_store.set_schedules(staging_schedules, user_id=user.get('employee_id'))
                                print(f"[REJECTION] Removed {removed_count} locked shifts for request {request_id}")
                        
                        current_week_start += timedelta(days=7)
                        
                except Exception as e:
                    print(f"[REJECTION] Warning: could not remove locked shifts: {e}")
                    import traceback
                    traceback.print_exc()
        except Exception as e:
            print(f"[REJECTION] Warning: error in locked shift removal: {e}")
            import traceback
            traceback.print_exc()

        # Remove manager notifications for this request after rejection
        try:
            notifications = staging_store.get_notifications()
            cleaned = [
                n for n in notifications
                if not (
                    n.get('type') == NotificationType.AVAILABILITY_REQUEST and
                    n.get('details', {}).get('request_id') == request_id
                )
            ]
            if len(cleaned) < len(notifications):
                staging_store.set_notifications(cleaned, user_id=user.get('employee_id'))
                print(f"[REJECTION] Removed {len(notifications) - len(cleaned)} manager notifications for request {request_id}")
        except Exception as e:
            print(f"[REJECTION] Warning: could not clean up manager notifications: {e}")

        # Add to action queue for Excel sync (async, no blocking)
        # No action queue needed - GitHub JSON is single source of truth

        # Support both old and new model for notification message
        request_type = request_data.get('request_type', 'availability')
        start_date = request_data.get('start_date', request_data.get('week_start_date', ''))
        end_date = request_data.get('end_date', start_date)

        # Send notification to employee
        try:
            comment_part = f" Reason: {body.get('comment')}" if body.get('comment') else ""
            notification = {
                'id': str(uuid.uuid4()),
                'employee_id': request_data['employee_id'],
                'type': NotificationType.AVAILABILITY_REJECTED,
                'message': f"Your {request_type} request ({start_date} to {end_date}) was not approved.{comment_part}",
                'details': {
                    'request_type': request_type,
                    'start_date': start_date,
                    'end_date': end_date,
                    'days_of_week': ', '.join(request_data.get('days_of_week', [])) if request_data.get('days_of_week') else 'All days',
                    'time_range': f"{request_data.get('start_time', '00:00')} - {request_data.get('end_time', '23:59')}" if request_data.get('start_time') else 'All day',
                    'employee_comment': request_data.get('employee_comment', '')
                },
                'created_at': datetime.now(),
                'read': False
            }
            # Update staging layer
            notifications = staging_store.get_notifications()
            notifications.append(notification)
            staging_store.set_notifications(notifications, user_id=user.get('employee_id'))
            
            # Add to action queue for Excel sync (async, no blocking)
            # No action queue needed - GitHub JSON is single source of truth
        except Exception as e:
            import traceback
            print(f"[API] Warning: could not send notification: {e}")
            traceback.print_exc()

        # Ensure response is JSON-serializable
        response = request_data.copy()
        if isinstance(response.get('created_at'), datetime):
            response['created_at'] = response['created_at'].isoformat()
        if isinstance(response.get('updated_at'), datetime):
            response['updated_at'] = response['updated_at'].isoformat()
        if isinstance(response.get('approved_at'), datetime):
            response['approved_at'] = response['approved_at'].isoformat()
        return response

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[API] Error rejecting availability request: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error rejecting request: {str(e)}")

# ============ Notifications ============

@app.get("/api/notifications")
async def get_employee_notifications(authorization: str = Header(None)):
    """Get notifications for the current user"""
    user = AuthManager.get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Read from GitHub JSON (single source of truth)
    staging_notifications = staging_store.get_notifications()
    user_notifications = [n for n in staging_notifications if n.get('employee_id') == user['employee_id']]
    return user_notifications


@app.get("/api/sync-status/{request_id}")
async def get_request_sync_status(request_id: str, authorization: str = Header(None)):
    """Get the sync status for a specific request"""
    user = AuthManager.get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    status = get_sync_status(request_id)
    if status:
        return {"request_id": request_id, "status": status}
    else:
        return {"request_id": request_id, "status": "unknown"}

@app.put("/api/notifications/{notification_id}/read")
async def mark_notification_as_read(notification_id: str, authorization: str = Header(None)):
    """Mark a notification as read"""
    user = AuthManager.get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Update staging layer
    notifications = staging_store.get_notifications()
    notification_found = False
    for notif in notifications:
        if notif.get('id') == notification_id:
            notif['read'] = True
            notification_found = True
            break
    
    if notification_found:
        staging_store.set_notifications(notifications, user_id=user.get('employee_id'))
        # Add to action queue for Excel sync
        # No action queue needed - GitHub JSON is single source of truth
        return {"success": True}
    
    raise HTTPException(status_code=404, detail="Notification not found")

@app.put("/api/notifications/read-all")
async def mark_all_notifications_as_read(authorization: str = Header(None)):
    """Mark all notifications as read for the current user"""
    user = AuthManager.get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Update staging layer
    notifications = staging_store.get_notifications()
    updated_count = 0
    for notif in notifications:
        if notif.get('employee_id') == user.get('employee_id') and not notif.get('read'):
            notif['read'] = True
            updated_count += 1
    
    if updated_count > 0:
        staging_store.set_notifications(notifications, user_id=user.get('employee_id'))
        # Add to action queue for Excel sync
        # No action queue needed - GitHub JSON is single source of truth
    
    return {"success": True, "updated_count": updated_count}

@app.post("/api/notifications/cleanup-processed")
async def cleanup_processed_notifications(authorization: str = Header(None)):
    """Remove AVAILABILITY_REQUEST notifications for requests that are already approved or rejected"""
    user = AuthManager.get_current_user(authorization)
    if not user or user.get('role') not in ['manager', 'admin']:
        raise HTTPException(status_code=403, detail="Manager access required")
    
    try:
        from datetime import timedelta
        
        # Get all requests to check their status
        requests = staging_store.get_availability_requests()
        processed_request_ids = {
            r['id'] for r in requests 
            if r.get('status') in ['approved', 'rejected', AvailabilityRequestStatus.APPROVED, AvailabilityRequestStatus.REJECTED]
        }
        
        # Get all notifications
        notifications = staging_store.get_notifications()
        
        # Remove AVAILABILITY_REQUEST notifications for processed requests OR older than 7 days
        cutoff_date = datetime.now() - timedelta(days=7)
        cleaned = [
            n for n in notifications
            if not (
                n.get('type') == NotificationType.AVAILABILITY_REQUEST and
                (
                    n.get('details', {}).get('request_id') in processed_request_ids or
                    (isinstance(n.get('created_at'), datetime) and n.get('created_at') < cutoff_date)
                )
            )
        ]
        
        removed_count = len(notifications) - len(cleaned)
        
        if removed_count > 0:
            staging_store.set_notifications(cleaned, user_id=user.get('employee_id'))
            print(f"[CLEANUP] Removed {removed_count} processed/old request notifications")
        
        return {"success": True, "removed_count": removed_count}
    except Exception as e:
        print(f"[CLEANUP] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error cleaning up notifications: {str(e)}")

# ============ Events ============

@app.get("/api/events/list")
async def get_week_events():
    """Get all events"""
    try:
        # Read from GitHub JSON (single source of truth)
        config = staging_store.get_system_config()
        staging_events = config.get('events', [])
        events = [Event(**e) for e in staging_events]
        
        # Convert to dict with string dates
        return [
            {
                "id": e.id,
                "name": e.name,
                "week_start_date": e.week_start_date.isoformat() if isinstance(e.week_start_date, date) else str(e.week_start_date),
                "date": e.date.isoformat() if isinstance(e.date, date) else str(e.date),
                "start_time": e.start_time,
                "end_time": e.end_time,
                "location": e.location,
                "people_needed": e.people_needed,
                "description": e.description,
                "created_by": e.created_by,
                "created_at": e.created_at.isoformat() if isinstance(e.created_at, datetime) else str(e.created_at),
                "updated_at": e.updated_at.isoformat() if e.updated_at and isinstance(e.updated_at, datetime) else str(e.updated_at) if e.updated_at else None
            }
            for e in events
        ]
    except Exception as e:
        print(f"Error in get_week_events: {e}")
        return []

@app.post("/api/events")
async def create_event(event_data: dict, authorization: str = Header(None)):
    """Create a new event"""
    user = require_manager(authorization)
    
    # Auto-generate ID if not provided
    if not event_data.get('id'):
        event_data['id'] = f"event_{uuid.uuid4().hex[:8]}"
    
    # Set created_by and created_at if not provided
    if not event_data.get('created_by'):
        event_data['created_by'] = user['employee_id']
    if not event_data.get('created_at'):
        event_data['created_at'] = datetime.now()
    if 'people_needed' not in event_data:
        event_data['people_needed'] = 0
    
    # Convert string dates to date/datetime objects
    if isinstance(event_data.get('week_start_date'), str):
        event_data['week_start_date'] = date.fromisoformat(event_data['week_start_date'])
    if isinstance(event_data.get('date'), str):
        event_data['date'] = date.fromisoformat(event_data['date'])
    
    # Create Event object
    event = Event(**event_data)
    result = save_event(event)
    
    # Update staging layer
    # Events are stored in system config
    config = staging_store.get_system_config()
    if 'events' not in config:
        config['events'] = []
    config['events'].append(result.model_dump())
    staging_store.set_system_config(config, user_id=user.get('employee_id'))
    
    # Add to action queue for Excel sync
    # No action queue needed - GitHub JSON is single source of truth
    
    return result

@app.put("/api/events/{event_id}")
async def update_event(event_id: str, event_data: dict, authorization: str = Header(None)):
    """Update an existing event"""
    user = require_manager(authorization)
    
    # Ensure the event ID matches
    event_data['id'] = event_id
    event_data['updated_at'] = datetime.now()
    
    # Convert string dates to date objects
    if isinstance(event_data.get('week_start_date'), str):
        event_data['week_start_date'] = date.fromisoformat(event_data['week_start_date'])
    if isinstance(event_data.get('date'), str):
        event_data['date'] = date.fromisoformat(event_data['date'])
    
    event = Event(**event_data)
    result = save_event(event)
    
    # Update staging layer
    config = staging_store.get_system_config()
    if 'events' not in config:
        config['events'] = []
    config['events'] = [e if e['id'] != event_id else result.model_dump() for e in config['events']]
    staging_store.set_system_config(config, user_id=user.get('employee_id'))
    
    # Add to action queue for Excel sync
    # No action queue needed - GitHub JSON is single source of truth
    
    return result

@app.get("/api/cron/nightly-excel-commit")
async def nightly_excel_commit():
    """Cron job: Generate Excel from GitHub JSON and commit to GitHub data branch"""
    try:
        import io
        from openpyxl import Workbook
        from datetime import datetime
        
        # Create Excel workbook from GitHub JSON data
        wb = Workbook()
        
        # Employees sheet
        emp_sheet = wb.active
        emp_sheet.title = "Employees"
        emp_sheet.append(["ID", "Name", "Email", "Type", "Max Hours", "Active", "Created At"])
        employees = staging_store.get_employees()
        for emp in employees:
            emp_sheet.append([
                emp.get('id'), emp.get('name'), emp.get('email') or "", emp.get('employee_type'),
                emp.get('max_hours_per_week'), emp.get('active'), emp.get('created_at')
            ])
        
        # Schedules sheet
        schedules = staging_store.get_schedules()
        if schedules:
            sched_sheet = wb.create_sheet("Schedules")
            sched_sheet.append(["Week Start", "Schedule ID", "Employee ID", "Day", "Location", "Start Time", "End Time", "Hours", "Break Provided"])
            for schedule in schedules:
                for shift in schedule.get('shifts', []):
                    sched_sheet.append([
                        schedule.get('week_start_date'), schedule.get('id'), shift.get('employee_id'), shift.get('day_of_week'),
                        shift.get('floor'), shift.get('start_time'), shift.get('end_time'), shift.get('hours'), shift.get('break_provided')
                    ])
        
        # Availabilities sheet
        availabilities = staging_store.get_availabilities()
        if availabilities:
            avail_sheet = wb.create_sheet("Availabilities")
            avail_sheet.append(["ID", "Employee ID", "Week Start", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "Approved", "Submitted At"])
            for avail in availabilities:
                avail_sheet.append([
                    avail.get('id'), avail.get('employee_id'), avail.get('week_start_date'),
                    avail.get('monday'), avail.get('tuesday'), avail.get('wednesday'), avail.get('thursday'),
                    avail.get('friday'), avail.get('saturday'), avail.get('sunday'),
                    avail.get('approved'), avail.get('submitted_at')
                ])
        
        # Availability Requests sheet
        requests = staging_store.get_availability_requests()
        if requests:
            req_sheet = wb.create_sheet("Availability Requests")
            req_sheet.append(["ID", "Employee ID", "Request Type", "Start Date", "End Date", "Days of Week", "Start Time", "End Time", "Status", "Created At"])
            for req in requests:
                req_sheet.append([
                    req.get('id'), req.get('employee_id'), req.get('request_type'),
                    req.get('start_date'), req.get('end_date'), ', '.join(req.get('days_of_week', [])),
                    req.get('start_time'), req.get('end_time'), req.get('status'), req.get('created_at')
                ])
        
        # Notifications sheet
        notifications = staging_store.get_notifications()
        if notifications:
            notif_sheet = wb.create_sheet("Notifications")
            notif_sheet.append(["ID", "Employee ID", "Type", "Message", "Read", "Created At"])
            for notif in notifications:
                notif_sheet.append([
                    notif.get('id'), notif.get('employee_id'), notif.get('type'),
                    notif.get('message'), notif.get('read'), notif.get('created_at')
                ])
        
        # Config sheet
        config_sheet = wb.create_sheet("Config")
        config = staging_store.get_system_config()
        config_sheet.append(["Setting", "Value"])
        for key, value in config.items():
            config_sheet.append([key, str(value)])
        
        # Events sheet
        events = config.get('events', [])
        if events:
            event_sheet = wb.create_sheet("Events")
            event_sheet.append(["ID", "Name", "Week Start Date", "Date", "Start Time", "End Time", "Location", "People Needed", "Description", "Created By"])
            for event in events:
                event_sheet.append([
                    event.get('id'), event.get('name'), event.get('week_start_date'),
                    event.get('date'), event.get('start_time'), event.get('end_time'),
                    event.get('location'), event.get('people_needed'), event.get('description'),
                    event.get('created_by')
                ])
        
        # Save to buffer
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        excel_data = buffer.getvalue()
        
        # Commit to GitHub data branch
        from github_storage import GitHubStorage
        github = GitHubStorage()
        
        commit_message = f"Nightly Excel auto-commit - {datetime.now().isoformat()}"
        success = github.write_file(
            "ibu_schedule.xlsx",
            excel_data,
            commit_message=commit_message
        )
        
        if success:
            return {
                "success": True,
                "message": "Excel file generated and committed to GitHub",
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "message": "Failed to commit Excel file to GitHub",
                "timestamp": datetime.now().isoformat()
            }
    except Exception as e:
        import traceback
        print(f"[CRON] Error in nightly Excel commit: {e}")
        traceback.print_exc()
        return {
            "success": False,
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.delete("/api/events/{event_id}")
async def remove_event(event_id: str, authorization: str = Header(None)):
    """Delete an event"""
    user = require_manager(authorization)
    
    if delete_event(event_id):
        # Update staging layer
        config = staging_store.get_system_config()
        if 'events' in config:
            config['events'] = [e for e in config['events'] if e['id'] != event_id]
            staging_store.set_system_config(config, user_id=user.get('employee_id'))
        
        # Add to action queue for Excel sync
        # No action queue needed - GitHub JSON is single source of truth
        
        return {"success": True}
    
    raise HTTPException(status_code=404, detail="Event not found")

# ============ Health Check (simple) ============

@app.get("/api/ping")
async def health_ping():
    return {"status": "healthy", "timestamp": datetime.now()}


@app.get("/api/cache/stats")
async def get_cache_stats():
    """Get cache statistics for monitoring."""
    try:
        import cache_manager
        stats = cache_manager.get_cache_stats()
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/cache/clear")
async def clear_cache(authorization: str = Header(None)):
    """Clear the cache (manager only)."""
    user = require_manager(authorization)
    try:
        import cache_manager
        cache_manager.clear_cache()
        return {
            "success": True,
            "message": "Cache cleared successfully"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/audit-logs")
async def get_audit_logs(
    entity_type: Optional[str] = None,
    user_id: Optional[str] = None,
    operation: Optional[str] = None,
    limit: int = 100,
    authorization: str = Header(None)
):
    """Get audit logs with optional filtering (manager only)."""
    user = require_manager(authorization)
    try:
        import audit_logger
        logs = audit_logger.get_audit_logs(
            entity_type=entity_type,
            user_id=user_id,
            operation=operation,
            limit=limit
        )
        return {
            "success": True,
            "logs": logs,
            "count": len(logs)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/audit-logs/stats")
async def get_audit_log_stats(authorization: str = Header(None)):
    """Get audit log statistics (manager only)."""
    user = require_manager(authorization)
    try:
        import audit_logger
        stats = audit_logger.get_audit_log_stats()
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/audit-logs/flush")
async def flush_audit_log(authorization: str = Header(None)):
    """Manually flush the audit log buffer (manager only)."""
    user = require_manager(authorization)
    try:
        import audit_logger
        result = audit_logger.flush_audit_log()
        return {
            "success": result,
            "message": "Audit log flushed" if result else "Failed to flush audit log"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

# ============ Admin: Reset Blob Data ============

@app.post("/api/admin/reset-blob-data")
async def reset_blob_data(authorization: str = Header(None)):
    """Reset blob storage with local JSON data (for clearing stale data)"""
    user = require_manager(authorization)
    
    from storage import blob_put
    from pathlib import Path
    import json
    
    data_dir = Path(__file__).parent / "data"
    json_files = [
        "employees.json",
        "passwords.json",
        "availability_requests.json",
        "events.json",
        "coverage_requirements.json",
        "notifications.json",
    ]
    
    results = {}
    for filename in json_files:
        filepath = data_dir / filename
        if not filepath.exists():
            results[filename] = "skipped (not found)"
            continue
        
        with open(filepath, 'r') as f:
            data = f.read()
        
        success = blob_put(filename, data.encode('utf-8'))
        results[filename] = "success" if success else "failed"
    
    return {"success": True, "results": results}


@app.post("/api/admin/reset-manager-password")
async def reset_manager_password(employee_id: str):
    """TEMPORARY: Reset manager password without authentication (for recovery)"""
    from models import EmployeeType

    employee_dict = staging_store.get_employee_by_id(employee_id)
    if not employee_dict:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    employee = Employee(**employee_dict)
    if employee.employee_type != EmployeeType.MANAGER:
        raise HTTPException(status_code=400, detail="Employee is not a manager")
    
    # Set a default password "admin123" using Excel version
    set_manager_password(employee_id, "admin123")
    
    return {"success": True, "message": f"Password reset for {employee.name}. Default password: admin123"}

@app.post("/api/database/upload-excel")
async def upload_excel_file(
    file: UploadFile = File(...),
    user: Dict = Depends(require_manager)
):
    """Upload and merge Excel file with existing data (managers only)"""
    from excel_store import _invalidate_cache, _get_workbook, _save_workbook
    from openpyxl import load_workbook
    import io
    
    # Validate file type
    if not file.filename.endswith('.xlsx'):
        raise HTTPException(status_code=400, detail="Only .xlsx files are allowed")
    
    # Read file content
    content = await file.read()
    
    # Load uploaded Excel file
    uploaded_wb = load_workbook(io.BytesIO(content))
    
    # Get current workbook
    current_wb = _get_workbook()
    if not current_wb:
        raise HTTPException(status_code=500, detail="Failed to load current workbook")
    
    # Merge logic: preserve employees and passwords, merge schedules
    try:
        # Preserve Employees sheet from current
        if "Employees" in current_wb.sheetnames:
            employees_sheet = current_wb["Employees"]
            # Keep employees as-is
        
        # Preserve PWDs sheet from current
        if "PWDs" in current_wb.sheetnames:
            pwds_sheet = current_wb["PWDs"]
            # Keep passwords as-is
        
        # Merge Schedules from uploaded file
        # Handle both formats: weekly sheets (e.g., "June 15-21") and single "Schedules" sheet
        if "Schedules" in uploaded_wb.sheetnames and "Schedules" in current_wb.sheetnames:
            uploaded_schedules = uploaded_wb["Schedules"]
            current_schedules = current_wb["Schedules"]
            
            # Check if uploaded has data (rows beyond header)
            has_data = any(cell.value for row in uploaded_schedules.iter_rows(min_row=2) for cell in row)
            
            if has_data:
                # Clear current schedules (except header)
                for row in list(current_schedules.iter_rows(min_row=2)):
                    for cell in row:
                        cell.value = None
                
                # Copy uploaded schedules
                for row in uploaded_schedules.iter_rows(min_row=2):
                    for cell in row:
                        current_schedules.cell(row=cell.row, column=cell.column, value=cell.value)
        
        # Always process weekly sheets if they exist (takes precedence over Schedule_ sheets)
        weekly_sheets = [s for s in uploaded_wb.sheetnames if not s.startswith('Schedule_') and s not in ['PWDs', 'Employees', 'Schedules', 'Availability']]
        print(f"[MERGE] Found {len(weekly_sheets)} weekly sheets to process: {weekly_sheets[:5]}...")
        if weekly_sheets:
            # Handle weekly sheets format - convert to Schedule_YYYY-MM-DD format with proper parsing
            from datetime import datetime
            import re
            import uuid
            from data_store_excel import get_all_employees
            
            # Get employee name to ID mapping (exact + normalized fallback)
            employees = get_all_employees()
            print(f"[MERGE] Loaded {len(employees)} employees from system")
            exact_map, base_map = build_employee_lookup(employees)
            id_to_name = {emp.id: emp.name for emp in employees}
            unmatched_names = set()
            
            # Remove existing Schedule_ sheets from current
            for sheet_name in list(current_wb.sheetnames):
                if sheet_name.startswith('Schedule_'):
                    current_wb.remove(current_wb[sheet_name])
            
            # Convert weekly sheets from uploaded file
            for sheet_name in weekly_sheets:
                print(f"[MERGE] Processing sheet: {sheet_name}")
                try:
                    # Extract week start date from sheet name
                    year = 2026
                    month_map = {
                        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
                    }
                    
                    sheet_lower = sheet_name.lower()
                    week_start = None
                    
                    for month_name, month_num in month_map.items():
                        if month_name in sheet_lower:
                            day_match = re.search(r'(\d{1,2})[-\s]+(\d{1,2})', sheet_name)
                            if day_match:
                                start_day = int(day_match.group(1))
                                week_start = datetime(year, month_num, start_day).strftime('%Y-%m-%d')
                                break
                    
                    if not week_start:
                        continue
                    
                    schedule_sheet_name = f"Schedule_{week_start}"
                    print(f"[MERGE] Creating Schedule sheet: {schedule_sheet_name}")
                    
                    # Parse the weekly sheet and convert to Schedule_ format
                    uploaded_sheet = uploaded_wb[sheet_name]
                    
                    # Create new Schedule_ sheet with proper headers
                    new_sheet = current_wb.create_sheet(schedule_sheet_name)
                    new_sheet.append([
                        "Shift_ID", "Employee_ID", "Employee_Name", "Day", 
                        "Start_Time", "End_Time", "Job_Type", "Floor", 
                        "Hours", "Is_Event", "Event_Name", "Locked", 
                        "Locked_Avail_Type", "Location"
                    ])
                    
                    # Parse employee schedules from weekly format
                    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                    day_columns = [1, 3, 5, 7, 9, 11, 13]  # Column indices for each day
                    hour_columns = [2, 4, 6, 8, 10, 12, 14]  # Hour columns
                    
                    for row_idx, row in enumerate(uploaded_sheet.iter_rows(min_row=3, values_only=True), start=3):
                        employee_name = row[0]
                        if not employee_name or str(employee_name).strip().upper() == 'EVENTS':
                            continue
                        
                        employee_name = str(employee_name).strip()
                        employee_id = match_employee_id(employee_name, exact_map, base_map)
                        
                        if not employee_id:
                            unmatched_names.add(employee_name)
                            continue
                        
                        # Use the canonical system name
                        canonical_name = id_to_name.get(employee_id, employee_name)
                        shift_count_for_employee = 0
                        
                        for day_idx, (col_idx, hour_col_idx) in enumerate(zip(day_columns, hour_columns)):
                            if col_idx >= len(row):
                                continue
                            shift_text = row[col_idx]
                            hours = row[hour_col_idx] if hour_col_idx < len(row) else None
                            
                            if not shift_text:
                                continue
                            
                            # Parse all shifts in this cell (may be multiple separated by '/')
                            parsed_shifts = parse_shift_cell(shift_text, hours)
                            
                            for ps in parsed_shifts:
                                shift_id = f"shift_{uuid.uuid4().hex[:8]}"
                                new_sheet.append([
                                    shift_id,
                                    employee_id,
                                    canonical_name,
                                    days[day_idx],
                                    ps['start'],
                                    ps['end'],
                                    'ibu_ops',
                                    None,
                                    ps['hours'],
                                    False,
                                    None,
                                    False,
                                    None,
                                    ps['location']
                                ])
                                shift_count_for_employee += 1
                    print(f"[MERGE] Created {new_sheet.max_row - 1} shifts in {schedule_sheet_name}")
                except Exception as e:
                    print(f"Could not parse sheet {sheet_name}: {e}")
                    continue
            
            if unmatched_names:
                print(f"[UPLOAD] Unmatched employee names (skipped): {sorted(unmatched_names)}")
            print(f"[MERGE] Weekly sheet processing complete. Total Schedule_ sheets now: {len([s for s in current_wb.sheetnames if s.startswith('Schedule_')])}")
        
        # Merge Availabilities from uploaded file
        if "Availability" in uploaded_wb.sheetnames and "Availability" in current_wb.sheetnames:
            uploaded_avail = uploaded_wb["Availability"]
            current_avail = current_wb["Availability"]
            
            # Check if uploaded has data (rows beyond header)
            has_data = any(cell.value for row in uploaded_avail.iter_rows(min_row=2) for cell in row)
            
            if has_data:
                # Clear current availability (except header)
                for row in list(current_avail.iter_rows(min_row=2)):
                    for cell in row:
                        cell.value = None
                
                # Copy uploaded availability
                for row in uploaded_avail.iter_rows(min_row=2):
                    for cell in row:
                        current_avail.cell(row=cell.row, column=cell.column, value=cell.value)
        
        # Save merged workbook
        print(f"[MERGE] Saving workbook with sheets: {current_wb.sheetnames[:10]}...")
        saved = _save_workbook(current_wb)
        current_wb.close()
        uploaded_wb.close()
        
        if not saved:
            raise HTTPException(status_code=500, detail="Failed to save merged workbook")
        print(f"[MERGE] Workbook saved successfully")
        
        # Invalidate cache
        _invalidate_cache()
        
        return {
            "success": True, 
            "message": "Excel file merged successfully. Employees and passwords preserved, schedules and availability updated."
        }
    except Exception as e:
        current_wb.close()
        uploaded_wb.close()
        raise HTTPException(status_code=500, detail=f"Merge failed: {str(e)}")

# Helper functions for parsing shift strings
def normalize_employee_name(name: str) -> str:
    """Normalize an employee name by stripping trailing suffixes (numbers, single letters, role titles)
    and collapsing whitespace. e.g. 'Pablo 2' -> 'pablo', 'Sagar C' -> 'sagar', 'Fran SManager' -> 'fran'."""
    if not name:
        return ""
    n = str(name).strip().lower()
    # Collapse multiple spaces
    n = re.sub(r'\s+', ' ', n)
    # Strip common prefixes like 'intern -', 'inton-'
    n = re.sub(r'^(intern|inton)\s*[-]?\s*', '', n)
    # Strip common role suffixes
    suffixes_to_strip = [
        r'\s+smanager$',
        r'\s+supervisor$',
        r'\s+last\s+day$',
        r'\s+b$',
        r'\s+c$',
        r'\s+\d{1,2}$',
        r'\s+[a-z]$',
    ]
    for suffix in suffixes_to_strip:
        n = re.sub(suffix, '', n)
    return n.strip()

# Manual alias map for spelling differences between Excel and system
EMPLOYEE_NAME_ALIASES = {
    'arnab': 'arnob',
}

def build_employee_lookup(employees):
    """Build exact and normalized name->id lookups from a list of Employee objects.
    Exact match takes precedence; normalized (suffix-stripped) is the fallback."""
    exact = {}
    base = {}
    for emp in employees:
        ename = str(emp.name).strip().lower()
        ename = re.sub(r'\s+', ' ', ename)
        # Exact lookup
        if ename not in exact:
            exact[ename] = emp.id
        # Base (normalized) lookup - prefer lower/original emp_ ids
        norm = normalize_employee_name(emp.name)
        if norm and (norm not in base or str(emp.id) < str(base[norm])):
            base[norm] = emp.id
    return exact, base

def match_employee_id(excel_name: str, exact_map: dict, base_map: dict):
    """Match an Excel employee name to a system employee id using multiple strategies."""
    if not excel_name:
        return None
    raw = re.sub(r'\s+', ' ', str(excel_name).strip().lower())
    # 1. Exact match
    if raw in exact_map:
        return exact_map[raw]
    # 2. Normalized base match
    norm = normalize_employee_name(excel_name)
    norm = EMPLOYEE_NAME_ALIASES.get(norm, norm)
    if norm in base_map:
        return base_map[norm]
    if norm in exact_map:
        return exact_map[norm]
    return None

def _parse_one_time_range(segment: str):
    """Parse a single time range like '9a-5p', '7:45a - 3p', '10a-4:30', '1-1:30'.
    Returns (start_24, end_24, duration_minutes) or (None, None, 0)."""
    seg = segment.lower()
    # Strip break markers like 'b@11:30', '8@11:30', '@12'
    seg = re.sub(r'\S*@\S*', ' ', seg)
    # Find a start-end time range
    m = re.search(
        r'(\d{1,2})(?::(\d{2}))?\s*([ap])?m?\s*-\s*(\d{1,2})(?::(\d{2}))?\s*([ap])?m?',
        seg,
    )
    if not m:
        return None, None, 0
    sh = int(m.group(1)); sm = int(m.group(2)) if m.group(2) else 0; sap = m.group(3)
    eh = int(m.group(4)); em = int(m.group(5)) if m.group(5) else 0; eap = m.group(6)

    def base_24(hour, ap, default_pm=False):
        if ap == 'p':
            return hour + 12 if hour != 12 else 12
        if ap == 'a':
            return 0 if hour == 12 else hour
        # No marker - infer
        if default_pm and hour < 12:
            return hour + 12
        # Heuristic: 1-6 -> pm, 7-11 -> am, 12 -> pm
        if 1 <= hour <= 6:
            return hour + 12
        if hour == 12:
            return 12
        return hour

    start_h = base_24(sh, sap)
    # For end, if no marker, infer pm so that end > start
    if eap:
        end_h = base_24(eh, eap)
    else:
        end_h = base_24(eh, None)
        # If end <= start, bump to pm
        if (end_h * 60 + em) <= (start_h * 60 + sm) and eh < 12:
            end_h = eh + 12
    start_min = start_h * 60 + sm
    end_min = end_h * 60 + em
    duration = end_min - start_min
    if duration <= 0:
        return None, None, 0
    return f"{start_h:02d}:{sm:02d}", f"{end_h:02d}:{em:02d}", duration

def parse_shift_cell(cell_text: str, total_hours):
    """Parse a cell that may contain one or more shifts separated by '/'.
    Returns a list of dicts: {start, end, location, hours}.
    Hours from total_hours are split proportionally by each shift's duration."""
    if not cell_text:
        return []
    text = str(cell_text).strip()
    # Skip non-working markers
    upper = text.upper()
    if upper in ('OFF', 'RO') or upper.startswith('OFF ') or 'LIEU' in upper or upper.startswith('RO '):
        return []

    segments = [s.strip() for s in text.split('/') if s.strip()]
    shifts = []
    for seg in segments:
        start, end, duration = _parse_one_time_range(seg)
        loc = parse_location_from_string(seg)
        if start and end:
            shifts.append({'start': start, 'end': end, 'location': loc, 'duration': duration})
        else:
            # No time in this segment - treat as location modifier for previous shift
            if shifts and loc:
                if not shifts[-1]['location']:
                    shifts[-1]['location'] = loc

    # Distribute total_hours proportionally by duration
    try:
        total = float(total_hours) if total_hours not in (None, '') else None
    except (ValueError, TypeError):
        total = None

    total_duration = sum(s['duration'] for s in shifts) or 0
    for s in shifts:
        if total is not None and total_duration > 0:
            s['hours'] = round(total * (s['duration'] / total_duration), 2)
        else:
            s['hours'] = round(s['duration'] / 60.0, 2)
    return shifts

def parse_shift_time_from_string(shift_str: str) -> tuple:
    """Backward-compatible single-range parser."""
    start, end, _ = _parse_one_time_range(str(shift_str))
    return start, end

def parse_location_from_string(shift_str: str) -> str:
    """Parse location from shift string like '8a-3p INVENTORY' or '12p-7p f6 CC'"""
    shift_lower = shift_str.lower()
    
    # Check for common location patterns (order matters - more specific first)
    if 'offsite' in shift_lower:
        return 'offsite'
    elif 'inventory' in shift_lower:
        return 'inventory'
    elif 'f6' in shift_lower or '6th' in shift_lower or 'sixth' in shift_lower:
        return 'sixth_floor'
    elif 'f2' in shift_lower or '2nd' in shift_lower or 'second' in shift_lower:
        return 'second_floor'
    elif 'ground' in shift_lower or re.search(r'\bgr\b', shift_lower) or 'gf' in shift_lower:
        return 'ground_floor'
    elif 'cc' in shift_lower or 'call center' in shift_lower:
        return 'call_center'
    elif 'cl' in shift_lower or 'closing' in shift_lower:
        return 'closing'
    elif 'event' in shift_lower:
        return 'event'
    
    return None

@app.post("/api/diagnostic/test-saturday-approval")
async def test_saturday_approval():
    """Test approval of the Saturday request to debug the issue"""
    try:
        # Get the Saturday request
        all_requests = get_availability_requests()
        saturday_request = None
        for r in all_requests:
            if r.get('days_of_week') and 'saturday' in [d.lower() for d in r.get('days_of_week', [])]:
                saturday_request = r
                break
        
        if not saturday_request:
            return {"error": "No Saturday request found"}
        
        print(f"[TEST] Found Saturday request: {saturday_request.get('id')}")
        print(f"  Employee ID: {saturday_request.get('employee_id')}")
        print(f"  Date range: {saturday_request.get('start_date')} to {saturday_request.get('end_date')}")
        print(f"  Days of week: {saturday_request.get('days_of_week')}")
        print(f"  Time: {saturday_request.get('start_time')} - {saturday_request.get('end_time')}")
        print(f"  Status: {saturday_request.get('status')}")
        
        # Check if schedule exists for the week
        from datetime import timedelta
        start_date = date.fromisoformat(str(saturday_request.get('start_date'))[:10])
        week_start = start_date - timedelta(days=start_date.weekday())
        
        print(f"[TEST] Week start for Saturday: {week_start}")
        
        # Check staging
        staging_schedules = staging_store.get_schedules()
        schedule = None
        for s in staging_schedules:
            if s.get('week_start_date') == str(week_start):
                schedule = s
                break
        
        if schedule:
            print(f"[TEST] Schedule exists in staging for week {week_start}")
            print(f"  Total shifts: {len(schedule.get('shifts', []))}")
            employee_shifts = [s for s in schedule.get('shifts', []) if s.get('employee_id') == saturday_request.get('employee_id')]
            print(f"  Employee shifts: {len(employee_shifts)}")
            print(f"  Employee shift details: {employee_shifts}")
        else:
            print(f"[TEST] No schedule in staging for week {week_start}")
            # Check Excel
            from data_store_excel import get_schedule_by_week
            schedule_obj = get_schedule_by_week(week_start)
            if schedule_obj:
                print(f"[TEST] Schedule exists in Excel for week {week_start}")
                print(f"  Total shifts: {len(schedule_obj.shifts)}")
                employee_shifts = [s for s in schedule_obj.shifts if s.employee_id == saturday_request.get('employee_id')]
                print(f"  Employee shifts: {len(employee_shifts)}")
            else:
                print(f"[TEST] No schedule in Excel for week {week_start}")
        
        return {
            "request_id": saturday_request.get('id'),
            "employee_id": saturday_request.get('employee_id'),
            "date_range": f"{saturday_request.get('start_date')} to {saturday_request.get('end_date')}",
            "days_of_week": saturday_request.get('days_of_week'),
            "week_start": str(week_start),
            "status": saturday_request.get('status'),
            "schedule_in_staging": schedule is not None,
            "employee_shifts_count": len(employee_shifts) if schedule else 0
        }
    except Exception as e:
        import traceback
        print(f"[TEST] Error: {e}")
        traceback.print_exc()
        return {"error": str(e)}

@app.get("/api/diagnostic/check-week-shifts/{week_start_date}")
async def check_week_shifts(week_start_date: str):
    """Check shifts for a specific week"""
    try:
        from excel_store import _get_workbook, _invalidate_cache
        
        print(f"[DIAGNOSTIC] Checking shifts for week {week_start_date}")
        
        # Get schedule from staging first
        staging_schedules = staging_store.get_schedules()
        print(f"[DIAGNOSTIC] Found {len(staging_schedules)} schedules in staging")
        print(f"[DIAGNOSTIC] Staging week starts: {[s.get('week_start_date') for s in staging_schedules]}")
        
        schedule = None
        source = None
        for s in staging_schedules:
            # Handle both string and date objects
            week_start = s.get('week_start_date')
            if isinstance(week_start, date):
                week_start_str = str(week_start)
            else:
                week_start_str = week_start
            
            if week_start_str == week_start_date:
                schedule = s
                source = "staging"
                print(f"[DIAGNOSTIC] Found schedule in staging for week {week_start_date}")
                break
        
        if not schedule:
            print(f"[DIAGNOSTIC] Schedule not found for week {week_start_date}")
        
        if not schedule:
            return {"error": "No schedule found for this week"}
        
        # Filter shifts for the employee
        employee_id = "emp_1781999606683"
        employee_shifts = [s for s in schedule.get('shifts', []) if s.get('employee_id') == employee_id]
        
        print(f"[DIAGNOSTIC] Source: {source}, Total shifts: {len(schedule.get('shifts', []))}, Employee shifts: {len(employee_shifts)}")
        
        return {
            "week_start_date": week_start_date,
            "source": source,
            "total_shifts": len(schedule.get('shifts', [])),
            "employee_shifts": employee_shifts,
            "employee_shifts_count": len(employee_shifts),
            "all_shifts": schedule.get('shifts', [])
        }
    except Exception as e:
        import traceback
        print(f"[DIAGNOSTIC] Error: {e}")
        traceback.print_exc()
        return {"error": str(e)}

@app.get("/api/diagnostic/schedules-data")
async def diagnostic_schedules_data():
    """Diagnostic endpoint to inspect schedules data in Excel"""
    from excel_store import _get_workbook, get_all_schedules, _invalidate_cache
    
    wb = _get_workbook()
    if not wb:
        return {"error": "Failed to load workbook"}
    
    result = {
        "sheet_names": wb.sheetnames,
        "schedules_data": [],
        "schedule_sheets": {},
        "weekly_sheets": {},
        "parsed_schedules": []
    }
    
    # Check for Schedule_ sheets
    for sheet_name in wb.sheetnames:
        if sheet_name.startswith('Schedule_'):
            sheet = wb[sheet_name]
            rows = []
            for i, row in enumerate(sheet.iter_rows(values_only=True)):
                if i < 5:  # First 5 rows
                    rows.append(list(row))
                elif i == 5:
                    rows.append(["... (truncated)"])
                    break
            result["schedule_sheets"][sheet_name] = {
                "rows": rows,
                "total_rows": sheet.max_row,
                "total_cols": sheet.max_column
            }
    
    # Check for weekly sheets (non-Schedule_, non-PWDs)
    for sheet_name in wb.sheetnames:
        if not sheet_name.startswith('Schedule_') and sheet_name != 'PWDs' and sheet_name != 'Employees':
            sheet = wb[sheet_name]
            rows = []
            for i, row in enumerate(sheet.iter_rows(values_only=True)):
                if i < 10:  # First 10 rows
                    rows.append(list(row))
                elif i == 10:
                    rows.append(["... (truncated)"])
                    break
            result["weekly_sheets"][sheet_name] = {
                "rows": rows,
                "total_rows": sheet.max_row,
                "total_cols": sheet.max_column
            }
    
    if "Schedules" in wb.sheetnames:
        sheet = wb["Schedules"]
        rows = []
        for i, row in enumerate(sheet.iter_rows(values_only=True)):
            if i < 10:  # First 10 rows
                rows.append(list(row))
            elif i == 10:
                rows.append(["... (truncated)"])
                break
        result["schedules_data"] = rows
        result["total_rows"] = sheet.max_row
        result["total_cols"] = sheet.max_column
    
    wb.close()
    
    # Test name matching with sample names from weekly sheets
    from data_store_excel import get_all_employees
    employees = get_all_employees()
    exact_map, base_map = build_employee_lookup(employees)
    test_names = ['Fran', 'Aashima', 'NAHIM ', 'Pablo 2', 'Kavya C', 'Mickaela  C', 'Viviana 3', 'Fran SManager', 'Aashima Supervisor', 'Sagar C', 'Daria C', 'Chinnesha C', 'Anastasia B', 'Iqra B', 'Viviana B', 'Osmaro last day']
    name_test_results = {}
    for name in test_names:
        matched_id = match_employee_id(name, exact_map, base_map)
        norm = normalize_employee_name(name)
        name_test_results[name] = {
            'normalized': norm,
            'matched_id': matched_id,
            'in_exact': norm in exact_map or name.lower().strip() in exact_map,
            'in_base': norm in base_map
        }
    result['name_matching_test'] = name_test_results
    result['system_employees'] = [e.name for e in employees[:10]]  # First 10
    
    # Invalidate cache and try to parse schedules
    _invalidate_cache()
    try:
        schedules = get_all_schedules()
        result["parsed_schedules"] = [
            {
                "week_start_date": str(s.week_start_date),
                "shifts_count": len(s.shifts)
            }
            for s in schedules
        ]
        result["parsed_count"] = len(schedules)
    except Exception as e:
        result["parse_error"] = str(e)
    
    return result

@app.get("/api/diagnostic/github-storage")
async def diagnostic_github_storage():
    """Diagnostic endpoint to verify GitHub storage connectivity"""
    from github_storage import GITHUB_AVAILABLE, GITHUB_TOKEN, GITHUB_REPO, GITHUB_DATA_BRANCH, GITHUB_DATA_FILE
    from github_storage import github_get_file
    
    result = {
        "github_available": GITHUB_AVAILABLE,
        "token_set": bool(GITHUB_TOKEN),
        "repo": GITHUB_REPO,
        "data_branch": GITHUB_DATA_BRANCH,
        "data_file": GITHUB_DATA_FILE,
        "read_test": None,
        "write_test": None,
    }
    
    if GITHUB_AVAILABLE:
        # Test read
        try:
            data = github_get_file()
            result["read_test"] = {
                "success": data is not None,
                "size_bytes": len(data) if data else 0,
            }
        except Exception as e:
            result["read_test"] = {
                "success": False,
                "error": str(e),
            }
        
        # Write test is a dry-run (we don't actually write)
        result["write_test"] = {
            "status": "skipped_dry_run",
            "note": "Write test would require actual data modification. Read test validates connectivity.",
        }
    else:
        result["read_test"] = {
            "success": False,
            "error": "GITHUB_TOKEN not set",
        }
    
    return result

@app.get("/api/diagnostic/password-check/{employee_id}/{password}")
async def diagnostic_password_check(employee_id: str, password: str):
    """Diagnostic endpoint to test password verification"""
    from github_storage import GITHUB_AVAILABLE
    from excel_store import verify_manager_password, manager_has_password, hash_password
    
    result = {
        "github_available": GITHUB_AVAILABLE,
        "employee_id": employee_id,
        "has_password": manager_has_password(employee_id),
        "password_hash": hash_password(password),
        "verification_result": verify_manager_password(employee_id, password),
    }
    return result

@app.post("/api/diagnostic/cleanup-duplicate-schedules")
async def cleanup_duplicate_schedules():
    """Clean up duplicate schedules in staging layer"""
    try:
        staging_schedules = staging_store.get_schedules()
        
        # Group by week_start_date
        schedule_map = {}
        for s in staging_schedules:
            week_start = s.get('week_start_date')
            if week_start not in schedule_map:
                schedule_map[week_start] = []
            schedule_map[week_start].append(s)
        
        # Keep only the schedule with the most shifts for each week
        cleaned_schedules = []
        duplicates_removed = 0
        for week_start, schedules in schedule_map.items():
            if len(schedules) > 1:
                # Sort by shift count descending, keep the one with most shifts
                schedules.sort(key=lambda s: len(s.get('shifts', [])), reverse=True)
                cleaned_schedules.append(schedules[0])
                duplicates_removed += len(schedules) - 1
                print(f"[CLEANUP] Week {week_start}: kept {len(schedules[0].get('shifts', []))} shifts, removed {len(schedules) - 1} duplicates")
            else:
                cleaned_schedules.append(schedules[0])
        
        staging_store.set_schedules(cleaned_schedules)
        
        return {
            "success": True,
            "duplicates_removed": duplicates_removed,
            "schedules_kept": len(cleaned_schedules)
        }
    except Exception as e:
        import traceback
        print(f"[CLEANUP] Error: {e}")
        traceback.print_exc()
        return {"error": str(e)}

@app.get("/api/diagnostic/check-staging")
async def check_staging():
    """Check what's in the staging layer and Excel"""
    try:
        from excel_store import _get_workbook, get_availability_requests
        
        employees_dicts = staging_store.get_employees()
        employees = [Employee(**e) for e in employees_dicts]
        active_employee_ids = {e.id for e in employees}
        
        staging_requests = staging_store.get_availability_requests()
        staging_notifications = staging_store.get_notifications()
        staging_schedules = staging_store.get_schedules()
        
        # Check Excel directly
        excel_requests = get_availability_requests()
        
        # Check Excel notifications directly
        wb = _get_workbook()
        excel_notifications = []
        if wb and 'Notifications' in wb.sheetnames:
            sheet = wb['Notifications']
            for row in range(2, sheet.max_row + 1):
                notif = {
                    'id': sheet.cell(row=row, column=1).value,
                    'employee_id': sheet.cell(row=row, column=2).value,
                    'type': sheet.cell(row=row, column=3).value,
                    'message': sheet.cell(row=row, column=4).value,
                    'read': sheet.cell(row=row, column=5).value,
                    'created_at': sheet.cell(row=row, column=6).value
                }
                if notif['employee_id']:  # Skip empty rows
                    excel_notifications.append(notif)
        
        return {
            "active_employee_ids": list(active_employee_ids),
            "staging_requests_count": len(staging_requests),
            "staging_request_employee_ids": [r.get('employee_id') for r in staging_requests],
            "staging_notifications_count": len(staging_notifications),
            "staging_notification_employee_ids": [n.get('employee_id') for n in staging_notifications],
            "staging_notification_details": staging_notifications,
            "staging_schedules_count": len(staging_schedules),
            "staging_schedules_week_starts": [s.get('week_start_date') for s in staging_schedules],
            "staging_schedules_shift_counts": [{"week": s.get('week_start_date'), "shifts": len(s.get('shifts', []))} for s in staging_schedules],
            "excel_requests_count": len(excel_requests),
            "excel_request_employee_ids": [r.get('employee_id') for r in excel_requests],
            "excel_request_details": [{"id": r.get('id'), "employee_id": r.get('employee_id'), "status": r.get('status'), "days": r.get('days_of_week')} for r in excel_requests],
            "excel_notifications_count": len(excel_notifications),
            "excel_notification_employee_ids": [n.get('employee_id') for n in excel_notifications],
            "excel_notification_details": excel_notifications
        }
    except Exception as e:
        import traceback
        print(f"[DIAGNOSTIC] Error: {e}")
        traceback.print_exc()
        return {"error": str(e)}

@app.post("/api/diagnostic/cleanup-orphaned-records")
async def cleanup_orphaned_records():
    """Clean up availability requests and notifications from deleted employees"""
    try:
        from excel_store import _get_workbook, _save_workbook, get_availability_requests, get_notifications
        
        # Get current employees
        employees_dicts = staging_store.get_employees()
        employees = [Employee(**e) for e in employees_dicts]
        active_employee_ids = {e.id for e in employees}
        print(f"[CLEANUP] Active employee IDs: {active_employee_ids}")
        
        # Clean up staging layer FIRST (frontend reads from here)
        staging_requests = staging_store.get_availability_requests()
        print(f"[CLEANUP] Staging requests before: {len(staging_requests)}")
        print(f"[CLEANUP] Staging request employee IDs: {[r.get('employee_id') for r in staging_requests]}")
        cleaned_staging_requests = [r for r in staging_requests if r.get('employee_id') in active_employee_ids]
        print(f"[CLEANUP] Staging requests after: {len(cleaned_staging_requests)}")
        staging_store.set_availability_requests(cleaned_staging_requests)
        
        staging_notifications = staging_store.get_notifications()
        print(f"[CLEANUP] Staging notifications before: {len(staging_notifications)}")
        cleaned_staging_notifications = [n for n in staging_notifications if n.get('employee_id') in active_employee_ids]
        print(f"[CLEANUP] Staging notifications after: {len(cleaned_staging_notifications)}")
        staging_store.set_notifications(cleaned_staging_notifications)
        
        # Note: Excel cleanup removed - GitHub JSON is now the single source of truth
        
        print(f"[CLEANUP] Staging layer: removed {len(staging_requests) - len(cleaned_staging_requests)} requests, {len(staging_notifications) - len(cleaned_staging_notifications)} notifications")
        
        return {
            "success": True,
            "removed_requests": len(staging_requests) - len(cleaned_staging_requests),
            "removed_notifications": len(staging_notifications) - len(cleaned_staging_notifications)
        }
    except Exception as e:
        import traceback
        print(f"[CLEANUP] Error: {e}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}

@app.get("/api/diagnostic/reset-admin-password")
async def reset_admin_password():
    """Reset admin password to admin123 (emergency fix)"""
    from excel_store import set_manager_password
    set_manager_password('admin_001', 'System Admin', 'admin123')
    return {"success": True, "message": "Admin password reset to admin123"}

@app.get("/api/diagnostic/test-github-write")
async def test_github_write():
    """Test GitHub write by reading the current Excel file and writing it back"""
    from excel_store import _get_workbook, _save_workbook
    from openpyxl import load_workbook
    import io
    
    try:
        # Get current workbook
        wb = _get_workbook()
        if not wb:
            return {"success": False, "error": "Failed to get workbook"}
        
        # Save it (this should trigger GitHub write)
        result = _save_workbook(wb)
        wb.close()
        
        return {"success": result, "message": "Test write completed"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/log-error")
async def log_frontend_error(error_data: dict):
    """Log frontend errors for monitoring"""
    message = f"{error_data.get('type', 'unknown')}: {error_data.get('message', 'no message')}"
    url = error_data.get('url', 'N/A')
    component = error_data.get('component', 'N/A')
    
    print(f"[FRONTEND ERROR] {message}")
    print(f"  URL: {url}")
    print(f"  Method: {error_data.get('method', 'N/A')}")
    print(f"  Status: {error_data.get('status', 'N/A')}")
    
    # Store in log storage
    log_storage.get_log_storage().add_frontend_log(
        message=message,
        level="ERROR",
        url=url,
        component=component
    )
    
    return {"success": True}

# ============ Monitoring Dashboard Endpoints ============

def verify_admin_auth(username: str, password: str) -> bool:
    """Verify admin credentials."""
    return username == "admin" and password == "ibu-admin-secret-2026"

@app.get("/admin/login")
async def admin_login():
    """Serve admin login page."""
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Login - IBU Operations</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
        .login-container { background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); width: 100%; max-width: 400px; }
        h1 { color: #333; margin-bottom: 20px; text-align: center; }
        .form-group { margin-bottom: 20px; }
        label { display: block; color: #666; margin-bottom: 8px; font-weight: 500; }
        input { width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
        input:focus { outline: none; border-color: #007bff; }
        button { width: 100%; padding: 12px; background: #007bff; color: white; border: none; border-radius: 4px; font-size: 14px; font-weight: 500; cursor: pointer; }
        button:hover { background: #0056b3; }
        .error { color: #dc3545; text-align: center; margin-bottom: 20px; padding: 10px; background: #f8d7da; border-radius: 4px; display: none; }
    </style>
</head>
<body>
    <div class="login-container">
        <h1>Admin Login</h1>
        <div id="error" class="error">Invalid credentials</div>
        <form id="loginForm">
            <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" required autofocus>
            </div>
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required>
            </div>
            <button type="submit">Login</button>
        </form>
    </div>
    <script>
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            
            const response = await fetch('/admin/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            
            if (response.ok) {
                window.location.href = '/admin/dashboard';
            } else {
                document.getElementById('error').style.display = 'block';
            }
        });
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)

@app.post("/admin/api/login")
async def admin_api_login(credentials: dict):
    """Handle admin login."""
    username = credentials.get('username')
    password = credentials.get('password')
    
    if not verify_admin_auth(username, password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    response = JSONResponse(content={"success": True})
    response.set_cookie(key="admin_session", value="authenticated", httponly=True, secure=True, samesite="lax")
    return response

@app.get("/admin/logout")
async def admin_logout():
    """Handle admin logout."""
    response = RedirectResponse(url="/admin/login")
    response.delete_cookie(key="admin_session")
    return response

@app.get("/admin/dashboard")
async def admin_dashboard(admin_session: Optional[str] = Cookie(None)):
    """Serve admin dashboard HTML page."""
    if admin_session != "authenticated":
        return RedirectResponse(url="/admin/login")
    
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IBU Operations - System Monitoring Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { color: #333; margin-bottom: 20px; }
        .status-banner { padding: 15px; margin-bottom: 20px; border-radius: 5px; font-weight: bold; }
        .status-banner.green { background: #d4edda; color: #155724; }
        .status-banner.red { background: #f8d7da; color: #721c24; }
        .grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; margin-bottom: 20px; }
        .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .card.full-width { grid-column: 1 / -1; }
        .card h3 { color: #555; margin: 15px 0 10px 0; font-size: 15px; border-bottom: 1px solid #eee; padding-bottom: 5px; }
        .card h3:first-child { margin-top: 0; }
        .card h2 { color: #333; margin-bottom: 15px; font-size: 18px; }
        .status-indicator { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; }
        .status-indicator.green { background: #28a745; }
        .status-indicator.red { background: #dc3545; }
        .card h2 .status-indicator { float: right; margin-top: 4px; }
        .metric { display: flex; justify-content: space-between; margin-bottom: 10px; }
        .metric-label { color: #666; }
        .metric-value { font-weight: bold; color: #333; }
        .log-container { background: #1e1e1e; color: #d4d4d4; padding: 15px; border-radius: 5px; max-height: 360px; overflow-y: auto; font-family: monospace; font-size: 12px; line-height: 1.5; }
        .logout-btn { background: #dc3545; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; text-decoration: none; }
        .logout-btn:hover { background: #c82333; }
        .log-entry { margin-bottom: 5px; padding: 5px; border-bottom: 1px solid #333; }
        .log-entry.error { color: #f8d7da; }
        .log-entry.warning { color: #fff3cd; }
        .log-entry.info { color: #d1ecf1; }
        .timestamp { color: #888; margin-right: 10px; }
        .level { margin-right: 10px; font-weight: bold; }
        .empty-logs { color: #888; font-style: italic; padding: 20px; text-align: center; }
    </style>
</head>
<body>
    <div class="container">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h1>IBU Operations - System Monitoring Dashboard</h1>
            <a href="/admin/logout" class="logout-btn">Logout</a>
        </div>
        <div style="margin-bottom:15px; color:#666; font-size:13px;">Auto-refreshes every 5 minutes &nbsp;|&nbsp; Last updated: <span id="last-updated">-</span></div>
        
        <div class="grid">
            <div class="card">
                <h2>Backend & Frontend Status <span id="backend-frontend-status" class="status-indicator green"></span></h2>
                <h3>Backend</h3>
                <div class="metric">
                    <span class="metric-label">Status:</span>
                    <span class="metric-value"><span class="status-indicator green"></span>Running</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Start Time:</span>
                    <span class="metric-value" id="backend-start-time">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Recent Errors:</span>
                    <span class="metric-value" id="backend-errors">-</span>
                </div>
                <h3>Frontend</h3>
                <div class="metric">
                    <span class="metric-label">Status:</span>
                    <span class="metric-value" id="frontend-status">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Start Time:</span>
                    <span class="metric-value" id="frontend-start-time">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Recent Errors:</span>
                    <span class="metric-value" id="frontend-errors">-</span>
                </div>
            </div>
            
            <div class="card">
                <h2>GitHub Health <span id="github-status" class="status-indicator green"></span></h2>
                <div class="metric">
                    <span class="metric-label">API Status:</span>
                    <span class="metric-value" id="github-api-status">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Branch:</span>
                    <span class="metric-value" id="github-branch">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Rate Limit:</span>
                    <span class="metric-value" id="github-rate-limit">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Last Commit:</span>
                    <span class="metric-value" id="github-last-commit">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">employees.json:</span>
                    <span class="metric-value" id="file-employees">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">schedules.json:</span>
                    <span class="metric-value" id="file-schedules">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">availabilities.json:</span>
                    <span class="metric-value" id="file-availabilities">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">availability_requests.json:</span>
                    <span class="metric-value" id="file-requests">-</span>
                </div>
            </div>
            
            <div class="card">
                <h2>System Metrics <span id="system-status" class="status-indicator green"></span></h2>
                <div class="metric">
                    <span class="metric-label">Cache Hit Rate:</span>
                    <span class="metric-value" id="cache-hit-rate">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Cache Hits:</span>
                    <span class="metric-value" id="cache-hits">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Cache Misses:</span>
                    <span class="metric-value" id="cache-misses">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Active Sessions:</span>
                    <span class="metric-value" id="active-sessions">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Error Rate:</span>
                    <span class="metric-value" id="error-rate">-</span>
                </div>
            </div>
        </div>
        
        <div class="grid">
            <div class="card full-width">
                <h2>Backend Logs (Last 200)</h2>
                <div class="log-container" id="backend-logs">Loading...</div>
            </div>
        </div>
    </div>
    
    <script>
        function formatTimestamp(isoString) {
            const date = new Date(isoString);
            return date.toLocaleString('en-CA', {
                timeZone: 'America/Toronto',
                hour12: false,
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                year: 'numeric',
                month: '2-digit',
                day: '2-digit'
            }).replace(',', '');
        }
        
        function loadDashboard() {
            fetch('/api/health')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('backend-start-time').textContent = formatTimestamp(data.backend_start_time);
                    document.getElementById('backend-errors').textContent = data.backend_has_errors ? 'Yes' : 'No';
                    
                    const frontendStatusEl = document.getElementById('frontend-status');
                    if (data.frontend_has_errors) {
                        frontendStatusEl.innerHTML = '<span class="status-indicator red"></span>Errors';
                    } else {
                        frontendStatusEl.innerHTML = '<span class="status-indicator green"></span>OK';
                    }
                    document.getElementById('frontend-errors').textContent = data.frontend_has_errors ? 'Yes' : 'No';
                    document.getElementById('frontend-start-time').textContent = data.frontend_start_time !== 'N/A' ? formatTimestamp(data.frontend_start_time) : 'N/A';
                    
                    document.getElementById('github-api-status').textContent = data.github_health.api_status;
                    document.getElementById('github-branch').textContent = data.github_health.branch;
                    document.getElementById('github-rate-limit').textContent = data.github_health.rate_limit;
                    document.getElementById('github-last-commit').textContent = data.github_health.last_commit !== 'Unknown' && data.github_health.last_commit !== 'Error fetching' ? formatTimestamp(data.github_health.last_commit) : data.github_health.last_commit;
                    document.getElementById('file-employees').textContent = data.github_health.file_updates['employees.json'] !== 'N/A' && data.github_health.file_updates['employees.json'] !== 'No commits' && data.github_health.file_updates['employees.json'] !== 'Error' ? formatTimestamp(data.github_health.file_updates['employees.json']) : data.github_health.file_updates['employees.json'];
                    document.getElementById('file-schedules').textContent = data.github_health.file_updates['schedules.json'] !== 'N/A' && data.github_health.file_updates['schedules.json'] !== 'No commits' && data.github_health.file_updates['schedules.json'] !== 'Error' ? formatTimestamp(data.github_health.file_updates['schedules.json']) : data.github_health.file_updates['schedules.json'];
                    document.getElementById('file-availabilities').textContent = data.github_health.file_updates['availabilities.json'] !== 'N/A' && data.github_health.file_updates['availabilities.json'] !== 'No commits' && data.github_health.file_updates['availabilities.json'] !== 'Error' ? formatTimestamp(data.github_health.file_updates['availabilities.json']) : data.github_health.file_updates['availabilities.json'];
                    document.getElementById('file-requests').textContent = data.github_health.file_updates['availability_requests.json'] !== 'N/A' && data.github_health.file_updates['availability_requests.json'] !== 'No commits' && data.github_health.file_updates['availability_requests.json'] !== 'Error' ? formatTimestamp(data.github_health.file_updates['availability_requests.json']) : data.github_health.file_updates['availability_requests.json'];
                    document.getElementById('cache-hit-rate').textContent = data.metrics.cache_hit_rate;
                    document.getElementById('cache-hits').textContent = data.metrics.cache_hits;
                    document.getElementById('cache-misses').textContent = data.metrics.cache_misses;
                    document.getElementById('active-sessions').textContent = data.metrics.active_sessions;
                    document.getElementById('error-rate').textContent = data.metrics.error_rate;
                    
                    // Update per-card status indicators
                    const backendFrontendStatus = document.getElementById('backend-frontend-status');
                    if (data.backend_has_errors || data.frontend_has_errors) {
                        backendFrontendStatus.className = 'status-indicator red';
                    } else {
                        backendFrontendStatus.className = 'status-indicator green';
                    }
                    
                    const githubStatus = document.getElementById('github-status');
                    if (data.github_health.api_status !== 'OK') {
                        githubStatus.className = 'status-indicator red';
                    } else {
                        githubStatus.className = 'status-indicator green';
                    }
                    
                    const systemStatus = document.getElementById('system-status');
                    if (data.metrics.error_rate !== "0%") {
                        systemStatus.className = 'status-indicator red';
                    } else {
                        systemStatus.className = 'status-indicator green';
                    }
                    
                    document.getElementById('last-updated').textContent = formatTimestamp(new Date().toISOString());
                });
            
            fetch('/api/logs/backend')
                .then(r => r.json())
                .then(data => {
                    const container = document.getElementById('backend-logs');
                    if (data.logs.length === 0) {
                        container.innerHTML = '<div class="empty-logs">No backend logs yet. Logs will appear as the server processes requests.</div>';
                    } else {
                        // Reverse to show newest logs first
                        const reversedLogs = [...data.logs].reverse();
                        container.innerHTML = reversedLogs.map(log => 
                            `<div class="log-entry ${log.level.toLowerCase()}">
                                <span class="timestamp">${formatTimestamp(log.timestamp)}</span>
                                <span class="level">[${log.level}]</span>
                                <span>${log.message}</span>
                            </div>`
                        ).join('');
                    }
                });
        }
        
        loadDashboard();
        setInterval(loadDashboard, 300000);
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)

@app.get("/api/health")
async def get_health_status():
    """Get overall system health status."""
    import cache_manager
    import auth
    
    logs = log_storage.get_log_storage()
    cache_stats = cache_manager.get_cache_stats()
    
    # GitHub health check
    github_health = {
        "api_status": "OK",
        "rate_limit": f"{cache_stats.get('rate_limit_remaining', 'N/A')}/{cache_stats.get('rate_limit_total', 'N/A')}",
        "last_commit": "Unknown",
        "branch": os.getenv("GITHUB_DATA_BRANCH", "data"),
        "file_updates": {}
    }
    
    try:
        import json_store
        import requests as req
        if json_store.GITHUB_AVAILABLE:
            github_health["api_status"] = "OK"
            # Get last commit time for the data branch
            try:
                commit_url = f"https://api.github.com/repos/{os.getenv('GITHUB_REPO', 'LeviSantosAraujo/IBU-Operations-Schedule')}/commits?sha={os.getenv('GITHUB_DATA_BRANCH', 'data')}&per_page=1"
                cr = req.get(commit_url, headers=json_store._headers(), timeout=5)
                if cr.status_code == 200:
                    commits = cr.json()
                    if commits:
                        github_health["last_commit"] = commits[0].get("commit", {}).get("committer", {}).get("date", "Unknown")
            except:
                github_health["last_commit"] = "Error fetching"
            # Get last update times for key files
            files = ["employees.json", "schedules.json", "availabilities.json", "availability_requests.json"]
            for filename in files:
                try:
                    url = f"https://api.github.com/repos/{os.getenv('GITHUB_REPO', 'LeviSantosAraujo/IBU-Operations-Schedule')}/commits?sha={os.getenv('GITHUB_DATA_BRANCH', 'data')}&path={filename}&per_page=1"
                    resp = req.get(url, headers=json_store._headers(), timeout=5)
                    if resp.status_code == 200:
                        commits = resp.json()
                        if commits:
                            github_health["file_updates"][filename] = commits[0].get("commit", {}).get("committer", {}).get("date", "Unknown")
                        else:
                            github_health["file_updates"][filename] = "No commits"
                except:
                    github_health["file_updates"][filename] = "Error"
        else:
            github_health["api_status"] = "Not Configured"
    except Exception as e:
        github_health["api_status"] = f"Error: {str(e)}"
    
    # Get frontend status
    frontend_logs = logs.get_frontend_logs()
    frontend_has_errors = logs.has_errors("frontend")
    frontend_last_error = frontend_logs[-1].get('message') if frontend_logs else None
    
    # Get frontend start time from GitHub last commit (proxy for deploy time)
    frontend_start_time = github_health.get("last_commit", "N/A")
    
    return {
        "backend_start_time": logs.get_server_start_time(),
        "backend_has_errors": logs.has_errors("backend"),
        "frontend_has_errors": frontend_has_errors,
        "frontend_last_error": frontend_last_error,
        "frontend_start_time": frontend_start_time,
        "github_health": github_health,
        "metrics": {
            "cache_hit_rate": f"{cache_stats.get('hit_rate_percent', 0):.1f}%",
            "cache_hits": cache_stats.get('total_hits', 0),
            "cache_misses": cache_stats.get('total_misses', 0),
            "rate_limit_remaining": cache_stats.get('rate_limit_remaining', 'N/A'),
            "rate_limit_total": cache_stats.get('rate_limit_total', 'N/A'),
            "active_sessions": auth.AuthManager.get_active_session_count(),
            "error_rate": "0%" if not logs.has_errors("backend") else ">0%"
        }
    }

@app.get("/api/logs/backend")
async def get_backend_logs():
    """Get last 200 backend logs."""
    logs = log_storage.get_log_storage().get_backend_logs()
    return {"logs": logs}

@app.get("/api/logs/frontend")
async def get_frontend_logs():
    """Get last 200 frontend logs."""
    logs = log_storage.get_log_storage().get_frontend_logs()
    return {"logs": logs}

if __name__ == "__main__":
    import uvicorn
    # Initialize blob storage for cloud deployment
    if os.getenv("BLOB_READ_WRITE_TOKEN"):
        set_blob_key("ibu_schedule.xlsx")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
