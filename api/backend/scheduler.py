from typing import List, Dict, Optional, Tuple
from datetime import date, timedelta
import uuid
from models import (
    Employee, Availability, WeeklySchedule, Shift, 
    JobType, Floor, AvailabilityType, EmployeeType, Event
)
import json_store
from excel_store import get_location_color

class SchedulingEngine:
    def __init__(self):
        self.config = json_store.get_system_config()
        self.day_order = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]  # Sunday excluded - only for events
        
        # Location operating hours
        self.location_hours = {
            'ground floor': ('07:30', '18:00'),
            '2nd floor': ('08:00', '18:00'),
            '6th floor': ('08:00', '18:00'),
            '80 bloor': ('08:30', '18:00'),
            'working from home': ('08:00', '18:00')
        }

    def get_employee_max_hours(self, employee: Employee) -> int:
        if employee.max_hours_per_week is not None:
            return employee.max_hours_per_week
        if employee.employee_type == EmployeeType.MANAGER:
            return 40
        if employee.employee_type == EmployeeType.INTERN:
            return 15
        return 24
        
    def parse_availability_hours(self, avail_type: AvailabilityType) -> Tuple[str, str]:
        """Convert availability type to start/end time range"""
        availability_windows = {
            AvailabilityType.BLANK: ("07:00", "22:00"),  # Full day (covers ground floor 07:30 start)
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
    
    def get_employee_historical_hours(self, employee_id: str, current_week_start: date, schedule_cache: Optional[Dict] = None) -> float:
        """Get total hours for an employee over the last 4 weeks"""
        total_hours = 0
        week_count = 0

        # Get the last 4 weeks before the current week
        for i in range(1, 5):
            week_date = current_week_date = current_week_start - timedelta(weeks=i)

            try:
                if schedule_cache:
                    week_str = week_date.isoformat()
                    if week_str not in schedule_cache:
                        schedule_cache[week_str] = get_schedule_by_week(week_date)
                    schedule = schedule_cache[week_str]
                else:
                    schedule = get_schedule_by_week(week_date)
                if schedule:
                    total_hours += schedule.total_hours.get(employee_id, 0)
                    week_count += 1
            except Exception:
                # Week might not exist or have no schedule
                pass

        return total_hours
    
    def get_all_employee_historical_hours(self, employees: List[Employee], current_week_start: date, schedule_cache: Optional[Dict] = None) -> Dict[str, float]:
        """Get historical hours for all employees over the last 4 weeks"""
        historical_hours = {}
        for emp in employees:
            historical_hours[emp.id] = self.get_employee_historical_hours(emp.id, current_week_start, schedule_cache)
        return historical_hours
    
    def get_historical_shift_patterns(self, employee_id: str, current_week_start: date, schedule_cache: Optional[Dict] = None) -> Optional[Dict[str, List[Shift]]]:
        """Get shift patterns from the last 4 weeks for an employee, return the week with most hours"""
        best_week_shifts = None
        best_week_hours = 0
        best_week_date = None

        for i in range(1, 5):
            week_date = current_week_start - timedelta(weeks=i)
            try:
                if schedule_cache:
                    week_str = week_date.isoformat()
                    if week_str not in schedule_cache:
                        schedule_cache[week_str] = get_schedule_by_week(week_date)
                    schedule = schedule_cache[week_str]
                else:
                    schedule = get_schedule_by_week(week_date)
                if schedule:
                    # Get shifts for this employee
                    emp_shifts = [s for s in schedule.shifts if s.employee_id == employee_id]
                    emp_hours = schedule.total_hours.get(employee_id, 0)

                    # If this week has more hours than previous best, use it
                    if emp_hours > best_week_hours:
                        best_week_hours = emp_hours
                        best_week_shifts = emp_shifts
                        best_week_date = week_date
            except Exception:
                continue
        
        if best_week_shifts:
            # Group shifts by day of week
            shifts_by_day = {}
            for shift in best_week_shifts:
                if shift.day_of_week not in shifts_by_day:
                    shifts_by_day[shift.day_of_week] = []
                shifts_by_day[shift.day_of_week].append(shift)
            return shifts_by_day
        
        return None
    
    def get_historical_job_preferences(self, employee_id: str, current_week_start: date, schedule_cache: Optional[Dict] = None) -> Dict[JobType, int]:
        """Analyze last 4 weeks to infer job preferences based on actual assignments"""
        job_type_counts = {}
        total_shifts = 0

        for i in range(1, 5):
            week_date = current_week_start - timedelta(weeks=i)
            try:
                if schedule_cache:
                    week_str = week_date.isoformat()
                    if week_str not in schedule_cache:
                        schedule_cache[week_str] = get_schedule_by_week(week_date)
                    schedule = schedule_cache[week_str]
                else:
                    schedule = get_schedule_by_week(week_date)
                if schedule:
                    emp_shifts = [s for s in schedule.shifts if s.employee_id == employee_id]
                    for shift in emp_shifts:
                        job_type = shift.job_type
                        job_type_counts[job_type] = job_type_counts.get(job_type, 0) + 1
                        total_shifts += 1
            except Exception:
                continue
        
        # Convert counts to preference weights (1-10 scale)
        preferences = {}
        if total_shifts > 0:
            for job_type, count in job_type_counts.items():
                # Calculate percentage of shifts for this job type
                percentage = count / total_shifts
                # Map to 1-10 scale (more frequent = higher preference)
                preferences[job_type] = round(percentage * 10)
        
        return preferences
    
    def can_assign_shift(self, employee: Employee, shift: Shift, schedule: WeeklySchedule, 
                         availability: Optional[Availability], approved_requests: Dict = None) -> Tuple[bool, str]:
        """Check if shift can be assigned to employee"""
        
        # Validate shift data
        if shift.hours <= 0:
            return False, f"Invalid shift hours: {shift.hours}"
        
        # Validate time format and logic
        try:
            from datetime import datetime
            start_dt = datetime.strptime(shift.start_time, "%H:%M")
            end_dt = datetime.strptime(shift.end_time, "%H:%M")
            
            # Handle overnight shifts (e.g., 22:00 to 02:00)
            if end_dt <= start_dt:
                # Assume overnight shift, add 24 hours to end time
                from datetime import timedelta
                end_dt += timedelta(days=1)
            
            # Calculate actual hours from times
            actual_hours = (end_dt - start_dt).total_seconds() / 3600
            if abs(actual_hours - shift.hours) > 0.5:  # Allow 30min tolerance
                return False, f"Time mismatch: calculated {actual_hours}h but shift has {shift.hours}h"
        except Exception as e:
            return False, f"Invalid time format: {e}"
        
        # Priority 1: Check max hours
        current_hours = self.get_employee_weekly_hours(schedule, employee.id)
        max_hours = self.get_employee_max_hours(employee)
        if current_hours + shift.hours > max_hours:
            return False, f"Exceeds max hours ({max_hours})"
        
        # Intern-specific: Max 6 continuous hours per shift
        if employee.employee_type == EmployeeType.INTERN and shift.hours > 6:
            return False, f"Intern shift exceeds 6 hours (shift: {shift.hours}h)"
        
        # Intern-specific: Restrict locations to ground floor, 2nd floor, 6th floor only
        if employee.employee_type == EmployeeType.INTERN:
            allowed_locations = {'ground floor', '2nd floor', '6th floor'}
            if shift.location not in allowed_locations:
                return False, f"Intern not allowed at {shift.location} (only: ground floor, 2nd floor, 6th floor)"
        
        # Priority 2: Check Day Off constraints (approved requests)
        if approved_requests and employee.id in approved_requests:
            day_request = approved_requests[employee.id].get(shift.day_of_week)
            if day_request and day_request == AvailabilityType.OFF:
                # Employee has approved Day Off for this day - cannot assign ANY shift
                return False, f"Employee has approved Day Off on {shift.day_of_week}"
        
        # Priority 3: Check approved availability requests (non-day-off)
        if approved_requests and employee.id in approved_requests:
            day_request = approved_requests[employee.id].get(shift.day_of_week)
            if day_request and day_request != AvailabilityType.OFF:
                # Employee has an approved request for this day
                if isinstance(day_request, dict) and day_request.get('type') == 'time_range':
                    # Check if shift fits within the approved time range
                    req_start = day_request.get('start', '00:00')
                    req_end = day_request.get('end', '23:59')
                    if not (shift.start_time >= req_start and shift.end_time <= req_end):
                        print(f"[SCHEDULER] REJECTED: Employee {employee.id} shift {shift.start_time}-{shift.end_time} outside approved range {req_start}-{req_end} on {shift.day_of_week}")
                        return False, f"Shift {shift.start_time}-{shift.end_time} outside approved range {req_start}-{req_end}"
                elif not self.is_time_within_availability(shift.start_time, shift.end_time, day_request):
                    print(f"[SCHEDULER] REJECTED: Employee {employee.id} not available on {shift.day_of_week} (approved availability type: {day_request})")
                    return False, f"Not available on {shift.day_of_week} (approved availability)"
        
        # Check for overlapping shifts
        for existing_shift in schedule.shifts:
            if existing_shift.employee_id == employee.id and existing_shift.day_of_week == shift.day_of_week and not existing_shift.locked:
                # Check overlap
                if (shift.start_time < existing_shift.end_time and 
                    shift.end_time > existing_shift.start_time):
                    return False, "Overlapping shift exists"
        
        return True, "OK"
    
    def score_employee_for_shift(self, employee: Employee, shift: Shift, 
                                  availability: Optional[Availability], employee_preferences: Dict = None, 
                                  historical_preferences: Dict = None, current_hours: float = 0) -> float:
        """Score how good of a fit an employee is for a shift (higher = better)"""
        score = 0.0
        
        # Job preference weight (1-10, default 5)
        # Priority: manager-set preferences (employee.manager_preferences) > employee-submitted preferences (employee.preferences) > availability request preferences > historical preferences > default
        pref_weight = 5
        pref_source = "default"
        
        if employee.manager_preferences and shift.job_type in employee.manager_preferences:
            # Manager-set preferences have highest priority
            pref_weight = employee.manager_preferences.get(shift.job_type, 5)
            pref_source = "manager_preferences"
            print(f"[SCHEDULER] Using manager_preferences for {employee.name}: {shift.job_type} = {pref_weight}")
        elif employee.preferences and shift.job_type in employee.preferences:
            # Employee-submitted preferences (fallback)
            pref_weight = employee.preferences.get(shift.job_type, 5)
            pref_source = "employee_preferences"
            print(f"[SCHEDULER] Using employee_preferences for {employee.name}: {shift.job_type} = {pref_weight}")
        elif employee_preferences and employee.id in employee_preferences:
            prefs = employee_preferences[employee.id]
            pref_weight = prefs.get(shift.job_type, 5)
            pref_source = "availability_request_preferences"
            print(f"[SCHEDULER] Using availability request preferences for {employee.name}: {shift.job_type} = {pref_weight}")
        elif historical_preferences and employee.id in historical_preferences:
            hist_prefs = historical_preferences[employee.id]
            pref_weight = hist_prefs.get(shift.job_type, 5)
            pref_source = "historical_preferences"
            print(f"[SCHEDULER] Using historical preferences for {employee.name}: {shift.job_type} = {pref_weight}")
        else:
            print(f"[SCHEDULER] Using default preference for {employee.name}: {shift.job_type} = {pref_weight}")
        
        # Reduce preference weight as employee gets more hours assigned
        # First shifts: strong preference (100% weight)
        # Later shifts: more flexible (down to 50% weight at max hours)
        max_hours = self.get_employee_max_hours(employee)
        hours_ratio = current_hours / max_hours if max_hours > 0 else 0
        preference_multiplier = 1.0 - (hours_ratio * 0.5)  # 1.0 at 0 hours, 0.5 at max hours
        score += pref_weight * 10 * preference_multiplier
        
        # Check if availability is exact match or partial
        day_avail = getattr(availability, shift.day_of_week, AvailabilityType.BLANK)
        
        # Bonus for exact fit
        if day_avail == AvailabilityType.BLANK:
            score += 20  # Full availability is valuable
        elif day_avail in [AvailabilityType.UNTIL_3PM, AvailabilityType.AFTER_12_EOD]:
            score += 10  # Good availability
        
        # Penalty for employees already working many hours
        remaining_capacity = 1.0 - hours_ratio
        score += remaining_capacity * 5
        
        return score
    
    def generate_auto_schedule(self, week_start_date: date,
                               location_requirements: Optional[Dict] = None,
                               event_staffing: Optional[Dict[str, int]] = None,
                               call_center_target: int = 0) -> WeeklySchedule:
        """Generate an automatic schedule based on availability, preferences, and location requirements"""
        import time
        start_time = time.time()

        print(f"[SCHEDULER] Starting auto-schedule generation for week {week_start_date}")

        # Cache for schedules to avoid repeated loading
        schedule_cache = {}

        # Load all schedules from JSON store
        all_schedules_dict = json_store.get_schedules()
        all_schedules = [WeeklySchedule(**s) for s in all_schedules_dict]

        def get_cached_schedule(week_date: date) -> Optional[WeeklySchedule]:
            """Get schedule with caching to avoid repeated loading"""
            week_str = week_date.isoformat()
            if week_str not in schedule_cache:
                # Find schedule for this week from JSON schedules
                for sched in all_schedules:
                    if str(sched.week_start_date) == week_str:
                        schedule_cache[week_str] = sched
                        return sched
                schedule_cache[week_str] = None
            return schedule_cache[week_str]

        # Load employees from JSON store (single source of truth)
        employee_dicts = json_store.get_employees()
        employees = [Employee(**emp_dict) for emp_dict in employee_dicts if emp_dict.get('active', True)]
        
        # Load approved availability requests for this week (single source of truth)
        approved_requests = {}
        employee_preferences = {}
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        day_map = {0: 'monday', 1: 'tuesday', 2: 'wednesday', 3: 'thursday', 4: 'friday', 5: 'saturday', 6: 'sunday'}
        try:
            all_requests = json_store.get_availability_requests()
            week_end_date = week_start_date + timedelta(days=6)

            for req in all_requests:
                if req.get('status') not in ['approved', 'AvailabilityRequestStatus.APPROVED']:
                    continue

                emp_id = req.get('employee_id')
                if not emp_id:
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
                                if emp_id not in approved_requests:
                                    approved_requests[emp_id] = {}

                                # Mark as unavailable for day-offs or specific time ranges
                                if request_type == 'day_off':
                                    approved_requests[emp_id][day_name] = AvailabilityType.OFF
                                    print(f"[SCHEDULER] Loaded approved day-off for {emp_id} on {day_name}")
                                else:
                                    # For time range availability, store the time range
                                    # Format: {"type": "time_range", "start": "09:00", "end": "17:00"}
                                    time_range = {
                                        "type": "time_range",
                                        "start": req.get('start_time', '00:00'),
                                        "end": req.get('end_time', '23:59')
                                    }
                                    approved_requests[emp_id][day_name] = time_range
                                    print(f"[SCHEDULER] Loaded approved time range for {emp_id} on {day_name}: {time_range['start']}-{time_range['end']}")

                            current_date += timedelta(days=1)

                    except Exception as e:
                        print(f"Warning: could not parse date range request: {e}")
                        continue

                # Handle legacy model for backward compatibility
                elif req.get('week_start_date'):
                    week_str = week_start_date.isoformat()
                    if req.get('week_start_date') != week_str:
                        continue

                    day = req.get('day_of_week', '').lower()
                    avail_type_str = req.get('availability_type', 'blank')
                    if emp_id and day:
                        if emp_id not in approved_requests:
                            approved_requests[emp_id] = {}
                        try:
                            approved_requests[emp_id][day] = AvailabilityType(avail_type_str)
                        except:
                            approved_requests[emp_id][day] = AvailabilityType.BLANK

                if emp_id not in employee_preferences and req.get('preferences'):
                    employee_preferences[emp_id] = req.get('preferences')

        except Exception as e:
            print(f"Warning: could not load approved availability requests: {e}")

        # Load events from JSON store
        try:
            events_dict = json_store.get_events()
            events = [Event(**e) for e in events_dict]
            print(f"[SCHEDULER] Loaded {len(events)} events from JSON")
        except Exception as e:
            print(f"[SCHEDULER] Error loading events from JSON: {e}")
            events = []
        
        # Calculate historical job preferences for all employees
        historical_job_preferences = {}
        for emp in employees:
            hist_prefs = self.get_historical_job_preferences(emp.id, week_start_date, schedule_cache)
            if hist_prefs:
                historical_job_preferences[emp.id] = hist_prefs
        
        # Create empty schedule
        schedule = WeeklySchedule(
            id=str(uuid.uuid4()),
            week_start_date=week_start_date,
            shifts=[],
            total_hours={}
        )
        
        # If no location requirements provided, skip regular location staffing
        if not location_requirements:
            print(f"[SCHEDULER] No location requirements provided - skipping regular location staffing")
            location_requirements = {}
        
        # Common shift patterns
        shift_patterns = [
            ("08:00", "12:00", 4.0),
            ("12:00", "16:00", 4.0),
            ("16:00", "20:00", 4.0),
            ("08:00", "16:00", 8.0),
            ("09:00", "17:00", 8.0),
            ("10:00", "14:00", 4.0),
            ("14:00", "18:00", 4.0),
            ("18:00", "22:00", 4.0),
        ]
        
        # Track assigned employees per location per day
        location_assignments = {loc: {day: 0 for day in self.day_order} for loc in location_requirements}
        
        # Track call center hours per employee (max 16 hours per week for regular employees)
        call_center_hours = {emp.id: 0 for emp in employees if emp.employee_type != EmployeeType.MANAGER}
        max_call_center_hours = 16
        
        # Track unique locations per employee for diversity
        employee_locations = {emp.id: set() for emp in employees if emp.employee_type != EmployeeType.MANAGER}
        
        # Phase 0: Event Staffing
        print(f"[SCHEDULER] Processing {len(events)} events")
        print(f"[SCHEDULER] Event staffing dict: {event_staffing}")
        
        for event in events:
            event_day = event.date.strftime("%A").lower()
            print(f"[SCHEDULER] Event '{event.name}' id={event.id}, day={event_day}")
            # Allow Sunday events even though Sunday is not in day_order (Sunday is for events only)
            if event_day not in self.day_order and event_day != 'sunday':
                print(f"[SCHEDULER] Skipping event '{event.name}' - day '{event_day}' not in schedule")
                continue
            
            event_keys = [
                event.id,
                f"event_{event.id}" if not str(event.id).startswith('event_') else str(event.id).replace('event_', 'event_event_', 1),
                f"event_{event.name.lower().replace(' ', '_')}",
                event.name.lower().replace(' ', '_')
            ]
            staffing_value = None
            if event_staffing:
                for key in event_keys:
                    if key in event_staffing:
                        staffing_value = event_staffing[key]
                        break
            try:
                people_needed = int(staffing_value if staffing_value is not None else event.people_needed or 0)
            except (TypeError, ValueError):
                people_needed = 0
            print(f"[SCHEDULER] Event '{event.name}' people_needed={people_needed} (from staffing: {staffing_value}, default: {event.people_needed})")
            
            # Skip if no staffing required (0 people needed)
            if people_needed <= 0:
                print(f"[SCHEDULER] Skipping event '{event.name}' - 0 people needed")
                continue
            
            # Calculate event duration in hours
            from datetime import datetime
            start_dt = datetime.strptime(event.start_time, "%H:%M")
            end_dt = datetime.strptime(event.end_time, "%H:%M")
            event_hours = (end_dt - start_dt).total_seconds() / 3600
            
            print(f"[SCHEDULER] Event '{event.name}' on {event_day} ({event.start_time}-{event.end_time}, {event_hours}h) needs {people_needed} people")
            
            assigned = 0
            attempts = 0
            assigned_employees = set()  # Track which employees already assigned to this event
            
            # Assign employees to event using exact event time
            while assigned < people_needed and attempts < 100:
                attempts += 1

                candidates = []
                # Skip managers in event staffing - they get management assignments only
                regular_employees_event = [e for e in employees if e.employee_type != EmployeeType.MANAGER]
                print(f"[SCHEDULER] Evaluating {len(regular_employees_event)} regular employees for event '{event.name}'")
                for emp in regular_employees_event:
                    # Skip if already assigned to this event
                    if emp.id in assigned_employees:
                        continue

                    # Create shift with exact event time
                    test_shift = Shift(
                        id="temp",
                        employee_id=emp.id,
                        day_of_week=event_day,
                        start_time=event.start_time,
                        end_time=event.end_time,
                        job_type=JobType.EVENT,
                        location=event.location,
                        hours=event_hours,
                        is_event=True,
                        event_name=event.name,
                        color=get_location_color(event.location)
                    )

                    can_assign, reason = self.can_assign_shift(emp, test_shift, schedule, None, approved_requests)
                    if can_assign:
                        current_hours = self.get_employee_weekly_hours(schedule, emp.id)
                        score = self.score_employee_for_shift(emp, test_shift, None, employee_preferences, historical_job_preferences, current_hours)
                        candidates.append((score, emp, test_shift))
                        print(f"[SCHEDULER] Candidate for event '{event.name}': {emp.name} (score={score:.2f})")
                    else:
                        print(f"[SCHEDULER] Rejected {emp.name} for event '{event.name}': {reason}")

                candidates.sort(key=lambda x: x[0], reverse=True)
                print(f"[SCHEDULER] Found {len(candidates)} candidates for event '{event.name}'")

                if candidates:
                    _, best_emp, shift = candidates[0]
                    shift.id = str(uuid.uuid4())
                    schedule.shifts.append(shift)

                    current = schedule.total_hours.get(best_emp.id, 0)
                    schedule.total_hours[best_emp.id] = current + shift.hours

                    # Track unique locations for diversity
                    employee_locations[best_emp.id].add(event.location)

                    assigned_employees.add(best_emp.id)
                    assigned += 1
                    print(f"[SCHEDULER] Assigned {best_emp.name} to event '{event.name}' ({assigned}/{people_needed})")
                else:
                    print(f"[SCHEDULER] No candidates found for event '{event.name}' (attempt {attempts})")
                    break
            
            print(f"[SCHEDULER] Event '{event.name}' staffing complete: {assigned}/{people_needed} assigned")
        
        # Phase 1-3: Regular Location Staffing with 3-hour shift distribution
        print(f"[SCHEDULER] Location requirements: {location_requirements}")
        
        for day in self.day_order:
            for location, daily_req in location_requirements.items():
                needed = daily_req.get(day, 0)
                if needed == 0:
                    continue
                
                # Get location operating hours
                loc_hours = self.location_hours.get(location.lower(), ('08:00', '18:00'))
                loc_start, loc_end = loc_hours if loc_hours and len(loc_hours) == 2 else ('08:00', '18:00')
                # Ensure location hours are strings
                loc_start = str(loc_start) if loc_start else '08:00'
                loc_end = str(loc_end) if loc_end else '18:00'
                
                # Calculate total operating hours
                from datetime import datetime
                start_dt = datetime.strptime(loc_start, "%H:%M")
                end_dt = datetime.strptime(loc_end, "%H:%M")
                total_hours = (end_dt - start_dt).total_seconds() / 3600
                
                # Generate dynamic shifts based on employee availability
                # Min shift: 15 minutes, Max shift: 8 hours
                print(f"[SCHEDULER] Location '{location}' on {day}: {needed} people needed ({loc_start}-{loc_end})")
                
                # Skip managers in regular location staffing
                regular_employees_phase1 = [e for e in employees if e.employee_type != EmployeeType.MANAGER]
                
                assigned = 0
                assigned_emp_ids = set()
                
                # Try to assign shifts until we meet the requirement
                while assigned < needed:
                    best_candidate = None
                    best_score = -1
                    best_shift = None
                    
                    for emp in regular_employees_phase1:
                        # Skip employees already assigned to this location today
                        if emp.id in assigned_emp_ids:
                            continue
                        
                        # Get employee's availability for this day from approved requests
                        day_attr = day.lower()
                        day_request = approved_requests.get(emp.id, {}).get(day_attr)
                        
                        # Check if employee has day off
                        if day_request == AvailabilityType.OFF:
                            continue
                        
                        # Get time range from approved request
                        if day_request and isinstance(day_request, dict) and day_request.get('type') == 'time_range':
                            avail_start = day_request.get('start', loc_start)
                            avail_end = day_request.get('end', loc_end)
                        else:
                            # No specific time range, use location hours
                            avail_start = loc_start
                            avail_end = loc_end
                        
                        # Calculate optimal shift within availability and location hours
                        # Use availability start time (respect employee's availability)
                        shift_start = avail_start
                        # Use availability end time (respect employee's availability)
                        shift_end = avail_end
                        
                        # Calculate available hours
                        shift_start_dt = datetime.strptime(shift_start, "%H:%M")
                        shift_end_dt = datetime.strptime(shift_end, "%H:%M")
                        available_hours = (shift_end_dt - shift_start_dt).total_seconds() / 3600
                        
                        # Skip if less than 15 minutes available
                        if available_hours < 0.25:
                            continue
                        
                        # Cap at 8 hours max for regular employees, 6 hours for interns
                        max_shift_hours = 6.0 if emp.employee_type == EmployeeType.INTERN else 8.0
                        shift_hours = min(available_hours, max_shift_hours)
                        
                        # Calculate actual end time
                        actual_end_dt = shift_start_dt + timedelta(hours=shift_hours)
                        actual_end = actual_end_dt.strftime("%H:%M")
                        
                        job_type = self._location_to_job_type(location)
                        
                        test_shift = Shift(
                            id="temp",
                            employee_id=emp.id,
                            day_of_week=day,
                            start_time=shift_start,
                            end_time=actual_end,
                            job_type=job_type,
                            location=location,
                            hours=shift_hours,
                            color=get_location_color(location)
                        )
                        
                        can_assign, reason = self.can_assign_shift(emp, test_shift, schedule, None, approved_requests)
                        if can_assign:
                            current_hours = self.get_employee_weekly_hours(schedule, emp.id)
                            score = self.score_employee_for_shift(emp, test_shift, None, employee_preferences, historical_job_preferences, current_hours)
                            if score > best_score:
                                best_score = score
                                best_candidate = emp
                                best_shift = test_shift
                    
                    if best_candidate and best_shift:
                        best_shift.id = str(uuid.uuid4())
                        schedule.shifts.append(best_shift)
                        
                        current = schedule.total_hours.get(best_candidate.id, 0)
                        schedule.total_hours[best_candidate.id] = current + best_shift.hours
                        
                        employee_locations[best_candidate.id].add(location)
                        assigned_emp_ids.add(best_candidate.id)
                        assigned += 1
                        location_assignments[location][day] += 1
                        print(f"[SCHEDULER] Assigned {best_candidate.name} to {location} on {day} ({best_shift.start_time}-{best_shift.end_time}, {best_shift.hours}h)")
                    else:
                        # No more candidates available
                        print(f"[SCHEDULER] No more candidates for {location} on {day}")
                        break
        
        # Separate managers from regular employees (needed for call center phase)
        managers = [e for e in employees if e.employee_type == EmployeeType.MANAGER]
        interns = [e for e in employees if e.employee_type == EmployeeType.INTERN]
        regular_employees = [e for e in employees if e.employee_type != EmployeeType.MANAGER]
        
        # Phase: Call Center Role Assignment
        # Assign is_call_center flag to existing shifts based on call_center_target
        # Interns are NOT eligible for call center roles
        if call_center_target > 0:
            print(f"[SCHEDULER] Call center role target: {call_center_target} people per day (Mon-Sat only)")
            cc_assigned_total = 0
            
            # Get all existing shifts (excluding events, managers, and interns)
            regular_shifts = [s for s in schedule.shifts if not s.is_event and s.employee_id not in [m.id for m in managers] and s.employee_id not in [i.id for i in interns]]
            
            # Group shifts by day (skip Sunday)
            shifts_by_day = {day: [] for day in days if day != 'sunday'}
            for shift in regular_shifts:
                if shift.day_of_week in shifts_by_day:
                    shifts_by_day[shift.day_of_week].append(shift)
            
            # For each day (Mon-Sat), assign CC roles up to the daily target
            for day in shifts_by_day.keys():
                day_shifts = shifts_by_day[day]
                if not day_shifts:
                    print(f"[SCHEDULER] No shifts available on {day} for CC role assignment")
                    continue
                
                # Sort shifts by employee's call center preference (higher preference first)
                day_shifts.sort(key=lambda s: employee_preferences.get(s.employee_id, {}).get('call_center', 0), reverse=True)
                
                cc_assigned_day = 0
                for shift in day_shifts:
                    if cc_assigned_day >= call_center_target:
                        break
                    
                    # Check if employee has call center hours cap
                    emp_cc_hours = call_center_hours.get(shift.employee_id, 0)
                    if emp_cc_hours >= max_call_center_hours:
                        continue
                    
                    # Mark this shift as call center
                    shift.is_call_center = True
                    call_center_hours[shift.employee_id] = emp_cc_hours + shift.hours
                    cc_assigned_day += 1
                    cc_assigned_total += 1
                    print(f"[SCHEDULER] Assigned call center role to {shift.employee_id} on {day} ({shift.start_time}-{shift.end_time})")
                
                print(f"[SCHEDULER] {day}: {cc_assigned_day}/{call_center_target} CC roles assigned")
            
            print(f"[SCHEDULER] Call center roles assigned total: {cc_assigned_total}/{call_center_target * 6}")
        
        # Phase 4: Fairness Phase - Ensure all employees reach max hours
        # Skip this phase if location_requirements are provided (manager wants specific staffing only)
        if location_requirements:
            print(f"[SCHEDULER] Skipping Phase 4 (Fairness Phase) - using manager-specified staffing targets only")
        else:
            print(f"[SCHEDULER] Phase 4: Fairness Phase - ensuring all employees reach max hours")
            # Get historical hours for all employees (last 4 weeks)
            historical_hours = self.get_all_employee_historical_hours(employees, week_start_date, schedule_cache)
            
            # Process regular employees first (distribute across days)
            for day in self.day_order:
                # Sort employees by current hours + historical hours for this day
                employees_with_hours = []
                for emp in regular_employees:
                    current_hours = self.get_employee_weekly_hours(schedule, emp.id)
                    hist_hours = historical_hours.get(emp.id, 0)
                    total_load = current_hours + hist_hours
                    employees_with_hours.append((total_load, emp, current_hours))
                
                # Process employees in order of lowest total load first
                employees_with_hours.sort(key=lambda x: x[0])
                
                for total_load, emp, current_hours in employees_with_hours:
                    # Skip if employee already at max hours
                    max_hours = self.get_employee_max_hours(emp)
                    if current_hours >= max_hours:
                        continue
                    
                    hours_remaining = max_hours - current_hours
                    if hours_remaining <= 0:
                        continue
                    
                    # Use default availability (available all day)
                    avail = Availability(
                        id=str(uuid.uuid4()),
                        employee_id=emp.id,
                        week_start_date=week_start_date
                    )
                    
                    # Try to mirror historical patterns first
                    historical_patterns = self.get_historical_shift_patterns(emp.id, week_start_date, schedule_cache)
                    if historical_patterns and day in historical_patterns:
                        # Use historical shifts for this day as priority
                        for hist_shift in historical_patterns[day]:
                            hours_remaining = self.get_employee_max_hours(emp) - self.get_employee_weekly_hours(schedule, emp.id)
                            if hours_remaining <= 0:
                                break
                            
                            test_shift = Shift(
                                id="temp",
                                employee_id=emp.id,
                                day_of_week=day,
                                start_time=hist_shift.start_time,
                                end_time=hist_shift.end_time,
                                job_type=hist_shift.job_type,
                                location=hist_shift.location,
                                hours=hist_shift.hours,
                                color=get_location_color(hist_shift.location)
                            )
                            
                            can_assign, reason = self.can_assign_shift(emp, test_shift, schedule, avail, approved_requests)
                            if can_assign:
                                # Prioritize location diversity: if employee already has this location, skip unless they need more hours
                                if test_shift.location in employee_locations.get(emp.id, set()):
                                    # Only assign if they really need the hours (less than 80% of max)
                                    current_hours = self.get_employee_weekly_hours(schedule, emp.id)
                                    if current_hours >= self.get_employee_max_hours(emp) * 0.8:
                                        continue
                                
                                test_shift.id = str(uuid.uuid4())
                                schedule.shifts.append(test_shift)
                                
                                current = schedule.total_hours.get(emp.id, 0)
                                schedule.total_hours[emp.id] = current + test_shift.hours
                                
                                
                                # Track unique locations for diversity
                                employee_locations[emp.id].add(test_shift.location)
                                
                                # Update location assignments
                                if test_shift.location in location_assignments:
                                    location_assignments[test_shift.location][day] += 1
                    
                    # Then fill remaining hours with standard patterns
                    for start, end, hours in shift_patterns:
                        # Re-check hours remaining before each shift
                        hours_remaining = self.get_employee_max_hours(emp) - self.get_employee_weekly_hours(schedule, emp.id)
                        if hours_remaining <= 0:
                            break
                        
                        if hours > hours_remaining:
                            continue
                        
                        # Try each regular location
                        for location in location_requirements.keys():
                            # Skip if location is event-related (events should not be overstaffed)
                            if location == 'event' or 'event' in location.lower():
                                continue
                            
                            job_type = self._location_to_job_type(location)
                            
                            test_shift = Shift(
                                id="temp",
                                employee_id=emp.id,
                                day_of_week=day,
                                start_time=start,
                                end_time=end,
                                job_type=job_type,
                                location=location,
                                hours=hours,
                                color=get_location_color(location)
                            )
                            
                            can_assign, reason = self.can_assign_shift(emp, test_shift, schedule, avail, approved_requests)
                            if can_assign:
                                # Prioritize location diversity: if employee already has this location, skip unless they need more hours
                                if location in employee_locations.get(emp.id, set()):
                                    # Only assign if they really need the hours (less than 80% of max)
                                    current_hours = self.get_employee_weekly_hours(schedule, emp.id)
                                    if current_hours >= self.get_employee_max_hours(emp) * 0.8:
                                        continue
                                
                                # Assign the shift
                                test_shift.id = str(uuid.uuid4())
                                schedule.shifts.append(test_shift)
                                
                                current = schedule.total_hours.get(emp.id, 0)
                                schedule.total_hours[emp.id] = current + test_shift.hours
                            
                            # Track unique locations for diversity
                            employee_locations[emp.id].add(location)
                            
                            # Update location assignments (this allows overstaffing)
                            location_assignments[location][day] += 1
                            break  # Move to next shift pattern
        
        # Phase 5: Ensure interns get their full 15 hours
        # Interns have a hard requirement to get all 15 hours if possible
        print("[SCHEDULER] Phase 5: Ensuring interns get full 15 hours")
        interns = [emp for emp in employees if emp.employee_type == EmployeeType.INTERN]
        for intern in interns:
            current_hours = self.get_employee_weekly_hours(schedule, intern.id)
            hours_needed = 15 - current_hours
            if hours_needed <= 0:
                continue
            
            print(f"[SCHEDULER] Intern {intern.name} needs {hours_needed} more hours (current: {current_hours})")
            
            # Try to assign remaining hours across available days
            for day in self.day_order:
                if hours_needed <= 0:
                    break
                
                # Check if intern has availability for this day
                day_request = approved_requests.get(intern.id, {}).get(day)
                if day_request == AvailabilityType.OFF:
                    continue
                
                # Get availability time range
                if day_request and isinstance(day_request, dict) and day_request.get('type') == 'time_range':
                    avail_start = day_request.get('start', '07:30')
                    avail_end = day_request.get('end', '18:00')
                else:
                    # Default to full day if no specific time range
                    avail_start = '07:30'
                    avail_end = '18:00'
                
                # Try intern-allowed locations only
                intern_locations = ['ground floor', '2nd floor', '6th floor']
                for location in intern_locations:
                    if hours_needed <= 0:
                        break
                    
                    loc_start, loc_end = self.location_hours.get(location, ('07:30', '18:00'))
                    
                    # Calculate shift within availability and location hours
                    shift_start = avail_start
                    shift_end = avail_end
                    
                    shift_start_dt = datetime.strptime(shift_start, "%H:%M")
                    shift_end_dt = datetime.strptime(shift_end, "%H:%M")
                    available_hours = (shift_end_dt - shift_start_dt).total_seconds() / 3600
                    
                    if available_hours < 0.25:
                        continue
                    
                    # Cap at 6 hours for interns
                    shift_hours = min(available_hours, 6.0, hours_needed)
                    
                    actual_end_dt = shift_start_dt + timedelta(hours=shift_hours)
                    actual_end = actual_end_dt.strftime("%H:%M")
                    
                    job_type = self._location_to_job_type(location)
                    
                    test_shift = Shift(
                        id="temp",
                        employee_id=intern.id,
                        day_of_week=day,
                        start_time=shift_start,
                        end_time=actual_end,
                        job_type=job_type,
                        location=location,
                        hours=shift_hours,
                        color=get_location_color(location)
                    )
                    
                    can_assign, reason = self.can_assign_shift(intern, test_shift, schedule, None, approved_requests)
                    if can_assign:
                        test_shift.id = str(uuid.uuid4())
                        schedule.shifts.append(test_shift)
                        current = schedule.total_hours.get(intern.id, 0)
                        schedule.total_hours[intern.id] = current + test_shift.hours
                        hours_needed -= shift_hours
                        print(f"[SCHEDULER] Assigned intern {intern.name} to {location} on {day} ({shift_start}-{actual_end}, {shift_hours}h)")
                        break  # Move to next day after assigning one shift
        
        # Process managers separately (assign to management role, no location constraints)
        # Managers work Monday-Friday only (weekdays), one 8-hour shift per day
        weekday_order = ["monday", "tuesday", "wednesday", "thursday", "friday"]
        for manager in managers:
            current_hours = self.get_employee_weekly_hours(schedule, manager.id)
            manager_max_hours = self.get_employee_max_hours(manager)
            hours_remaining = manager_max_hours - current_hours
            
            if hours_remaining <= 0:
                continue
            
            print(f"[SCHEDULER] Processing manager {manager.name}: max_hours={manager_max_hours}, current={current_hours}, remaining={hours_remaining}")
            
            # Assign one 8-hour shift per weekday
            for day in weekday_order:
                hours_remaining = manager_max_hours - self.get_employee_weekly_hours(schedule, manager.id)
                if hours_remaining < 8:
                    break
                
                # Use default availability (available all day)
                avail = Availability(
                    id=str(uuid.uuid4()),
                    employee_id=manager.id,
                    week_start_date=week_start_date
                )
                
                # Assign one 8-hour shift (09:00-17:00) for this day
                test_shift = Shift(
                    id="temp",
                    employee_id=manager.id,
                    day_of_week=day,
                    start_time="09:00",
                    end_time="17:00",
                    job_type=JobType.MANAGEMENT,
                    location="manager activities",
                    hours=8.0,
                    color=None
                )
                
                can_assign, reason = self.can_assign_shift(manager, test_shift, schedule, avail, approved_requests)
                if can_assign:
                    test_shift.id = str(uuid.uuid4())
                    schedule.shifts.append(test_shift)
                    
                    current = schedule.total_hours.get(manager.id, 0)
                    schedule.total_hours[manager.id] = current + test_shift.hours
        
        elapsed = time.time() - start_time
        print(f"[SCHEDULER] Auto-schedule generation completed in {elapsed:.2f} seconds")
        print(f"[SCHEDULER] Total shifts assigned: {len(schedule.shifts)}")
        print(f"[SCHEDULER] Employees with hours: {len(schedule.total_hours)}")
        
        # Return schedule with timing metadata
        schedule.metadata = {
            "generation_time_seconds": round(elapsed, 2),
            "total_shifts": len(schedule.shifts),
            "employees_with_hours": len(schedule.total_hours)
        }
        
        return schedule
    
    def _location_to_job_type(self, location: str) -> JobType:
        """Map location string to JobType enum"""
        location_lower = location.lower()
        if 'call center' in location_lower or 'cc' in location_lower:
            return JobType.CALL_CENTER
        elif '2nd floor' in location_lower or 'f2' in location_lower or 'second' in location_lower:
            return JobType.SECOND_FLOOR
        elif '6th floor' in location_lower or 'f6' in location_lower or 'sixth' in location_lower:
            return JobType.SIXTH_FLOOR
        elif 'ground' in location_lower or 'gr' in location_lower:
            return JobType.GROUND_FLOOR
        elif 'event' in location_lower:
            return JobType.EVENT
        else:
            return JobType.DESK
    
    def optimize_schedule(self, schedule: WeeklySchedule) -> WeeklySchedule:
        """Optimize existing schedule for better coverage and preferences"""
        # TODO: Implement swap/exchange optimization
        return schedule

def generate_schedule(week_start_date: date) -> WeeklySchedule:
    """Convenience function to generate a schedule"""
    engine = SchedulingEngine()
    return engine.generate_auto_schedule(week_start_date)
