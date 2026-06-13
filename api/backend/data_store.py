import json
import os
import hashlib
from typing import List, Optional, Dict
from datetime import date, timedelta, datetime
from models import Employee, Availability, WeeklySchedule, SystemConfig, AvailabilityRequest, Event, HourlyCoverageRequirement

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# In-memory fallback for read-only filesystems (Vercel serverless)
_MEMORY_STORE: Dict[str, List[Dict]] = {}
_READ_ONLY = False

# Try to ensure data directory exists
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except OSError:
    _READ_ONLY = True

def _get_path(filename: str) -> str:
    return os.path.join(DATA_DIR, filename)

def _load_json(filename: str) -> List[Dict]:
    print(f"_load_json: Loading {filename}")
    # Try blob storage first (for Vercel persistence)
    try:
        from storage import blob_get
        blob_data = blob_get(filename)
        if blob_data:
            data = json.loads(blob_data.decode('utf-8'))
            _MEMORY_STORE[filename] = list(data)  # Cache in memory
            print(f"_load_json: Loaded {filename} from blob ({len(data)} items)")
            return data
    except Exception as e:
        print(f"_load_json: Blob error for {filename}: {e}")

    # Check in-memory store
    if filename in _MEMORY_STORE:
        print(f"_load_json: Loaded {filename} from memory ({len(_MEMORY_STORE[filename])} items)")
        return list(_MEMORY_STORE[filename])

    # Try disk
    path = _get_path(filename)
    if not os.path.exists(path):
        print(f"_load_json: {filename} not found on disk, returning empty")
        return []
    try:
        with open(path, 'r') as f:
            data = json.load(f)
            _MEMORY_STORE[filename] = list(data)  # Cache in memory
            print(f"_load_json: Loaded {filename} from disk ({len(data)} items)")
            return data
    except Exception as e:
        print(f"_load_json: Disk error for {filename}: {e}")
        return []

def _save_json(filename: str, data: List[Dict]):
    print(f"_save_json: Saving {filename} ({len(data)} items)")
    # Always update memory store
    _MEMORY_STORE[filename] = list(data)

    # Try blob storage (for Vercel persistence)
    try:
        from storage import blob_put
        json_str = json.dumps(data, indent=2, default=str)
        success = blob_put(filename, json_str.encode('utf-8'))
        print(f"_save_json: Blob put for {filename} returned {success}")
    except Exception as e:
        print(f"_save_json: Blob error for {filename}: {e}")

    # Try disk write (will fail silently on Vercel read-only fs)
    if _READ_ONLY:
        print(f"_save_json: Skipping disk write (read-only fs)")
        return
    try:
        path = _get_path(filename)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        print(f"_save_json: Saved {filename} to disk")
    except OSError as e:
        print(f"_save_json: Disk error for {filename}: {e}")
        pass  # Read-only filesystem - blob/memory store is the fallback

# Employee operations
def get_all_employees() -> List[Employee]:
    data = _load_json("employees.json")
    return [Employee(**item) for item in data]

def get_employee_by_id(employee_id: str) -> Optional[Employee]:
    employees = get_all_employees()
    for emp in employees:
        if emp.id == employee_id:
            return emp
    return None

def save_employee(employee: Employee) -> Employee:
    employees = _load_json("employees.json")
    # Update in place to preserve original position
    for i, e in enumerate(employees):
        if e.get("id") == employee.id:
            employees[i] = employee.model_dump()
            _save_json("employees.json", employees)
            return employee
    # If not found, append as new
    employees.append(employee.model_dump())
    _save_json("employees.json", employees)
    return employee

def delete_employee(employee_id: str) -> bool:
    employees = _load_json("employees.json")
    original_count = len(employees)
    employees = [e for e in employees if e.get("id") != employee_id]
    if len(employees) < original_count:
        _save_json("employees.json", employees)
        return True
    return False

# Availability operations
def get_availabilities(week_start_date: Optional[date] = None, employee_id: Optional[str] = None) -> List[Availability]:
    data = _load_json("availabilities.json")
    availabilities = [Availability(**item) for item in data]
    
    if week_start_date:
        availabilities = [a for a in availabilities if a.week_start_date == week_start_date]
    if employee_id:
        availabilities = [a for a in availabilities if a.employee_id == employee_id]
    
    return availabilities

def get_availability_for_week(employee_id: str, week_start_date: date) -> Optional[Availability]:
    availabilities = get_availabilities(week_start_date, employee_id)
    return availabilities[0] if availabilities else None

def save_availability(availability: Availability) -> Availability:
    availabilities = _load_json("availabilities.json")
    # Remove existing if updating
    availabilities = [a for a in availabilities if not (
        a.get("employee_id") == availability.employee_id and 
        a.get("week_start_date") == str(availability.week_start_date)
    )]
    availabilities.append(availability.model_dump())
    _save_json("availabilities.json", availabilities)
    return availability

