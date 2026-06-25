"""
Excel-based data store for IBU Schedule
- Uses Excel as the primary database
- Maintains the same API as data_store.py for compatibility
- Includes caching for performance
"""

import json
import os
import hashlib
import time
from typing import List, Optional, Dict, Any
from datetime import date, timedelta, datetime
from models import (
    Employee, Availability, WeeklySchedule, SystemConfig, 
    AvailabilityRequest, Event, HourlyCoverageRequirement
)

# Import Excel storage functions
from excel_store import (
    get_all_employees as excel_get_employees,
    save_employee as excel_save_employee,
    get_all_schedules as excel_get_schedules,
    save_schedule as excel_save_schedule,
    get_system_config as excel_get_system_config,
    save_system_config as excel_save_system_config,
    get_availabilities as excel_get_availabilities,
    save_availability as excel_save_availability,
    get_availability_requests as excel_get_availability_requests,
    save_availability_request as excel_save_availability_request,
    get_events as excel_get_events,
    save_event as excel_save_event
)

# In-memory cache for Excel data to improve performance
_MEMORY_CACHE: Dict[str, Any] = {}
# DISABLE CACHING for employees to prevent stale data from reappearing
_CACHE_TTL_SECONDS = 0  # Force fresh load from GitHub every time
_CACHE_TIME: Dict[str, float] = {}

def clear_all_caches():
    """Clear all memory caches"""
    global _MEMORY_CACHE, _CACHE_TIME
    _MEMORY_CACHE.clear()
    _CACHE_TIME.clear()
    print("[CACHE] Cleared all data_store_excel caches")

# Clear cache on module load to force fresh data from GitHub
clear_all_caches()
print("[INIT] Cleared data_store_excel cache on startup")

def _is_cache_valid(key: str) -> bool:
    """Check if cache entry is still valid"""
    if key not in _CACHE_TIME:
        return False
    return (time.time() - _CACHE_TIME[key]) < _CACHE_TTL_SECONDS

def _update_cache(key: str, data: Any):
    """Update cache with new data"""
    _MEMORY_CACHE[key] = data
    _CACHE_TIME[key] = time.time()

# Employee operations
def get_all_employees() -> List[Employee]:
    """Get all employees from Excel (with caching)"""
    cache_key = "employees"
    if cache_key in _MEMORY_CACHE and _is_cache_valid(cache_key):
        print(f"[LOAD] Loaded employees from cache ({len(_MEMORY_CACHE[cache_key])} items)")
        return _MEMORY_CACHE[cache_key]
    
    employees = excel_get_employees()
    _update_cache(cache_key, employees)
    print(f"[LOAD] Loaded employees from Excel ({len(employees)} items)")
    return employees

def get_employee_by_id(employee_id: str) -> Optional[Employee]:
    """Get employee by ID"""
    employees = get_all_employees()
    for emp in employees:
        if emp.id == employee_id:
            return emp
    return None

def save_employee(employee: Employee) -> Employee:
    """Save employee to Excel and update cache"""
    result = excel_save_employee(employee)
    # Invalidate cache
    if "employees" in _MEMORY_CACHE:
        del _MEMORY_CACHE["employees"]
        del _CACHE_TIME["employees"]
    print(f"[SAVE] Saved employee {employee.name} to Excel")
    return result

def delete_employee(employee_id: str) -> bool:
    """Delete employee from Excel"""
    from excel_store import delete_employee as excel_delete_employee
    result = excel_delete_employee(employee_id)
    if result:
        # Invalidate cache
        if "employees" in _MEMORY_CACHE:
            del _MEMORY_CACHE["employees"]
            del _CACHE_TIME["employees"]
        # Clear all caches to ensure fresh load
        clear_all_caches()
    return result

# Availability operations
def get_availabilities(week_start_date: Optional[date] = None, employee_id: Optional[str] = None) -> List[Availability]:
    """Get availabilities from Excel (with caching)"""
    cache_key = f"availabilities_{week_start_date}_{employee_id}"
    if cache_key in _MEMORY_CACHE and _is_cache_valid(cache_key):
        return _MEMORY_CACHE[cache_key]
    
    availabilities = excel_get_availabilities()
    
    if week_start_date:
        availabilities = [a for a in availabilities if a.week_start_date == week_start_date]
    if employee_id:
        availabilities = [a for a in availabilities if a.employee_id == employee_id]
    
    _update_cache(cache_key, availabilities)
    return availabilities

def get_availability_for_week(employee_id: str, week_start_date: date) -> Optional[Availability]:
    """Get availability for specific employee and week"""
    availabilities = get_availabilities(week_start_date, employee_id)
    return availabilities[0] if availabilities else None

