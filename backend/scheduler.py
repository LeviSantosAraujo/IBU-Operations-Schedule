from typing import List, Dict, Optional, Tuple
from datetime import date, timedelta
import uuid
from models import (
    Employee, Availability, WeeklySchedule, Shift, 
    JobType, Floor, AvailabilityType, EmployeeType
)
from excel_store import (
    get_all_employees, get_availabilities, get_availability_for_week,
    save_schedule, get_system_config
)

class SchedulingEngine:
    def __init__(self):
        self.config = get_system_config()
        self.day_order = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        
    def parse_availability_hours(self, avail_type: AvailabilityType) -> Tuple[str, str]:
        """Convert availability type to start/end time range"""
        availability_windows = {
            AvailabilityType.BLANK: ("08:00", "22:00"),  # Full day
            AvailabilityType.UNTIL_12PM: ("08:00", "12:00"),
            AvailabilityType.UNTIL_3PM: ("08:00", "15:00"),
            AvailabilityType.AFTER_330PM: ("15:30", "22:00"),
            AvailabilityType.TWELVE_TO_3: ("12:00", "15:00"),
            AvailabilityType.AFTER_12_EOD: ("12:00", "22:00"),
            AvailabilityType.BEFORE_12_AFTER_330: None,  # Two windows, handle separately
            AvailabilityType.OFF: None,
        }
        return availability_windows.get(avail_type)
    
    def is_time_within_availability(self, start_time: str, end_time: str, avail_type: AvailabilityType) -> bool:
        """Check if a shift fits within availability"""
        if avail_type == AvailabilityType.OFF:
            return False
        
        if avail_type == AvailabilityType.BEFORE_12_AFTER_330:
            # Two windows: before 12 and after 3:30
            # Shift must fit entirely in one of them
            if end_time <= "12:00":
                return True
            if start_time >= "15:30":
                return True
            return False
        
        window = self.parse_availability_hours(avail_type)
        if window is None:
            return False
        
        avail_start, avail_end = window
        return start_time >= avail_start and end_time <= avail_end
    
    def calculate_shift_hours(self, start_time: str, end_time: str) -> float:
        """Calculate hours between two times"""
        start_h, start_m = map(int, start_time.split(":"))
        end_h, end_m = map(int, end_time.split(":"))
        
        start_decimal = start_h + start_m / 60
        end_decimal = end_h + end_m / 60
        
        hours = end_decimal - start_decimal
        # Handle overnight shifts (not expected here but just in case)
        if hours < 0:
            hours += 24
        
        return round(hours, 1)
    
    def get_employee_weekly_hours(self, schedule: WeeklySchedule, employee_id: str) -> float:
        """Get total hours for an employee in a schedule"""
        return schedule.total_hours.get(employee_id, 0)
    
    def can_assign_shift(self, employee: Employee, shift: Shift, schedule: WeeklySchedule, 
                         availability: Availability) -> Tuple[bool, str]:
        """Check if shift can be assigned to employee"""
        
        # Check max hours
        current_hours = self.get_employee_weekly_hours(schedule, employee.id)
        if current_hours + shift.hours > employee.max_hours_per_week:
            return False, f"Exceeds max hours ({employee.max_hours_per_week})"
        
        # Check availability for the day
        day_avail = getattr(availability, shift.day_of_week, AvailabilityType.OFF)
        if not self.is_time_within_availability(shift.start_time, shift.end_time, day_avail):
            return False, f"Not available on {shift.day_of_week}"
        
        # Check for overlapping shifts
        for existing_shift in schedule.shifts:
            if existing_shift.employee_id == employee.id and existing_shift.day_of_week == shift.day_of_week:
                # Check overlap
                if (shift.start_time < existing_shift.end_time and 
                    shift.end_time > existing_shift.start_time):
                    return False, "Overlapping shift exists"
        
        return True, "OK"
    
    def score_employee_for_shift(self, employee: Employee, shift: Shift, 
                                  availability: Availability) -> float:
        """Score how good of a fit an employee is for a shift (higher = better)"""
        score = 0.0
        
        # Job preference weight (1-10, default 5)
        pref_weight = employee.preferences.get(shift.job_type, 5)
        score += pref_weight * 10
        
        # Check if availability is exact match or partial
        day_avail = getattr(availability, shift.day_of_week, AvailabilityType.BLANK)
        
        # Bonus for exact fit
        if day_avail == AvailabilityType.BLANK:
            score += 20  # Full availability is valuable
        elif day_avail in [AvailabilityType.UNTIL_3PM, AvailabilityType.AFTER_12_EOD]:
            score += 10  # Good availability
        
        # Penalty for employees already working many hours
        current_hours = employee.max_hours_per_week  # We don't have schedule here, so estimate
        remaining_capacity = 1.0  # Assume full capacity for initial scoring
        score += remaining_capacity * 5
        
        return score
    
    def generate_auto_schedule(self, week_start_date: date, 
                               floor_requirements: Optional[Dict] = None) -> WeeklySchedule:
        """Generate an automatic schedule based on availability and preferences"""
        
        employees = [e for e in get_all_employees() if e.active]
        availabilities = {a.employee_id: a for a in get_availabilities(week_start_date)}
        
        # Create empty schedule
        schedule = WeeklySchedule(
            id=str(uuid.uuid4()),
            week_start_date=week_start_date,
            shifts=[],
            total_hours={}
        )
        
        # Default floor requirements if none provided
        if not floor_requirements:
            floor_requirements = {
                Floor.GROUND: {"monday": 2, "tuesday": 2, "wednesday": 2, "thursday": 2, "friday": 2, "saturday": 1, "sunday": 1},
                Floor.SECOND: {"monday": 1, "tuesday": 1, "wednesday": 1, "thursday": 1, "friday": 1, "saturday": 0, "sunday": 0},
                Floor.SIXTH: {"monday": 1, "tuesday": 1, "wednesday": 1, "thursday": 1, "friday": 1, "saturday": 1, "sunday": 0},
            }
        
        # Common shift patterns
        shift_patterns = [
            ("08:00", "12:00", 4.0),    # Morning
            ("12:00", "16:00", 4.0),    # Mid-day
            ("16:00", "20:00", 4.0),    # Evening
            ("08:00", "16:00", 8.0),    # Full day short
            ("09:00", "17:00", 8.0),    # Standard day
            ("10:00", "14:00", 4.0),    # Short mid-day
            ("14:00", "18:00", 4.0),    # Afternoon
            ("18:00", "22:00", 4.0),    # Late evening
        ]
        
        # For each day and floor, try to fill requirements
        for day in self.day_order:
            for floor, daily_req in floor_requirements.items():
                needed = daily_req.get(day, 0)
                if needed == 0:
                    continue
                
                assigned = 0
                attempts = 0
                
                while assigned < needed and attempts < 50:
                    attempts += 1
                    
                    # Try different shift patterns
                    for start, end, hours in shift_patterns:
                        if assigned >= needed:
                            break
                        
                        # Score all available employees for this shift
                        candidates = []
                        for emp in employees:
                            avail = availabilities.get(emp.id)
                            if not avail:
                                avail = Availability(
                                    id=str(uuid.uuid4()),
                                    employee_id=emp.id,
                                    week_start_date=week_start_date
                                )
                            
                            test_shift = Shift(
                                id="temp",
                                employee_id=emp.id,
                                day_of_week=day,
                                start_time=start,
                                end_time=end,
                                job_type=JobType.GROUND_FLOOR if floor == Floor.GROUND else 
                                        JobType.SECOND_FLOOR if floor == Floor.SECOND else JobType.SIXTH_FLOOR,
                                floor=floor,
                                hours=hours
                            )
                            
                            can_assign, reason = self.can_assign_shift(emp, test_shift, schedule, avail)
                            if can_assign:
                                score = self.score_employee_for_shift(emp, test_shift, avail)
                                candidates.append((score, emp, avail, test_shift))
                        
                        # Sort by score (descending)
                        candidates.sort(key=lambda x: x[0], reverse=True)
                        
                        # Assign to best candidate
                        if candidates:
                            _, best_emp, best_avail, shift = candidates[0]
                            shift.id = str(uuid.uuid4())
                            schedule.shifts.append(shift)
                            
                            # Update total hours
                            current = schedule.total_hours.get(best_emp.id, 0)
                            schedule.total_hours[best_emp.id] = current + shift.hours
                            
                            assigned += 1
        
        return schedule
    
    def optimize_schedule(self, schedule: WeeklySchedule) -> WeeklySchedule:
        """Optimize existing schedule for better coverage and preferences"""
        # TODO: Implement swap/exchange optimization
        return schedule

def generate_schedule(week_start_date: date) -> WeeklySchedule:
    """Convenience function to generate a schedule"""
    engine = SchedulingEngine()
    return engine.generate_auto_schedule(week_start_date)