# Schedule operations
def get_all_schedules() -> List[WeeklySchedule]:
    data = _load_json("schedules.json")
    return [WeeklySchedule(**item) for item in data]

def get_schedule_by_week(week_start_date: date) -> Optional[WeeklySchedule]:
    schedules = get_all_schedules()
    for schedule in schedules:
        if schedule.week_start_date == week_start_date:
            return schedule
    return None

def save_schedule(schedule: WeeklySchedule) -> WeeklySchedule:
    schedules = _load_json("schedules.json")
    # Remove existing if updating
    schedules = [s for s in schedules if s.get("week_start_date") != str(schedule.week_start_date)]
    schedules.append(schedule.model_dump())
    _save_json("schedules.json", schedules)
    return schedule

def delete_schedule(week_start_date: date) -> bool:
    schedules = _load_json("schedules.json")
    original_count = len(schedules)
    schedules = [s for s in schedules if s.get("week_start_date") != str(week_start_date)]
    if len(schedules) < original_count:
        _save_json("schedules.json", schedules)
        return True
    return False

# System config operations
def get_system_config() -> SystemConfig:
    data = _load_json("config.json")
    if data:
        return SystemConfig(**data[0])
    return SystemConfig()

def save_system_config(config: SystemConfig) -> SystemConfig:
    _save_json("config.json", [config.model_dump()])
    return config

# Floor coverage query
def get_floor_coverage(floor: str, day_of_week: str, time_slot: str, week_start_date: date) -> Dict:
    schedule = get_schedule_by_week(week_start_date)
    if not schedule:
        return {"floor": floor, "day_of_week": day_of_week, "time_slot": time_slot, "employee_count": 0, "employees": []}
    
    # Filter shifts for this floor and day
    relevant_shifts = [
        s for s in schedule.shifts 
        if s.floor and s.floor.value == floor and s.day_of_week == day_of_week
    ]
    
    # If time_slot is specific, filter further
    if time_slot in ["morning", "afternoon", "evening"]:
        time_ranges = {
            "morning": ("08:00", "12:00"),
            "afternoon": ("12:00", "17:00"),
            "evening": ("17:00", "22:00")
        }
        start, end = time_ranges.get(time_slot, ("00:00", "23:59"))
        relevant_shifts = [
            s for s in relevant_shifts
            if s.start_time <= end and s.end_time >= start
        ]
    
    employees = []
    seen_employees = set()
    for shift in relevant_shifts:
        if shift.employee_id not in seen_employees:
            emp = get_employee_by_id(shift.employee_id)
            if emp:
                employees.append({
                    "id": emp.id,
                    "name": emp.name,
                    "shift": shift.model_dump()
                })
                seen_employees.add(shift.employee_id)
    
    return {
        "floor": floor,
        "day_of_week": day_of_week,
        "time_slot": time_slot,
        "employee_count": len(employees),
        "employees": employees
    }

# Initialize with sample data if empty
def initialize_sample_data():
    if not get_all_employees():
        sample_employees = [
            Employee(id="emp1", name="Fran", employee_type="manager", max_hours_per_week=80),
            Employee(id="emp2", name="Aashima", employee_type="manager", max_hours_per_week=80),
            Employee(id="emp3", name="Mickaela C", employee_type="employee", max_hours_per_week=24),
            Employee(id="emp4", name="Kavya C", employee_type="employee", max_hours_per_week=24),
            Employee(id="emp5", name="Pablo 2", employee_type="employee", max_hours_per_week=24),
            Employee(id="emp6", name="Viviana 3", employee_type="employee", max_hours_per_week=24),
            Employee(id="emp7", name="Anastasia 3", employee_type="employee", max_hours_per_week=24),
            Employee(id="emp8", name="MEG 3", employee_type="employee", max_hours_per_week=24),
            Employee(id="emp9", name="Achal 2", employee_type="employee", max_hours_per_week=24),
            Employee(id="emp10", name="PRIYANKA 2", employee_type="employee", max_hours_per_week=24),
            Employee(id="emp11", name="Arta C", employee_type="employee", max_hours_per_week=24),
            Employee(id="emp12", name="Taran C", employee_type="employee", max_hours_per_week=24),
            Employee(id="emp13", name="Sagar C", employee_type="employee", max_hours_per_week=24),
            Employee(id="emp14", name="Itshan 3", employee_type="employee", max_hours_per_week=24),
            Employee(id="emp15", name="Arnob 2", employee_type="employee", max_hours_per_week=24),
            Employee(id="emp16", name="Intern-Levi 7", employee_type="intern", max_hours_per_week=15),
            Employee(id="emp17", name="Intern-Himanshu 7", employee_type="intern", max_hours_per_week=15),
        ]
        for emp in sample_employees:
            save_employee(emp)