def save_availability(availability: Availability) -> Availability:
    """Save availability to Excel and update cache"""
    result = excel_save_availability(availability)
    # Invalidate relevant caches
    keys_to_delete = [k for k in _MEMORY_CACHE.keys() if k.startswith("availabilities_")]
    for key in keys_to_delete:
        del _MEMORY_CACHE[key]
        del _CACHE_TIME[key]
    print(f"[SAVE] Saved availability for {availability.employee_id} to Excel")
    return result

# Schedule operations
def get_all_schedules() -> List[WeeklySchedule]:
    """Get all schedules from Excel (with caching)"""
    cache_key = "schedules"
    if cache_key in _MEMORY_CACHE and _is_cache_valid(cache_key):
        print(f"[LOAD] Loaded schedules from cache ({len(_MEMORY_CACHE[cache_key])} items)")
        return _MEMORY_CACHE[cache_key]
    
    schedules = excel_get_schedules()
    _update_cache(cache_key, schedules)
    print(f"[LOAD] Loaded schedules from Excel ({len(schedules)} items)")
    return schedules

def get_schedule_by_week(week_start_date: date) -> Optional[WeeklySchedule]:
    """Get schedule for specific week"""
    schedules = get_all_schedules()
    for schedule in schedules:
        if schedule.week_start_date == week_start_date:
            return schedule
    return None

def save_schedule(schedule: WeeklySchedule) -> WeeklySchedule:
    """Save schedule to Excel and update cache"""
    print(f"[SAVE] Attempting to save schedule for week {schedule.week_start_date} with {len(schedule.shifts)} shifts")
    try:
        result = excel_save_schedule(schedule)
        print(f"[SAVE] Excel save returned: {result}")
        # Invalidate cache
        if "schedules" in _MEMORY_CACHE:
            del _MEMORY_CACHE["schedules"]
            del _CACHE_TIME["schedules"]
        print(f"[SAVE] Saved schedule for week {schedule.week_start_date} to Excel")
        return result
    except Exception as e:
        print(f"[SAVE] Error saving schedule: {e}")
        import traceback
        traceback.print_exc()
        raise

def delete_schedule(week_start_date: date) -> bool:
    """Delete schedule from Excel"""
    from excel_store import delete_schedule as excel_delete_schedule
    result = excel_delete_schedule(week_start_date)
    if result:
        # Invalidate cache
        if "schedules" in _MEMORY_CACHE:
            del _MEMORY_CACHE["schedules"]
            del _CACHE_TIME["schedules"]
    return result

# System config operations
def get_system_config() -> SystemConfig:
    """Get system config from Excel (with caching)"""
    cache_key = "config"
    if cache_key in _MEMORY_CACHE and _is_cache_valid(cache_key):
        return _MEMORY_CACHE[cache_key]

    config_dict = excel_get_system_config()
    if not config_dict:
        config = SystemConfig()
    else:
        # Ensure notifications is a list, not None or a JSON string
        if config_dict.get('notifications') is None:
            config_dict['notifications'] = []
        elif isinstance(config_dict.get('notifications'), str):
            import json
            try:
                config_dict['notifications'] = json.loads(config_dict['notifications'])
            except (json.JSONDecodeError, ValueError):
                config_dict['notifications'] = []
        # Convert dict to Pydantic model
        config = SystemConfig(**config_dict)
    _update_cache(cache_key, config)
    print(f"[LOAD] Loaded system config from Excel")
    return config

