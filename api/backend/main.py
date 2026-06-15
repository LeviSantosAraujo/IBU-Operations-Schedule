# IBU Operations Schedule API
# GitHub persistence enabled - data stored in data branch
from fastapi import FastAPI, HTTPException, Query, Header, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from typing import List, Optional, Dict
from datetime import date, datetime
import uuid
import os
import shutil
import io
from pathlib import Path
from pydantic import BaseModel

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
    get_all_employees, get_employee_by_id, save_employee, delete_employee,
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
from storage import store_excel_data, excel_file_exists, get_excel_data
from scheduler import SchedulingEngine, generate_schedule
from auth import AuthManager, require_auth, require_manager, require_self_or_manager
from openpyxl import load_workbook

# Pydantic models for requests
class LoginRequest(BaseModel):
    employee_id: str
    password: Optional[str] = None

class SetPasswordRequest(BaseModel):
    employee_id: str
    password: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: do not load Excel file - all data is served from JSON/blob storage"""
    _clear_workbook_cache()
    print("[STARTUP] Server starting - using JSON/blob storage for all data")
    yield
    _clear_workbook_cache()

class ExcelPathRequest(BaseModel):
    file_path: str

# Global state
CURRENT_EXCEL_FILE: Optional[str] = None
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
    allow_origins=["*"],
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

@app.get("/api/health")
async def health_check():
    """Simple health check to verify API is working"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "message": "API is working"
    }

# ============ Excel File Management ============

