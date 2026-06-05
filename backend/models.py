from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import date, datetime
from enum import Enum

class EmployeeType(str, Enum):
    INTERN = "intern"  # 15 hrs/week max
    STUDENT_WORKER = "student_worker"  # 24 hrs/week max
    MANAGER = "manager"  # no limit

class AvailabilityType(str, Enum):
    BLANK = "blank"  # Anytime/all day
    UNTIL_12PM = "until_12pm"  # Until 12pm
    UNTIL_3PM = "until_3pm"  # UNTIL 3pm
    AFTER_330PM = "after_330pm"  # After 3:30pm
    TWELVE_TO_3 = "12_3"  # 12-3p
    AFTER_12_EOD = "after_12_eod"  # after 12 - eod
    BEFORE_12_AFTER_330 = "before_12_after_330"  # Before 12 and after 3:30
    OFF = "off"  # Not available

class JobType(str, Enum):
    GROUND_FLOOR = "ground_floor"  # GR
    SECOND_FLOOR = "second_floor"  # 2nd
    SIXTH_FLOOR = "sixth_floor"  # 6th
    CALL_CENTER = "call_center"  # CC
    CLASSROOM = "classroom"
    EVENT = "event"
    ELEVATOR = "elevator"
    IBU_OPS = "ibu_ops"
    DESK = "desk"
    MANAGEMENT = "management"

class Floor(str, Enum):
    GROUND = "ground"
    SECOND = "second"
    SIXTH = "sixth"

# Color mapping for availability types
AVAILABILITY_COLORS = {
    AvailabilityType.BLANK: "#FFFFFF",
    AvailabilityType.UNTIL_12PM: "#90EE90",  # Light green
    AvailabilityType.UNTIL_3PM: "#87CEEB",    # Sky blue
    AvailabilityType.AFTER_330PM: "#FFB6C1",  # Light pink
    AvailabilityType.TWELVE_TO_3: "#ADD8E6",  # Light blue
    AvailabilityType.AFTER_12_EOD: "#FFDAB9",  # Peach
    AvailabilityType.BEFORE_12_AFTER_330: "#DDA0DD",  # Plum
    AvailabilityType.OFF: "#000000",          # Black
}

class Employee(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    employee_type: EmployeeType
    max_hours_per_week: int = Field(..., description="Maximum hours per week")
    preferences: Dict[JobType, int] = Field(default_factory=dict, description="Job preferences with weights 1-10")
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.now)

class Availability(BaseModel):
    id: str
    employee_id: str
    week_start_date: date
    monday: AvailabilityType = AvailabilityType.BLANK
    tuesday: AvailabilityType = AvailabilityType.BLANK
    wednesday: AvailabilityType = AvailabilityType.BLANK
    thursday: AvailabilityType = AvailabilityType.BLANK
    friday: AvailabilityType = AvailabilityType.BLANK
    saturday: AvailabilityType = AvailabilityType.BLANK
    sunday: AvailabilityType = AvailabilityType.OFF
    submitted_at: datetime = Field(default_factory=datetime.now)
    notes: Optional[str] = None
    approved: bool = False
    approved_by: Optional[str] = None  # Manager employee_id who approved
    approved_at: Optional[datetime] = None

class Shift(BaseModel):
    id: str
    employee_id: str
    day_of_week: str  # monday, tuesday, etc.
    start_time: str  # HH:MM format
    end_time: str    # HH:MM format
    job_type: JobType
    floor: Optional[Floor] = None
    hours: float
    is_event: bool = False
    event_name: Optional[str] = None

class WeeklySchedule(BaseModel):
    id: str
    week_start_date: date
    shifts: List[Shift] = []
    total_hours: Dict[str, float] = Field(default_factory=dict)  # employee_id -> hours
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    created_by: str = "manager"
    status: str = "draft"  # draft, published, archived

class ScheduleRequest(BaseModel):
    week_start_date: date
    employee_ids: Optional[List[str]] = None  # None = all employees

class FloorCoverageQuery(BaseModel):
    floor: Floor
    day_of_week: str
    time_slot: str  # e.g., "morning", "afternoon", "evening" or specific time

class FloorCoverageResponse(BaseModel):
    floor: Floor
    day_of_week: str
    time_slot: str
    employee_count: int
    employees: List[Dict] = []

class SystemConfig(BaseModel):
    default_weights: Dict[str, int] = Field(default_factory=dict)
    scheduling_rules: Dict[str, Any] = Field(default_factory=dict)
    floor_requirements: Dict[Floor, Dict[str, int]] = Field(default_factory=dict)