def save_system_config(config: SystemConfig) -> SystemConfig:
    """Save system config to Excel and update cache"""
    config_dict = config.model_dump()

    # Convert datetime and date objects to ISO strings for JSON serialization
    def convert_datetime(obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: convert_datetime(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_datetime(item) for item in obj]
        return obj

    config_dict = convert_datetime(config_dict)

    result = excel_save_system_config(config_dict)
    # Invalidate cache
    if "config" in _MEMORY_CACHE:
        del _MEMORY_CACHE["config"]
        del _CACHE_TIME["config"]
    print(f"[SAVE] Saved system config to Excel")
    return result

# Floor coverage query (same as original)
def get_floor_coverage(floor: str, day_of_week: str, time_slot: str, week_start_date: date) -> Dict:
    """Get floor coverage for a specific time slot"""
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

# Password Management (using Excel's PWDs tab)
def hash_password(password: str) -> str:
    """Hash password using SHA-256 (first 16 chars for storage)"""
    return hashlib.sha256(password.encode()).hexdigest()[:16]

def set_manager_password(employee_id: str, employee_name: str, password: str):
    """Set password for a manager in Excel"""
    from excel_store import set_manager_password as excel_set_password
    excel_set_password(employee_id, employee_name, password)
    print(f"[SAVE] Saved password for manager {employee_name} to Excel")

def verify_manager_password(employee_id: str, password: str) -> bool:
    """Verify manager password from Excel"""
    from excel_store import verify_manager_password as excel_verify_password
    return excel_verify_password(employee_id, password)

def manager_has_password(employee_id: str) -> bool:
    """Check if manager has password set in Excel"""
    from excel_store import manager_has_password as excel_has_password
    return excel_has_password(employee_id)

# Availability Request Operations
def get_availability_requests() -> List[AvailabilityRequest]:
    """Get all availability requests from Excel (with caching)"""
    cache_key = "availability_requests"
    if cache_key in _MEMORY_CACHE and _is_cache_valid(cache_key):
        return _MEMORY_CACHE[cache_key]
    
    requests = excel_get_availability_requests()
    _update_cache(cache_key, requests)
    return requests

def save_availability_request(request) -> bool:
    """Save availability request to Excel and update cache"""
    result = excel_save_availability_request(request)
    # Invalidate cache
    if "availability_requests" in _MEMORY_CACHE:
        del _MEMORY_CACHE["availability_requests"]
        del _CACHE_TIME["availability_requests"]
    request_id = request.id if hasattr(request, 'id') else request.get('id')
    print(f"[SAVE] Saved availability request {request_id} to Excel")
    return result

# Event Operations
def get_events(week_start_date: Optional[date] = None) -> List[Event]:
    """Get events from Excel (with caching)"""
    cache_key = f"events_{week_start_date}"
    if cache_key in _MEMORY_CACHE and _is_cache_valid(cache_key):
        return _MEMORY_CACHE[cache_key]
    
    events = excel_get_events()
    if week_start_date:
        events = [e for e in events if e.date >= week_start_date and e.date < week_start_date + timedelta(days=7)]
    
    _update_cache(cache_key, events)
    return events

def save_event(event: Event) -> Event:
    """Save event to Excel and update cache"""
    result = excel_save_event(event)
    # Invalidate relevant caches
    keys_to_delete = [k for k in _MEMORY_CACHE.keys() if k.startswith("events_")]
    for key in keys_to_delete:
        del _MEMORY_CACHE[key]
        del _CACHE_TIME[key]
    print(f"[SAVE] Saved event {event.id} to Excel")
    return result

def delete_event(event_id: str) -> bool:
    """Delete event from Excel"""
    from excel_store import delete_event as excel_delete_event
    result = excel_delete_event(event_id)
    if result:
        # Invalidate relevant caches
        keys_to_delete = [k for k in _MEMORY_CACHE.keys() if k.startswith("events_")]
        for key in keys_to_delete:
            del _MEMORY_CACHE[key]
            del _CACHE_TIME[key]
    return result

# Week Schedule Dates
def get_all_week_schedule_dates() -> List[date]:
    """Get all week start dates from schedules"""
    schedules = get_all_schedules()
    dates = [s.week_start_date for s in schedules]
    return sorted(dates)

# Coverage Requirements (using Excel's Config tab)
def get_coverage_requirements(week_start_date: date) -> List[HourlyCoverageRequirement]:
    """Get hourly coverage requirements from system config"""
    config = get_system_config()
    return config.hourly_coverage_requirements or []

def save_coverage_requirement(requirement: HourlyCoverageRequirement) -> HourlyCoverageRequirement:
    """Save coverage requirement to system config"""
    config = get_system_config()
    if not config.hourly_coverage_requirements:
        config.hourly_coverage_requirements = []
    
    # Remove existing if updating
    config.hourly_coverage_requirements = [
        r for r in config.hourly_coverage_requirements 
        if r.id != requirement.id
    ]
    config.hourly_coverage_requirements.append(requirement)
    save_system_config(config)
    return requirement

# Notifications (using Excel's Config tab)
def get_notifications(employee_id: str) -> List[Dict]:
    """Get all notifications for an employee from system config"""
    config = get_system_config()
    notifications = config.notifications or []
    employee_notifications = [n for n in notifications if n.get("employee_id") == employee_id]
    return sorted(employee_notifications, key=lambda x: x.get("created_at", ""), reverse=True)

def save_notification(notification: Dict) -> bool:
    """Save notification to system config"""
    config = get_system_config()
    if not config.notifications:
        config.notifications = []

    # Convert datetime fields to ISO strings for JSON serialization
    notification_copy = notification.copy()
    if isinstance(notification_copy.get('created_at'), datetime):
        notification_copy['created_at'] = notification_copy['created_at'].isoformat()

    config.notifications.append(notification_copy)
    save_system_config(config)
    print(f"[SAVE] Saved notification for {notification.get('employee_id')} to Excel")
    return True

def mark_notification_read(notification_id: str) -> bool:
    """Mark notification as read in system config"""
    config = get_system_config()
    if config.notifications:
        for n in config.notifications:
            if n.get("id") == notification_id:
                n["read"] = True
                save_system_config(config)
                return True
    return False

# Initialize with sample data if empty
def initialize_sample_data():
    """Initialize Excel with sample data if empty"""
    if not get_all_employees():
        from excel_store import initialize_sample_data as excel_init
        excel_init()
        print("[INIT] Initialized Excel with sample data")
