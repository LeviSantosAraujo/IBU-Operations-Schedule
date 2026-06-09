from fastapi import FastAPI, HTTPException, Query, Header, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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
    get_all_employees, get_employee_by_id, save_employee, delete_employee,
    get_availabilities, get_availability_for_week, save_availability,
    get_all_schedules, get_schedule_by_week, save_schedule, delete_schedule,
    get_floor_coverage, get_system_config, save_system_config,
    set_excel_file, get_excel_file, ensure_excel_structure,
    set_manager_password, verify_manager_password, manager_has_password,
    initialize_from_excel, get_all_week_schedule_dates,
    initialize_sample_employees, set_blob_key,
    get_coverage_requirements, save_coverage_requirement,
    get_availability_requests, save_availability_request,
    get_notifications, save_notification, mark_notification_read,
    get_events, save_event, delete_event
)
from storage import store_excel_data, excel_file_exists, get_excel_data
from scheduler import SchedulingEngine, generate_schedule
from auth import AuthManager, require_auth, require_manager, require_self_or_manager

# Pydantic models for requests
class LoginRequest(BaseModel):
    employee_id: str
    password: Optional[str] = None

class SetPasswordRequest(BaseModel):
    employee_id: str
    password: str

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

app = FastAPI(title="IBU Operations team schedule", version="2.0.0")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
    """Check if Excel file is configured"""
    try:
        file_path = get_excel_file()
        exists = excel_file_exists()
        has_data = get_excel_data() is not None
        has_employees = len(get_all_employees()) > 0
        return {
            "configured": exists or has_data or has_employees or file_path is not None,
            "file_path": file_path or ("blob_storage" if exists or has_data or has_employees else None),
            "file_exists": exists or has_data or has_employees
        }
    except Exception as e:
        return {
            "configured": False,
            "file_path": None,
            "file_exists": False
        }

def normalize_name(name: str) -> str:
    """Normalize name for duplicate detection"""
    # Remove common suffixes and extra info
    name = name.lower()
    suffixes = [' smanager', ' supervisor', ' ops support', ' training', ' intern', ' temp', ' last day', ' break', ' tr', ' wk1', ' wk2', ' wk3', ' wk4', ' wk5', ' wk6', ' wk7']
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)].strip()
    # Remove numbers at the end
    while name and name[-1].isdigit():
        name = name[:-1].strip()
    return name

def extract_employees_from_schedule(wb) -> List[Dict]:
    """Extract employee names from schedule sheets"""
    employees = []
    seen_normalized = set()
    manager_names = ['fran', 'aashima']  # Known managers (removed Francisco)
    skip_names = ['events', 'total', 'grand total', 'total pt daily hours', 'availabilities', 'availability', '']
    skip_phrases = ['shifts', 'availability', 'blank', 'until', 'after', 'before', '12-3p', '12-3 pm', 'eod', 'anytime', 'all day', 'interns', 'ibu ops']
    
    # Only use the first sheet (most recent week)
    if wb.sheetnames:
        sheet_name = wb.sheetnames[0]
        sheet = wb[sheet_name]
        
        # Look for "EVENTS" header to identify schedule sheets
        events_row = None
        for row in range(1, min(10, sheet.max_row + 1)):
            cell_value = sheet.cell(row=row, column=1).value
            if cell_value and isinstance(cell_value, str) and 'events' in cell_value.lower():
                events_row = row
                break
        
        # If no EVENTS header, try scanning all rows for names
        start_row = events_row + 1 if events_row else 1
        
        # Look for employee names in first column
        for row in range(start_row, min(sheet.max_row + 1, 50)):  # Scan up to 50 rows
            cell_value = sheet.cell(row=row, column=1).value
            if cell_value and isinstance(cell_value, str):
                name = cell_value.strip()
                # Skip empty, header rows and totals
                if name and name.lower() not in skip_names and len(name) > 1:
                    # Skip if it contains skip phrases
                    if any(phrase in name.lower() for phrase in skip_phrases):
                        continue
                    
                    # Skip if it's too long (likely a phrase/instruction)
                    if len(name) > 50:
                        continue
                    
                    # Skip if it contains time patterns
                    if ':' in name and ('am' in name.lower() or 'pm' in name.lower()):
                        continue
                    
                    # Check if it looks like a person name (not a number or code)
                    if not name.replace('.', '').replace('-', '').replace(' ', '').isdigit():
                        # Normalize for duplicate detection
                        normalized = normalize_name(name)
                        
                        # Check if it's a manager
                        is_manager = any(mgr in name.lower() for mgr in manager_names)
                        emp_type = 'manager' if is_manager else 'staff'
                        
                        # Avoid duplicates (check normalized name)
                        if normalized not in seen_normalized:
                            seen_normalized.add(normalized)
                            # Use the cleanest version of the name (remove numbers and suffixes)
                            clean_name = normalized.title()
                            if clean_name.lower() in ['fran', 'aashima']:
                                clean_name = clean_name  # Keep as-is
                            employees.append({
                                'id': f"emp_{len(employees)+1:03d}",
                                'name': clean_name,
                                'type': emp_type
                            })
                            seen_normalized.add(normalized)
    
    return employees

