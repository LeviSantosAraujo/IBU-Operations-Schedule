from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import date, datetime
from enum import Enum

class EmployeeType(str, Enum):
    INTERN = "intern"  # 15 hrs/week max
    EMPLOYEE = "employee"  # 24 hrs/week max (was student_worker)
    STUDENT_WORKER = "student_worker"  # Legacy - maps to employee
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
    DAY_OFF = "day_off"  # Day off request

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
    max_hours_per_week: Optional[int] = Field(None, description="Maximum hours per week")
    preferences: Dict[str, int] = Field(default_factory=dict, description="Employee-submitted job preferences with weights 1-10")
    manager_preferences: Dict[str, int] = Field(default_factory=dict, description="Manager-set job preferences (overrides employee preferences)")
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    is_stealth_admin: bool = False

class EmployeeUpdate(BaseModel):
    """Model for partial employee updates - all fields optional"""
    name: Optional[str] = None
    email: Optional[str] = None
    employee_type: Optional[EmployeeType] = None
    max_hours_per_week: Optional[int] = None
    preferences: Optional[Dict[str, int]] = None
    manager_preferences: Optional[Dict[str, int]] = None
    active: Optional[bool] = None

class Availability(BaseModel):
    id: Optional[str] = None  # Optional - will be auto-generated if not provided
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

class HourlyCoverageRequirement(BaseModel):
    """Manager-defined per-hour coverage requirements for scheduling
    This represents which locations need coverage at which hours"""
    id: Optional[str] = None
    week_start_date: date
    day_of_week: str  # monday, tuesday, etc.
    hour: int  # 0-23, the hour of the day
    location: str  # e.g., "2nd Floor", "6th Floor", "Ground Floor", "Call Center", "80 Bloor"
    required_employees: int = 1  # How many employees needed
    is_call_center: bool = False  # Whether this location can be call center
    created_by: str  # Manager employee_id
    created_at: datetime = Field(default_factory=datetime.now)
    notes: Optional[str] = None

class Shift(BaseModel):
    id: str
    employee_id: str
    day_of_week: str  # monday, tuesday, etc.
    start_time: str  # HH:MM format
    end_time: str    # HH:MM format
    job_type: JobType
    floor: Optional[Floor] = None  # Legacy - kept for compatibility
    location: Optional[str] = None  # Human-readable location (e.g., "2nd Floor", "Call Center")
    hours: float
    is_event: bool = False
    event_name: Optional[str] = None
    color: Optional[str] = None  # Background color from Excel cell
    comment: Optional[str] = None  # Any unmapped text/comment from the cell
    requires_break: bool = False  # Whether this shift requires a 30-min break (>5 hours)
    break_provided: bool = False  # Whether a break was provided
    locked: bool = False  # Locked availability - manager cannot schedule over this
    locked_availability_type: Optional[str] = None  # The approved availability type
    preferences: Optional[Dict[str, int]] = None  # Employee job preferences (e.g., {"call_center": 8, "second_floor": 5})
    is_call_center: bool = False  # Whether this shift is assigned to call center duties (can be combined with any location)

class WeeklySchedule(BaseModel):
    id: str
    week_start_date: date
    shifts: List[Shift] = []
    total_hours: Dict[str, float] = Field(default_factory=dict)  # employee_id -> hours
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    created_by: str = "manager"
    status: str = "draft"  # draft, published, archived
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)  # Additional metadata like generation time

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
    staffing_targets: Dict[str, int] = Field(default_factory=dict)

class AvailabilityRequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class AvailabilityRequestType(str, Enum):
    AVAILABILITY = "availability"  # Time range availability
    DAY_OFF = "day_off"  # Full day off request

class AvailabilityRequest(BaseModel):
    id: str
    employee_id: str
    request_type: AvailabilityRequestType = AvailabilityRequestType.AVAILABILITY
    start_date: date  # Start of date range
    end_date: date  # End of date range
    days_of_week: List[str] = []  # e.g., ["monday", "wednesday", "friday"]
    start_time: Optional[str] = None  # HH:MM format (for availability requests)
    end_time: Optional[str] = None  # HH:MM format (for availability requests)
    week_start_date: Optional[date] = None  # Legacy - for compatibility
    day_of_week: Optional[str] = None  # Legacy - for compatibility
    availability_type: Optional[AvailabilityType] = None  # Legacy - for compatibility
    status: AvailabilityRequestStatus = AvailabilityRequestStatus.PENDING
    manager_comment: Optional[str] = None
    employee_comment: Optional[str] = None  # Employee's reason for the request
    preferences: Optional[Dict[str, int]] = None  # Job preferences (1-10)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    approved_by: Optional[str] = None  # Manager employee_id who approved
    approved_at: Optional[datetime] = None

class NotificationType(str, Enum):
    AVAILABILITY_APPROVED = "availability_approved"
    AVAILABILITY_REJECTED = "availability_rejected"
    SCHEDULE_UPDATED = "schedule_updated"

class Notification(BaseModel):
    id: str
    employee_id: str
    type: NotificationType
    message: str
    created_at: datetime = Field(default_factory=datetime.now)
    read: bool = False

class StaffingTarget(BaseModel):
    """Staffing target for a location"""
    location: str
    target: int  # Number of people needed per day

class LocationHours(BaseModel):
    """Operating hours for a location"""
    location: str
    start_time: str  # HH:MM format
    end_time: str  # HH:MM format

class Event(BaseModel):
    """Event created by managers for a specific week"""
    id: str
    name: str
    week_start_date: date  # The week this event belongs to
    date: date  # The specific date of the event
    start_time: str  # HH:MM format
    end_time: str  # HH:MM format
    location: str  # Where the event happens
    people_needed: int = 0  # Number of employees needed (set in auto-generate screen)
    description: Optional[str] = None
    created_by: str  # Manager employee_id who created the event
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