@app.get("/api/excel/status")
async def excel_status():
    """Check if system is configured (using JSON/blob storage)"""
    try:
        has_employees = len(get_all_employees()) > 0
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
    """Export current JSON data to Excel file for viewing"""
    from fastapi.responses import StreamingResponse
    import io
    from openpyxl import Workbook
    from data_store import get_all_employees, get_all_schedules, get_system_config

    # Create Excel workbook
    wb = Workbook()
    
    # Employees sheet
    emp_sheet = wb.active
    emp_sheet.title = "Employees"
    emp_sheet.append(["ID", "Name", "Email", "Type", "Max Hours", "Active"])
    for emp in get_all_employees():
        emp_sheet.append([
            emp.id, emp.name, emp.email or "", emp.employee_type,
            emp.max_hours_per_week, emp.active
        ])
    
    # Schedules sheet
    if get_all_schedules():
        sched_sheet = wb.create_sheet("Schedules")
        sched_sheet.append(["Week Start", "Employee ID", "Day", "Location", "Start Time", "End Time"])
        for schedule in get_all_schedules():
            for shift in schedule.shifts:
                sched_sheet.append([
                    schedule.week_start_date, shift.employee_id, shift.day_of_week,
                    shift.floor.value if shift.floor else "", shift.start_time, shift.end_time
                ])
    
    # Config sheet
    config_sheet = wb.create_sheet("Config")
    config = get_system_config()
    config_sheet.append(["Setting", "Value"])
    for key, value in config.model_dump().items():
        config_sheet.append([key, str(value)])
    
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
    employee = get_employee_by_id(request.employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
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
    
    employee = get_employee_by_id(request.employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
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
    has_employees = len(get_all_employees()) > 0
    if not has_employees:
        raise HTTPException(status_code=400, detail="No employees configured. Please initialize the system first.")

    employee = get_employee_by_id(request.employee_id)
    
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Managers need password verification
    if employee.employee_type == EmployeeType.MANAGER:
        if manager_has_password(request.employee_id):
            if not request.password:
                raise HTTPException(status_code=401, detail="Password required for managers")
            if not verify_manager_password(request.employee_id, request.password):
                raise HTTPException(status_code=401, detail="Invalid password")
        # If no password set yet, allow login (first time setup)
    
    token = AuthManager.login(request.employee_id, request.password, get_employee_by_id)
    
    return {
        "token": token,
        "employee": employee,
        "role": employee.employee_type,
        "requires_password_setup": employee.employee_type == EmployeeType.MANAGER and not manager_has_password(request.employee_id)
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

@app.get("/api/employees", response_model=List[Employee])
async def list_employees(active_only: bool = False, authorization: str = Header(None)):
    """List all employees (managers see manager_preferences, employees do not)"""
    try:
        employees = get_all_employees()
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
        if not user or user.get('employee_type') != 'MANAGER':
            for emp in employees:
                emp.manager_preferences = {}
        
        return employees
    except Exception as e:
        print(f"Error loading employees: {e}")
        raise HTTPException(status_code=500, detail=f"Error loading employees: {str(e)}")

@app.get("/api/employees/{employee_id}", response_model=Employee)
async def get_employee(employee_id: str):
    """Get a specific employee"""
    employee = get_employee_by_id(employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    return employee

@app.post("/api/employees", response_model=Employee)
async def create_employee(
    employee: Employee,
    user: Dict = Depends(require_manager)
):
    """Create a new employee (managers only)"""
    if not employee.id:
        employee.id = f"emp_{uuid.uuid4().hex[:8]}"
    return save_employee(employee)

@app.put("/api/employees/{employee_id}", response_model=Employee)
async def update_employee(
    employee_id: str,
    employee_update: EmployeeUpdate,
    user: Dict = Depends(require_self_or_manager)
):
    """Update an employee (managers can edit anyone, employees can edit themselves)"""
    existing = get_employee_by_id(employee_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Build updated employee by merging existing with new values
    update_data = employee_update.model_dump(exclude_unset=True)
    
    # Only managers can update manager_preferences
    if user.get('employee_type') != 'MANAGER' and 'manager_preferences' in update_data:
        del update_data['manager_preferences']
    
    # Managers cannot modify employee-submitted preferences (they can only view them)
    # Employees can modify their own preferences
    if user.get('employee_type') == 'MANAGER' and 'preferences' in update_data:
        del update_data['preferences']
    
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
    
    return save_employee(updated_employee)

@app.delete("/api/employees/{employee_id}")
async def remove_employee(
    employee_id: str,
    user: Dict = Depends(require_manager)
):
    """Delete an employee (managers only)"""
    if delete_employee(employee_id):
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
    
    return get_availabilities(week_start_date, employee_id)

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
    return save_availability(availability)

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
    
    return save_availability(availability)

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
    return get_all_schedules()

@app.get("/api/schedules/{week_start_date}", response_model=WeeklySchedule)
async def get_schedule(
    week_start_date: date,
    authorization: Optional[str] = Header(None)
):
    """Get schedule for a specific week (all authenticated users)"""
    user = require_auth(authorization)
    schedule = get_schedule_by_week(week_start_date)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    # Add approved availabilities to the schedule response
    all_availabilities = get_availabilities()
    approved_availabilities = [a for a in all_availabilities if a.approved and a.week_start_date == week_start_date]
    
    # Filter: managers see all, employees see only their own
    if user.get('employee_type') != 'MANAGER':
        approved_availabilities = [a for a in approved_availabilities if a.employee_id == user.get('employee_id')]
    
    # Add availability requests to the schedule response
    all_requests = get_availability_requests()
    # Filter by week start date
    week_requests = [r for r in all_requests if r.get('week_start_date') == week_start_date]
    # Filter: managers see all, employees see only their own
    if user.get('employee_type') != 'MANAGER':
        week_requests = [r for r in week_requests if r.get('employee_id') == user.get('employee_id')]
    
    # Add availabilities and requests to schedule (this is a dynamic field, not in the model)
    schedule_data = schedule.model_dump()
    schedule_data['approved_availabilities'] = approved_availabilities
    schedule_data['availability_requests'] = week_requests
    
    return schedule_data

@app.post("/api/schedules/generate/{week_start_date}", response_model=WeeklySchedule)
async def auto_generate_schedule(
    week_start_date: date,
    user: Dict = Depends(require_manager)
):
    """Auto-generate a schedule for a week (managers only)"""
    from scheduler import SchedulingEngine

    # Get staffing targets from config
    config = get_system_config()
    staffing_targets = config.get('staffing_targets', {})

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
    print(f"[API] Call center target: {call_center_target}")
    print(f"[API] Location requirements passed to scheduler: {location_requirements}")
    engine = SchedulingEngine()
    schedule = engine.generate_auto_schedule(week_start_date, location_requirements, event_staffing, call_center_target)
    return save_schedule(schedule)

@app.post("/api/schedules", response_model=WeeklySchedule)
async def create_or_update_schedule(
    schedule: WeeklySchedule,
    user: Dict = Depends(require_manager)
):
    """Save a schedule (manual editing) (managers only)"""
    schedule.updated_at = datetime.now()
    return save_schedule(schedule)

@app.put("/api/schedules/{week_start_date}/shifts", response_model=WeeklySchedule)
async def update_schedule_shifts(
    week_start_date: date,
    shifts: List[Shift],
    user: Dict = Depends(require_manager)
):
    """Update shifts for a schedule (drag-drop saves here) (managers only)"""
    schedule = get_schedule_by_week(week_start_date)
    if not schedule:
        schedule = WeeklySchedule(
            id=str(uuid.uuid4()),
            week_start_date=week_start_date
        )
    
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
    
    return save_schedule(schedule)

@app.put("/api/schedules/{week_start_date}/shifts/{shift_id}/break")
async def mark_break_provided(
    week_start_date: date,
    shift_id: str,
    break_provided: bool = True,
    user: Dict = Depends(require_manager)
):
    """Mark a shift's break as provided (managers only)"""
    schedule = get_schedule_by_week(week_start_date)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    shift = next((s for s in schedule.shifts if s.id == shift_id), None)
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    
    shift.break_provided = break_provided
    schedule.updated_at = datetime.now()
    
    return save_schedule(schedule)

@app.post("/api/schedules/{week_start_date}/publish")
async def publish_schedule(
    week_start_date: date,
    user: Dict = Depends(require_manager)
):
    """Publish a schedule (finalize it) (managers only)"""
    schedule = get_schedule_by_week(week_start_date)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    schedule.status = "published"
    save_schedule(schedule)
    return {"message": "Schedule published"}

@app.delete("/api/schedules/{week_start_date}")
async def remove_schedule(
    week_start_date: date,
    user: Dict = Depends(require_manager)
):
    """Delete a schedule (managers only)"""
    if delete_schedule(week_start_date):
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
    schedule = get_schedule_by_week(week_start_date)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    # Clear all shifts and reset total hours
    schedule.shifts = []
    schedule.total_hours = {}
    save_schedule(schedule)
    return {"message": "Schedule cleared"}

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
    schedule = get_schedule_by_week(week_start_date)
    employees = get_all_employees()
    
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
    return get_system_config()

@app.put("/api/config")
async def update_config(config: Dict):
    """Update system configuration"""
    return save_system_config(config)

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
    
    config['staffing_targets'] = cleaned_targets
    return save_system_config(config)

# ============ Availability Requests ============

@app.get("/api/availability-requests")
async def get_all_availability_requests(authorization: str = Header(None)):
    """Get all availability requests (managers only)"""
    user = AuthManager.get_current_user(authorization)
    if not user or user.get('role') not in ['manager', 'admin']:
        raise HTTPException(status_code=403, detail="Manager access required")
    
    return get_availability_requests()

@app.get("/api/availability-requests/my")
async def get_my_availability_requests(authorization: str = Header(None)):
    """Get current user's availability requests"""
    user = AuthManager.get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    all_requests = get_availability_requests()
    my_requests = [r for r in all_requests if r.get('employee_id') == user.get('employee_id')]
    return my_requests

@app.post("/api/availability-requests")
async def create_availability_request(request: Dict, authorization: str = Header(None)):
    """Create an availability request"""
    user = AuthManager.get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    request['id'] = str(uuid.uuid4())
    request['employee_id'] = user['employee_id']
    request['status'] = AvailabilityRequestStatus.PENDING
    request['created_at'] = datetime.now()
    
    if save_availability_request(request):
        return request
    raise HTTPException(status_code=500, detail="Failed to save request")

@app.put("/api/availability-requests/{request_id}/approve")
async def approve_availability_request(request_id: str, body: Dict = {}, authorization: str = Header(None)):
    """Approve an availability request"""
    user = AuthManager.get_current_user(authorization)
    if not user or user.get('role') not in ['manager', 'admin']:
        raise HTTPException(status_code=403, detail="Manager access required")

    requests = get_availability_requests()
    request_data = next((r for r in requests if r['id'] == request_id), None)

    if not request_data:
        raise HTTPException(status_code=404, detail="Request not found")

    request_data['status'] = AvailabilityRequestStatus.APPROVED
    request_data['manager_comment'] = body.get('comment')
    request_data['updated_at'] = datetime.now()
    request_data['approved_by'] = user.get('employee_id')
    request_data['approved_at'] = datetime.now()

    if save_availability_request(request_data):
        # Add locked shifts for each day in the date range
        try:
            from datetime import timedelta

            # Support both old and new model
            start_date = date.fromisoformat(str(request_data.get('start_date', request_data.get('week_start_date')))[:10])
            end_date = date.fromisoformat(str(request_data.get('end_date', request_data.get('week_start_date')))[:10])
            days_of_week = request_data.get('days_of_week', [request_data.get('day_of_week', '')])
            request_type = request_data.get('request_type', 'availability')

            # Determine time range
            if request_type == 'day_off':
                start_t, end_t = '00:00', '23:59'
                avail_label = 'Day Off'
                color = '#000000'  # Black for day-offs
            else:
                start_t = request_data.get('start_time', '00:00')
                end_t = request_data.get('end_time', '23:59')
                avail_label = f"{start_t} - {end_t}"
                color = '#D1D5DB'

            # Create locked shifts for each date in range
            # Use the actual date's day of week, not the days_of_week array
            current_date = start_date
            day_map = {0: 'monday', 1: 'tuesday', 2: 'wednesday', 3: 'thursday', 4: 'friday', 5: 'saturday', 6: 'sunday'}

            while current_date <= end_date:
                day_name = day_map[current_date.weekday()]
                # Get or create schedule for this week
                week_start = current_date - timedelta(days=current_date.weekday())
                schedule = get_schedule_by_week(week_start)
                if not schedule:
                    schedule = WeeklySchedule(
                        id=f"sched_{week_start.isoformat()}",
                        week_start_date=week_start
                    )

                # Calculate hours (0 for day off, calculated for regular shifts)
                if request_type == 'day_off':
                    hours = 0.0
                else:
                    start_h, start_m = map(int, start_t.split(':'))
                    end_h, end_m = map(int, end_t.split(':'))
                    hours = (end_h + end_m / 60) - (start_h + start_m / 60)
                    if hours < 0:
                        hours += 24

                locked_shift = Shift(
                    id=f"locked_{request_data['id']}_{current_date.isoformat()}",
                    employee_id=request_data['employee_id'],
                    day_of_week=day_name,
                    start_time=start_t,
                    end_time=end_t,
                    job_type=JobType.DESK,
                    hours=hours,
                    locked=True,
                    locked_availability_type=avail_label,
                    color=color,
                    location='day off' if request_type == 'day_off' else None,
                    comment=request_data.get('employee_comment', ''),
                    preferences=request_data.get('preferences')
                )

                # Remove any previous locked shift for same employee/day
                schedule.shifts = [s for s in schedule.shifts if not (
                    getattr(s, 'locked', False) and
                    s.employee_id == request_data['employee_id'] and
                    s.day_of_week == day_name
                )]
                schedule.shifts.append(locked_shift)
                save_schedule(schedule)

                current_date += timedelta(days=1)
        except Exception as e:
            import traceback
            print(f"Warning: could not add locked shift: {e}")
            traceback.print_exc()

        # Send notification to employee
        comment_part = f" Manager note: {body.get('comment')}" if body.get('comment') else ""
        notification = {
            'id': str(uuid.uuid4()),
            'employee_id': request_data['employee_id'],
            'type': NotificationType.AVAILABILITY_APPROVED,
            'message': f"Your {request_type} request ({start_date} to {end_date}) has been approved.{comment_part}",
            'created_at': datetime.now(),
            'read': False
        }
        save_notification(notification)
        return request_data

    raise HTTPException(status_code=500, detail="Failed to approve request")

@app.put("/api/availability-requests/{request_id}/reject")
async def reject_availability_request(request_id: str, body: Dict = {}, authorization: str = Header(None)):
    """Reject an availability request"""
    user = AuthManager.get_current_user(authorization)
    if not user or user.get('role') not in ['manager', 'admin']:
        raise HTTPException(status_code=403, detail="Manager access required")

    requests = get_availability_requests()
    request_data = next((r for r in requests if r['id'] == request_id), None)

    if not request_data:
        raise HTTPException(status_code=404, detail="Request not found")

    request_data['status'] = AvailabilityRequestStatus.REJECTED
    request_data['manager_comment'] = body.get('comment', '')
    request_data['updated_at'] = datetime.now()

    if save_availability_request(request_data):
        # Support both old and new model for notification message
        request_type = request_data.get('request_type', 'availability')
        start_date = request_data.get('start_date', request_data.get('week_start_date', ''))
        end_date = request_data.get('end_date', start_date)

        # Send notification to employee
        comment_part = f" Reason: {body.get('comment')}" if body.get('comment') else ""
        notification = {
            'id': str(uuid.uuid4()),
            'employee_id': request_data['employee_id'],
            'type': NotificationType.AVAILABILITY_REJECTED,
            'message': f"Your {request_type} request ({start_date} to {end_date}) was not approved.{comment_part}",
            'created_at': datetime.now(),
            'read': False
        }
        save_notification(notification)
        return request_data
    
    raise HTTPException(status_code=500, detail="Failed to reject request")

# ============ Notifications ============

@app.get("/api/notifications")
async def get_employee_notifications(authorization: str = Header(None)):
    """Get notifications for the current user"""
    user = AuthManager.get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    return get_notifications(user['employee_id'])

@app.put("/api/notifications/{notification_id}/read")
async def mark_notification_as_read(notification_id: str, authorization: str = Header(None)):
    """Mark a notification as read"""
    user = AuthManager.get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    if mark_notification_read(notification_id):
        return {"success": True}
    
    raise HTTPException(status_code=500, detail="Failed to mark notification as read")

# ============ Events ============

@app.get("/api/events/list")
async def get_week_events():
    """Get all events"""
    try:
        events = get_events()
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
    
    return save_event(event)

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
    return save_event(event)

@app.delete("/api/events/{event_id}")
async def remove_event(event_id: str, authorization: str = Header(None)):
    """Delete an event"""
    user = require_manager(authorization)
    
    if delete_event(event_id):
        return {"success": True}
    
    raise HTTPException(status_code=404, detail="Event not found")

# ============ Health Check ============

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now()}

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
    from data_store import set_manager_password
    from models import EmployeeType

    employee = get_employee_by_id(employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    if employee.employee_type != EmployeeType.MANAGER:
        raise HTTPException(status_code=400, detail="Employee is not a manager")
    
    # Set a default password "admin123"
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
        else:
            # Handle weekly sheets format - convert to Schedule_YYYY-MM-DD format
            from datetime import datetime
            from dateutil.parser import parse as parse_date
            
            # Remove existing Schedule_ sheets from current
            for sheet_name in list(current_wb.sheetnames):
                if sheet_name.startswith('Schedule_'):
                    current_wb.remove(current_wb[sheet_name])
            
            # Convert weekly sheets from uploaded file
            for sheet_name in uploaded_wb.sheetnames:
                if sheet_name.startswith('Schedule_'):
                    # Already in correct format, just copy
                    if sheet_name not in current_wb.sheetnames:
                        new_sheet = current_wb.create_sheet(sheet_name)
                        uploaded_sheet = uploaded_wb[sheet_name]
                        for row in uploaded_sheet.iter_rows(values_only=True):
                            new_sheet.append(row)
                else:
                    # Try to parse date from sheet name (e.g., "June 15-21", "June 1-7")
                    try:
                        # Extract year from current date context (assume 2026)
                        year = 2026
                        month_map = {
                            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
                        }
                        
                        # Parse month and day range
                        sheet_lower = sheet_name.lower()
                        for month_name, month_num in month_map.items():
                            if month_name in sheet_lower:
                                # Extract day range
                                import re
                                day_match = re.search(r'(\d{1,2})[-\s]+(\d{1,2})', sheet_name)
                                if day_match:
                                    start_day = int(day_match.group(1))
                                    # Create schedule sheet name
                                    week_start = datetime(year, month_num, start_day).strftime('%Y-%m-%d')
                                    schedule_sheet_name = f"Schedule_{week_start}"
                                    
                                    if schedule_sheet_name not in current_wb.sheetnames:
                                        new_sheet = current_wb.create_sheet(schedule_sheet_name)
                                        uploaded_sheet = uploaded_wb[sheet_name]
                                        for row in uploaded_sheet.iter_rows(values_only=True):
                                            new_sheet.append(row)
                                    break
                    except Exception as e:
                        print(f"Could not parse sheet name {sheet_name}: {e}")
                        continue
        
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
        saved = _save_workbook(current_wb)
        current_wb.close()
        uploaded_wb.close()
        
        if not saved:
            raise HTTPException(status_code=500, detail="Failed to save merged workbook")
        
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

@app.get("/api/diagnostic/schedules-data")
async def diagnostic_schedules_data():
    """Diagnostic endpoint to inspect schedules data in Excel"""
    from excel_store import _get_workbook
    
    wb = _get_workbook()
    if not wb:
        return {"error": "Failed to load workbook"}
    
    result = {
        "sheet_names": wb.sheetnames,
        "schedules_data": [],
        "schedule_sheets": {}
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

if __name__ == "__main__":
    import uvicorn
    # Initialize blob storage for cloud deployment
    if os.getenv("BLOB_READ_WRITE_TOKEN"):
        set_blob_key("ibu_schedule.xlsx")
    uvicorn.run(app, host="0.0.0.0", port=8000)
