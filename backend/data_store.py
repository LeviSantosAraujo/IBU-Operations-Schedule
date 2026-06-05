import json
import os
from typing import List, Optional, Dict
from datetime import date
from models import Employee, Availability, WeeklySchedule, SystemConfig

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

def _get_path(filename: str) -> str:
    return os.path.join(DATA_DIR, filename)

def _load_json(filename: str) -> List[Dict]:
    path = _get_path(filename)
    if not os.path.exists(path):
        return []
    with open(path, 'r') as f:
        return json.load(f)

def _save_json(filename: str, data: List[Dict]):
    path = _get_path(filename)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, default=str)

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
    # Remove existing if updating
    employees = [e for e in employees if e.get("id") != employee.id]
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
            Employee(id="emp3", name="Mickaela C", employee_type="student_worker", max_hours_per_week=24),
            Employee(id="emp4", name="Kavya C", employee_type="student_worker", max_hours_per_week=24),
            Employee(id="emp5", name="Pablo 2", employee_type="student_worker", max_hours_per_week=24),
            Employee(id="emp6", name="Viviana 3", employee_type="student_worker", max_hours_per_week=24),
            Employee(id="emp7", name="Anastasia 3", employee_type="student_worker", max_hours_per_week=24),
            Employee(id="emp8", name="MEG 3", employee_type="student_worker", max_hours_per_week=24),
            Employee(id="emp9", name="Achal 2", employee_type="student_worker", max_hours_per_week=24),
            Employee(id="emp10", name="PRIYANKA 2", employee_type="student_worker", max_hours_per_week=24),
            Employee(id="emp11", name="Arta C", employee_type="student_worker", max_hours_per_week=24),
            Employee(id="emp12", name="Taran C", employee_type="student_worker", max_hours_per_week=24),
            Employee(id="emp13", name="Sagar C", employee_type="student_worker", max_hours_per_week=24),
            Employee(id="emp14", name="Itshan 3", employee_type="student_worker", max_hours_per_week=24),
            Employee(id="emp15", name="Arnob 2", employee_type="student_worker", max_hours_per_week=24),
            Employee(id="emp16", name="Intern-Levi 7", employee_type="intern", max_hours_per_week=15),
            Employee(id="emp17", name="Intern-Himanshu 7", employee_type="intern", max_hours_per_week=15),
        ]
        for emp in sample_employees:
            save_employee(emp)