# ============ Password Management ============

def hash_password(password: str) -> str:
    """Hash password using SHA-256 (first 16 chars for storage)"""
    return hashlib.sha256(password.encode()).hexdigest()[:16]

def set_manager_password(employee_id: str, employee_name: str, password: str):
    """Set password for a manager in JSON storage"""
    passwords = _load_json("passwords.json")
    # Remove existing password for this employee
    passwords = [p for p in passwords if p.get("employee_id") != employee_id]
    # Add new password
    passwords.append({
        "employee_id": employee_id,
        "employee_name": employee_name,
        "password_hash": hash_password(password),
        "role": "manager",
        "last_login": None
    })
    _save_json("passwords.json", passwords)

def verify_manager_password(employee_id: str, password: str) -> bool:
    """Verify manager password"""
    passwords = _load_json("passwords.json")
    for pwd in passwords:
        if pwd.get("employee_id") == employee_id:
            return pwd.get("password_hash") == hash_password(password)
    return False

def manager_has_password(employee_id: str) -> bool:
    """Check if manager has password set"""
    passwords = _load_json("passwords.json")
    return any(p.get("employee_id") == employee_id for p in passwords)

# ============ Availability Request Operations ============

def get_availability_requests() -> List[AvailabilityRequest]:
    """Get all availability requests"""
    data = _load_json("availability_requests.json")
    return [AvailabilityRequest(**item) for item in data]

def save_availability_request(request: AvailabilityRequest) -> AvailabilityRequest:
    """Save an availability request"""
    requests = _load_json("availability_requests.json")
    # Remove existing if updating
    requests = [r for r in requests if r.get("id") != request.id]
    requests.append(request.model_dump())
    _save_json("availability_requests.json", requests)
    return request

# ============ Event Operations ============

def get_events(week_start_date: Optional[date] = None) -> List[Event]:
    """Get events, optionally filtered by week"""
    data = _load_json("events.json")
    events = [Event(**item) for item in data]
    if week_start_date:
        events = [e for e in events if e.date >= week_start_date and e.date < week_start_date + timedelta(days=7)]
    return events

def save_event(event: Event) -> Event:
    """Save an event"""
    events = _load_json("events.json")
    # Remove existing if updating
    events = [e for e in events if e.get("id") != event.id]
    events.append(event.model_dump())
    _save_json("events.json", events)
    return event

def delete_event(event_id: str) -> bool:
    """Delete an event"""
    events = _load_json("events.json")
    original_count = len(events)
    events = [e for e in events if e.get("id") != event_id]
    if len(events) < original_count:
        _save_json("events.json", events)
        return True
    return False

# ============ Week Schedule Dates ============

def get_all_week_schedule_dates() -> List[date]:
    """Get all week start dates from schedules"""
    schedules = _load_json("schedules.json")
    dates = []
    for s in schedules:
        try:
            dates.append(date.fromisoformat(s.get("week_start_date")))
        except:
            pass
    return sorted(dates)

# ============ Coverage Requirements ============

def get_coverage_requirements(week_start_date: date) -> List[HourlyCoverageRequirement]:
    """Get hourly coverage requirements for a week"""
    data = _load_json("coverage_requirements.json")
    requirements = []
    for item in data:
        try:
            req_week = item.get("week_start_date")
            if isinstance(req_week, str):
                req_week = date.fromisoformat(req_week)
            if req_week == week_start_date:
                requirements.append(HourlyCoverageRequirement(**item))
        except:
            pass
    return requirements

def save_coverage_requirement(requirement: HourlyCoverageRequirement) -> HourlyCoverageRequirement:
    """Save a coverage requirement"""
    requirements = _load_json("coverage_requirements.json")
    # Remove existing if updating
    requirements = [r for r in requirements if r.get("id") != requirement.id]
    requirements.append(requirement.model_dump())
    _save_json("coverage_requirements.json", requirements)
    return requirement

# ============ Notifications ============

def get_notifications(employee_id: str) -> List[Dict]:
    """Get all notifications for an employee"""
    data = _load_json("notifications.json")
    notifications = [n for n in data if n.get("employee_id") == employee_id]
    return sorted(notifications, key=lambda x: x.get("created_at", ""), reverse=True)

def save_notification(notification: Dict) -> bool:
    """Save a notification"""
    notifications = _load_json("notifications.json")
    notifications.append(notification)
    _save_json("notifications.json", notifications)
    return True

def mark_notification_read(notification_id: str) -> bool:
    """Mark a notification as read"""
    notifications = _load_json("notifications.json")
    for n in notifications:
        if n.get("id") == notification_id:
            n["read"] = True
            _save_json("notifications.json", notifications)
            return True
    return False
