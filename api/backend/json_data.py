"""
Model-aware data façade over json_store.

This module provides the same function names/signatures as data_store_excel
to enable a mechanical import swap in main.py and scheduler.py.

All data operations use json_store (GitHub JSON) as the single source of truth.
Excel is export-only.
"""

from typing import List, Dict, Any, Optional
from datetime import date, datetime
from models import (
    Employee, Availability, WeeklySchedule, Shift,
    AvailabilityRequest, SystemConfig, HourlyCoverageRequirement
)
import json_store
from utils import hash_password


# ============ Employee Operations ============

def get_all_employees() -> List[Employee]:
    """Get all employees from json_store as Pydantic models."""
    employees_dict = json_store.get_employees()
    return [Employee(**e) for e in employees_dict]


def get_employee_by_id(employee_id: str) -> Optional[Employee]:
    """Get employee by ID from json_store as Pydantic model."""
    employee_dict = json_store.get_employee_by_id(employee_id)
    if employee_dict:
        return Employee(**employee_dict)
    return None


def save_employee(employee: Employee) -> Employee:
    """Save employee to json_store (upsert)."""
    employees_dict = json_store.get_employees()
    # Convert to dict
    employee_dict = employee.model_dump()
    # Remove existing if updating
    employees_dict = [e for e in employees_dict if e.get("id") != employee.id]
    # Add/update
    employees_dict.append(employee_dict)
    json_store.set_employees(employees_dict, user_id=employee.id)
    return employee


def delete_employee(employee_id: str) -> bool:
    """Delete employee from json_store."""
    employees_dict = json_store.get_employees()
    original_count = len(employees_dict)
    employees_dict = [e for e in employees_dict if e.get("id") != employee_id]
    if len(employees_dict) < original_count:
        json_store.set_employees(employees_dict, user_id=employee_id)
        return True
    return False


# ============ Schedule Operations ============

def get_all_schedules() -> List[WeeklySchedule]:
    """Get all schedules from json_store as Pydantic models."""
    schedules_dict = json_store.get_schedules()
    return [WeeklySchedule(**s) for s in schedules_dict]


def get_schedule_by_week(week_start_date: date) -> Optional[WeeklySchedule]:
    """Get schedule for specific week from json_store."""
    schedules = get_all_schedules()
    for schedule in schedules:
        if schedule.week_start_date == week_start_date:
            return schedule
    return None


def save_schedule(schedule: WeeklySchedule) -> WeeklySchedule:
    """Save schedule to json_store (upsert)."""
    schedules_dict = json_store.get_schedules()
    # Convert to dict
    schedule_dict = schedule.model_dump()
    # Remove existing if updating
    schedules_dict = [s for s in schedules_dict if s.get("week_start_date") != str(schedule.week_start_date)]
    # Add/update
    schedules_dict.append(schedule_dict)
    json_store.set_schedules(schedules_dict, user_id="system")
    return schedule


def delete_schedule(week_start_date: date) -> bool:
    """Delete schedule from json_store."""
    schedules_dict = json_store.get_schedules()
    original_count = len(schedules_dict)
    schedules_dict = [s for s in schedules_dict if s.get("week_start_date") != str(week_start_date)]
    if len(schedules_dict) < original_count:
        json_store.set_schedules(schedules_dict, user_id="system")
        return True
    return False


def get_all_week_schedule_dates() -> List[date]:
    """Get all week start dates from schedules."""
    schedules_dict = json_store.get_schedules()
    dates = []
    for s in schedules_dict:
        week_start = s.get("week_start_date")
        if week_start:
            if isinstance(week_start, str):
                dates.append(date.fromisoformat(week_start))
            elif isinstance(week_start, date):
                dates.append(week_start)
    return sorted(dates)


# ============ System Config Operations ============

def get_system_config() -> SystemConfig:
    """Get system config from json_store as Pydantic model."""
    config_dict = json_store.get_system_config()
    if not config_dict:
        return SystemConfig()
    return SystemConfig(**config_dict)


def save_system_config(config: SystemConfig) -> SystemConfig:
    """Save system config to json_store."""
    config_dict = config.model_dump()
    json_store.set_system_config(config_dict, user_id="system")
    return config


# ============ Availability Request Operations ============

def get_availability_requests() -> List[AvailabilityRequest]:
    """Get availability requests from json_store as Pydantic models."""
    requests_dict = json_store.get_availability_requests()
    return [AvailabilityRequest(**r) for r in requests_dict]


def save_availability_request(request: AvailabilityRequest) -> AvailabilityRequest:
    """Save availability request to json_store (upsert)."""
    requests_dict = json_store.get_availability_requests()
    # Convert to dict
    request_dict = request.model_dump()
    # Remove existing if updating
    requests_dict = [r for r in requests_dict if r.get("id") != request.id]
    # Add/update
    requests_dict.append(request_dict)
    json_store.set_availability_requests(requests_dict, user_id=request.employee_id)
    return request