@app.post("/api/excel/upload")
async def upload_excel(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None)
):
    """Upload an Excel file to use as database - managers only, or anyone if no database exists"""
    # Allow upload if no database exists (initial setup)
    if not excel_file_exists():
        pass  # Initial setup
    else:
        user = require_manager(authorization)
    
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    if not file.filename.endswith(('.xlsx', '.xls')):
        print(f"Invalid file extension: {file.filename}")
        raise HTTPException(status_code=400, detail="Only Excel files (.xlsx, .xls) are allowed")
    
    try:
        # Read the file
        file_content = await file.read()
        
        # Parse as Excel
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(file_content))
        
        # Preserve PWDs tab from current file if it exists
        pwd_data = None
        try:
            from excel_store import _get_workbook
            current_wb = _get_workbook()
            if current_wb and 'PWDs' in current_wb.sheetnames:
                pwd_sheet = current_wb['PWDs']
                pwd_data = []
                for row in range(1, pwd_sheet.max_row + 1):
                    row_data = [pwd_sheet.cell(row=row, column=c).value for c in range(1, pwd_sheet.max_column + 1)]
                    pwd_data.append(row_data)
                current_wb.close()
        except Exception as e:
            print(f"Failed to preserve PWDs tab: {e}")
        
        # Clear all system-generated data before importing
        sheets_to_delete = []
        for sheet_name in wb.sheetnames:
            # Delete system-generated schedule tabs
            if sheet_name.startswith('Schedule_'):
                sheets_to_delete.append(sheet_name)
            # Clear system sheets (keep structure, clear data)
            elif sheet_name == 'Events':
                sheet = wb[sheet_name]
                if sheet.max_row > 1:
                    sheet.delete_rows(2, sheet.max_row - 1)
            elif sheet_name == 'Availability_Requests':
                sheet = wb[sheet_name]
                if sheet.max_row > 1:
                    sheet.delete_rows(2, sheet.max_row - 1)
            elif sheet_name == 'Notifications':
                sheet = wb[sheet_name]
                if sheet.max_row > 1:
                    sheet.delete_rows(2, sheet.max_row - 1)
        
        # Delete system-generated schedule tabs
        for sheet_name in sheets_to_delete:
            wb.remove(wb[sheet_name])
        
        # Restore PWDs tab if it was preserved
        if pwd_data:
            if 'PWDs' not in wb.sheetnames:
                wb.create_sheet('PWDs')
            pwd_sheet = wb['PWDs']
            pwd_sheet.delete_rows(1, pwd_sheet.max_row)
            for row_idx, row_data in enumerate(pwd_data, 1):
                for col_idx, cell_value in enumerate(row_data, 1):
                    pwd_sheet.cell(row=row_idx, column=col_idx, value=cell_value)
        
        # Extract employees from schedule
        employees = extract_employees_from_schedule(wb)
        
        # Create or update Employees sheet
        if 'Employees' not in wb.sheetnames:
            wb.create_sheet('Employees')
        
        emp_sheet = wb['Employees']
        emp_sheet.delete_rows(1, emp_sheet.max_row)  # Clear existing
        
        # Add headers matching the expected structure in excel_store.py
        headers = ['ID', 'Name', 'Email', 'Type', 'Max_Hours', 'Preferences', 'Active', 'Created_At']
        for col, header in enumerate(headers, 1):
            emp_sheet.cell(row=1, column=col, value=header)
        
        # Add employee data
        for idx, emp in enumerate(employees, 2):
            emp_sheet.cell(row=idx, column=1, value=emp['id'])
            emp_sheet.cell(row=idx, column=2, value=emp['name'])
            emp_sheet.cell(row=idx, column=3, value='')  # Email
            emp_sheet.cell(row=idx, column=4, value='manager' if emp['type'] == 'manager' else 'employee')
            emp_sheet.cell(row=idx, column=5, value=40 if emp['type'] == 'manager' else 24)
            emp_sheet.cell(row=idx, column=6, value='{}')  # Preferences JSON
            emp_sheet.cell(row=idx, column=7, value='Yes')
            emp_sheet.cell(row=idx, column=8, value=datetime.now().isoformat())
        
        # Save updated workbook
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        updated_content = buffer.read()
        
        # Store in storage - always as ibu_schedule.xlsx so _get_workbook finds it
        try:
            from storage import store_excel_data
            store_excel_data(updated_content, "ibu_schedule.xlsx")
            
            # Also write directly to the uploads folder for _get_workbook local path check
            import pathlib
            upload_path = pathlib.Path(__file__).parent / "uploads" / "ibu_schedule.xlsx"
            upload_path.parent.mkdir(exist_ok=True)
            with open(upload_path, "wb") as f:
                f.write(updated_content)
            
            # Clear workbook cache so next request reads the new file
            from excel_store import _clear_workbook_cache
            _clear_workbook_cache()
        except Exception as e:
            print(f"Storage failed: {e}")
        
        wb.close()
        
        return {
            "message": f"Excel file uploaded successfully with {len(employees)} employees. System data cleared.",
            "filename": file.filename,
            "employees_added": len(employees)
        }
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected upload error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to upload Excel file: {str(e)}")

@app.post("/api/excel/select")
async def select_excel_file(request: ExcelPathRequest):
    """Select an existing Excel file"""
    if not os.path.exists(request.file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    set_excel_file(request.file_path)
    
    return {
        "message": "Excel file selected",
        "file_path": request.file_path
    }

@app.get("/api/excel/download")
async def download_excel():
    """Download the current Excel file from blob storage"""
    from fastapi.responses import StreamingResponse
    import io
    
    # Try to get from blob first
    file_data = download_excel_from_blob()
    if file_data:
        return StreamingResponse(
            io.BytesIO(file_data),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=IBU_Schedule.xlsx"}
        )
    
    # Fall back to local file
    file_path = get_excel_file()
    if file_path and os.path.exists(file_path):
        return FileResponse(file_path, filename="IBU_Schedule.xlsx")
    
    raise HTTPException(status_code=404, detail="No Excel file configured")

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

    # Check if Excel file is configured (in storage or local) or employees can be loaded
    from storage import excel_file_exists
    has_employees = len(get_all_employees()) > 0
    if not excel_file_exists() and not get_excel_file() and not has_employees:
        raise HTTPException(status_code=400, detail="No Excel database configured. Please upload or select an Excel file first.")

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
async def list_employees(active_only: bool = False):
    """List all employees"""
    try:
        employees = get_all_employees()
        if active_only:
            employees = [e for e in employees if e.active]
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
    
    # Create updated employee object
    updated_employee = Employee(
        id=employee_id,
        name=update_data.get("name", existing.name),
        email=update_data.get("email", existing.email),
        employee_type=update_data.get("employee_type", existing.employee_type),
        max_hours_per_week=update_data.get("max_hours_per_week", existing.max_hours_per_week),
        preferences=update_data.get("preferences", existing.preferences),
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
    require_auth(authorization)
    schedule = get_schedule_by_week(week_start_date)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule

@app.post("/api/schedules/generate/{week_start_date}", response_model=WeeklySchedule)
async def auto_generate_schedule(
    week_start_date: date,
    user: Dict = Depends(require_manager)
):
    """Auto-generate a schedule for a week (managers only)"""
    schedule = generate_schedule(week_start_date)
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
    
    if save_availability_request(request_data):
        # Add a locked shift to the schedule for this week/day/employee
        try:
            week_date = date.fromisoformat(str(request_data['week_start_date'])[:10])
            schedule = get_schedule_by_week(week_date)
            if not schedule:
                schedule = WeeklySchedule(
                    id=f"sched_{week_date.isoformat()}",
                    week_start_date=week_date
                )
            
            # Map availability type to time range for the locked shift
            avail_type = request_data.get('availability_type', '')
            avail_time_map = {
                'off': ('00:00', '23:59'),
                'until_12pm': ('00:00', '12:00'),
                'until_3pm': ('00:00', '15:00'),
                'after_330pm': ('15:30', '23:59'),
                '12_3': ('12:00', '15:00'),
                'after_12_eod': ('12:00', '23:59'),
                'before_12_after_330': ('00:00', '23:59'),
                'blank': ('00:00', '23:59'),
            }
            start_t, end_t = avail_time_map.get(avail_type, ('00:00', '23:59'))
            
            locked_shift = Shift(
                id=f"locked_{request_data['id']}",
                employee_id=request_data['employee_id'],
                day_of_week=request_data['day_of_week'],
                start_time=start_t,
                end_time=end_t,
                job_type=JobType.DESK,
                hours=0,
                locked=True,
                locked_availability_type=avail_type,
                color='#D1D5DB',
                location='day off' if avail_type == 'off' else None
            )
            
            # Remove any previous locked shift for same employee/day
            schedule.shifts = [s for s in schedule.shifts if not (
                getattr(s, 'locked', False) and
                s.employee_id == request_data['employee_id'] and
                s.day_of_week == request_data['day_of_week']
            )]
            schedule.shifts.append(locked_shift)
            save_schedule(schedule)
        except Exception as e:
            print(f"Warning: could not add locked shift: {e}")

        # Send notification to employee
        avail_label = request_data.get('availability_type', '').replace('_', ' ')
        comment_part = f" Manager note: {body.get('comment')}" if body.get('comment') else ""
        notification = {
            'id': str(uuid.uuid4()),
            'employee_id': request_data['employee_id'],
            'type': NotificationType.AVAILABILITY_APPROVED,
            'message': f"Your availability request for {request_data['day_of_week']} ({avail_label}) has been approved.{comment_part}",
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
        # Send notification to employee
        notification = {
            'id': str(uuid.uuid4()),
            'employee_id': request_data['employee_id'],
            'type': NotificationType.AVAILABILITY_REJECTED,
            'message': f"Your availability request for {request_data['day_of_week']} ({request_data.get('availability_type','').replace('_',' ')}) was not approved.{' Reason: ' + body.get('comment','') if body.get('comment') else ''}",
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

if __name__ == "__main__":
    import uvicorn
    # Initialize blob storage for cloud deployment
    if os.getenv("BLOB_READ_WRITE_TOKEN"):
        set_blob_key("ibu_schedule.xlsx")
    uvicorn.run(app, host="0.0.0.0", port=8000)