# ============ Notification Operations ============

def get_notifications(employee_id: str) -> List[Dict]:
    """Get notifications for employee from json_store."""
    notifications_dict = json_store.get_notifications()
    return [n for n in notifications_dict if n.get("employee_id") == employee_id]


def save_notification(notification: Dict) -> bool:
    """Save notification to json_store (append)."""
    notifications_dict = json_store.get_notifications()
    notifications_dict.append(notification)
    json_store.set_notifications(notifications_dict, user_id=notification.get("employee_id"))
    return True


def mark_notification_read(notification_id: str) -> bool:
    """Mark notification as read in json_store."""
    notifications_dict = json_store.get_notifications()
    for notif in notifications_dict:
        if notif.get("id") == notification_id:
            notif["read"] = True
            json_store.set_notifications(notifications_dict, user_id="system")
            return True
    return False


# ============ Coverage Requirements Operations ============

def get_coverage_requirements(week_start_date: Optional[date] = None) -> List[HourlyCoverageRequirement]:
    """Get coverage requirements from json_store as Pydantic models."""
    requirements_dict = json_store.get_coverage_requirements()
    if week_start_date:
        requirements_dict = [r for r in requirements_dict if r.get("week_start_date") == str(week_start_date)]
    return [HourlyCoverageRequirement(**r) for r in requirements_dict]


def save_coverage_requirement(requirement: HourlyCoverageRequirement) -> HourlyCoverageRequirement:
    """Save coverage requirement to json_store (upsert)."""
    requirements_dict = json_store.get_coverage_requirements()
    # Convert to dict
    requirement_dict = requirement.model_dump()
    # Remove existing if updating
    requirements_dict = [r for r in requirements_dict if r.get("id") != requirement.id]
    # Add/update
    requirements_dict.append(requirement_dict)
    json_store.set_coverage_requirements(requirements_dict, user_id="system")
    return requirement


# ============ Floor Coverage Operations ============

def get_floor_coverage(floor: str, day_of_week: str, time_slot: str, week_start_date: date) -> Dict:
    """Get floor coverage from schedule data."""
    schedule = get_schedule_by_week(week_start_date)
    if not schedule:
        return {"floor": floor, "day_of_week": day_of_week, "time_slot": time_slot, "employee_count": 0, "employees": []}

    # Filter shifts for this floor and day
    relevant_shifts = [
        s for s in schedule.shifts
        if s.day_of_week == day_of_week and s.location and floor.lower() in s.location.lower()
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
            if s.start_time >= start and s.end_time <= end
        ]

    employee_ids = list(set(s.employee_id for s in relevant_shifts))
    return {
        "floor": floor,
        "day_of_week": day_of_week,
        "time_slot": time_slot,
        "employee_count": len(employee_ids),
        "employees": employee_ids
    }


# ============ Password Management Operations ============

def set_manager_password(employee_id: str, employee_name: str, password: str):
    """Set password for manager in json_store."""
    passwords_dict = json_store.get_passwords()
    # Check if employee already has password
    for pwd in passwords_dict:
        if pwd.get("employee_id") == employee_id:
            # Update existing
            pwd["password_hash"] = hash_password(password)
            pwd["updated_at"] = datetime.now().isoformat()
            json_store.set_passwords(passwords_dict, user_id=employee_id)
            return

    # Add new entry
    passwords_dict.append({
        "employee_id": employee_id,
        "employee_name": employee_name,
        "password_hash": hash_password(password),
        "role": "manager",
        "updated_at": datetime.now().isoformat()
    })
    json_store.set_passwords(passwords_dict, user_id=employee_id)


def verify_manager_password(employee_id: str, password: str) -> bool:
    """Verify manager password from json_store."""
    passwords_dict = json_store.get_passwords()
    for pwd in passwords_dict:
        if pwd.get("employee_id") == employee_id:
            stored_hash = pwd.get("password_hash")
            return stored_hash == hash_password(password)
    return False


def manager_has_password(employee_id: str) -> bool:
    """Check if manager has set a password in json_store."""
    passwords_dict = json_store.get_passwords()
    for pwd in passwords_dict:
        if pwd.get("employee_id") == employee_id:
            return True
    return False


# ============ Sample Data Initialization ============

def initialize_sample_data():
    """Initialize sample data in json_store if empty."""
    # This is a placeholder - the actual implementation would check if data is empty
    # and populate with sample employees, schedules, etc.
    # For now, we'll just log that this was called.
    print("[INIT] initialize_sample_data called (no-op in json_data)")
