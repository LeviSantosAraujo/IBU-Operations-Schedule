from typing import List, Dict, Optional, Tuple
from datetime import date, timedelta
import uuid
from models import (
    Employee, Availability, WeeklySchedule, Shift, 
    JobType, Floor, AvailabilityType, EmployeeType, Event
)
from excel_store import (
    get_all_employees, get_availabilities, get_availability_for_week,
    save_schedule, get_system_config, get_availability_requests, get_events,
    get_all_week_schedule_dates, get_schedule_by_week
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
    
    def get_employee_historical_hours(self, employee_id: str, current_week_start: date) -> float:
        """Get total hours for an employee over the last 4 weeks"""
        total_hours = 0
        week_count = 0
        
        # Get the last 4 weeks before the current week
        for i in range(1, 5):
            week_date = current_week_date = current_week_start - timedelta(weeks=i)
            
            try:
                schedule = get_schedule_by_week(week_date)
                if schedule:
                    total_hours += schedule.total_hours.get(employee_id, 0)
                    week_count += 1
            except Exception:
                # Week might not exist or have no schedule
                pass
        
        return total_hours
    
    def get_all_employee_historical_hours(self, employees: List[Employee], current_week_start: date) -> Dict[str, float]:
        """Get historical hours for all employees over the last 4 weeks"""
        historical_hours = {}
        for emp in employees:
            historical_hours[emp.id] = self.get_employee_historical_hours(emp.id, current_week_start)
        return historical_hours
    
    def get_historical_shift_patterns(self, employee_id: str, current_week_start: date) -> Optional[Dict[str, List[Shift]]]:
        """Get shift patterns from the last 4 weeks for an employee, return the week with most hours"""
        best_week_shifts = None
        best_week_hours = 0
        best_week_date = None
        
        for i in range(1, 5):
            week_date = current_week_start - timedelta(weeks=i)
            try:
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
    
    def get_historical_job_preferences(self, employee_id: str, current_week_start: date) -> Dict[JobType, int]:
        """Analyze last 4 weeks to infer job preferences based on actual assignments"""
        job_type_counts = {}
        total_shifts = 0
        
        for i in range(1, 5):
            week_date = current_week_start - timedelta(weeks=i)
            try:
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
                         availability: Availability, approved_requests: Dict = None) -> Tuple[bool, str]:
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
        if current_hours + shift.hours > employee.max_hours_per_week:
            return False, f"Exceeds max hours ({employee.max_hours_per_week})"
        
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
                if not self.is_time_within_availability(shift.start_time, shift.end_time, day_request):
                    return False, f"Not available on {shift.day_of_week} (approved availability)"
        
        # Priority 4: Fall back to general availability
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
                                  availability: Availability, employee_preferences: Dict = None, 
                                  historical_preferences: Dict = None, current_hours: float = 0) -> float:
        """Score how good of a fit an employee is for a shift (higher = better)"""
        score = 0.0
        
        # Job preference weight (1-10, default 5)
        # Priority: availability request > general preferences > historical preferences > default
        pref_weight = 5
        if employee_preferences and employee.id in employee_preferences:
            prefs = employee_preferences[employee.id]
            pref_weight = prefs.get(shift.job_type, 5)
        elif employee.preferences and shift.job_type in employee.preferences:
            pref_weight = employee.preferences.get(shift.job_type, 5)
        elif historical_preferences and employee.id in historical_preferences:
            hist_prefs = historical_preferences[employee.id]
            pref_weight = hist_prefs.get(shift.job_type, 5)
        
        # Reduce preference weight as employee gets more hours assigned
        # First shifts: strong preference (100% weight)
        # Later shifts: more flexible (down to 50% weight at max hours)
        hours_ratio = current_hours / employee.max_hours_per_week if employee.max_hours_per_week > 0 else 0
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
                               location_requirements: Optional[Dict] = None) -> WeeklySchedule:
        """Generate an automatic schedule based on availability, preferences, and location requirements"""
        import time
        start_time = time.time()
        
        print(f"[SCHEDULER] Starting auto-schedule generation for week {week_start_date}")
        
        employees = [e for e in get_all_employees() if e.active]
        availabilities = {a.employee_id: a for a in get_availabilities(week_start_date)}
        
        # Load approved availability requests for this week
        approved_requests = {}
        employee_preferences = {}
        day_map = {0: 'monday', 1: 'tuesday', 2: 'wednesday', 3: 'thursday', 4: 'friday', 5: 'saturday', 6: 'sunday'}
        try:
            all_requests = get_availability_requests()
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
                                else:
                                    # For time range availability, mark as OFF during that time
                                    # The scheduler will check time ranges when assigning shifts
                                    approved_requests[emp_id][day_name] = AvailabilityType.OFF

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
        
        # Load events for this week
        events = get_events(week_start_date)
        
        # Calculate historical job preferences for all employees
        historical_job_preferences = {}
        for emp in employees:
            hist_prefs = self.get_historical_job_preferences(emp.id, week_start_date)
            if hist_prefs:
                historical_job_preferences[emp.id] = hist_prefs
        
        # Create empty schedule
        schedule = WeeklySchedule(
            id=str(uuid.uuid4()),
            week_start_date=week_start_date,
            shifts=[],
            total_hours={}
        )
        
        # Default location requirements based on 4-week analysis if none provided
        if not location_requirements:
            location_requirements = {
                'call center': {"monday": 4, "tuesday": 4, "wednesday": 4, "thursday": 4, "friday": 4, "saturday": 3, "sunday": 3},
                '2nd floor': {"monday": 3, "tuesday": 3, "wednesday": 3, "thursday": 3, "friday": 3, "saturday": 2, "sunday": 2},
                'ground floor': {"monday": 1, "tuesday": 1, "wednesday": 1, "thursday": 1, "friday": 1, "saturday": 1, "sunday": 1},
                '6th floor': {"monday": 2, "tuesday": 2, "wednesday": 2, "thursday": 2, "friday": 2, "saturday": 1, "sunday": 1},
                'working from home': {"monday": 0, "tuesday": 0, "wednesday": 0, "thursday": 0, "friday": 0, "saturday": 0, "sunday": 0},
                '80 bloor': {"monday": 0, "tuesday": 0, "wednesday": 0, "thursday": 0, "friday": 0, "saturday": 0, "sunday": 0},
            }
        
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
        
        for event in events:
            event_day = event.date.strftime("%A").lower()
            if event_day not in self.day_order:
                print(f"[SCHEDULER] Skipping event '{event.name}' - day '{event_day}' not in schedule")
                continue
            
            # Calculate event duration in hours
            from datetime import datetime
            start_dt = datetime.strptime(event.start_time, "%H:%M")
            end_dt = datetime.strptime(event.end_time, "%H:%M")
            event_hours = (end_dt - start_dt).total_seconds() / 3600
            
            print(f"[SCHEDULER] Event '{event.name}' on {event_day} ({event.start_time}-{event.end_time}, {event_hours}h) needs {event.people_needed} people")
            
            assigned = 0
            attempts = 0
            assigned_employees = set()  # Track which employees already assigned to this event
            
            # Assign employees to event using exact event time
            while assigned < event.people_needed and attempts < 100:
                attempts += 1
                
                candidates = []
                # Skip managers in event staffing - they get management assignments only
                regular_employees_event = [e for e in employees if e.employee_type != EmployeeType.MANAGER]
                for emp in regular_employees_event:
                    # Skip if already assigned to this event
                    if emp.id in assigned_employees:
                        continue
                    
                    avail = availabilities.get(emp.id)
                    if not avail:
                        avail = Availability(
                            id=str(uuid.uuid4()),
                            employee_id=emp.id,
                            week_start_date=week_start_date
                        )
                    
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
                        event_name=event.name
                    )
                    
                    can_assign, reason = self.can_assign_shift(emp, test_shift, schedule, avail, approved_requests)
                    if can_assign:
                        current_hours = self.get_employee_weekly_hours(schedule, emp.id)
                        score = self.score_employee_for_shift(emp, test_shift, avail, employee_preferences, historical_job_preferences, current_hours)
                        candidates.append((score, emp, avail, test_shift))
                
                candidates.sort(key=lambda x: x[0], reverse=True)
                
                if candidates:
                    _, best_emp, best_avail, shift = candidates[0]
                    shift.id = str(uuid.uuid4())
                    schedule.shifts.append(shift)
                    
                    current = schedule.total_hours.get(best_emp.id, 0)
                    schedule.total_hours[best_emp.id] = current + shift.hours
                    
                    # Track unique locations for diversity
                    employee_locations[best_emp.id].add(event.location)
                    
                    assigned_employees.add(best_emp.id)
                    assigned += 1
                    print(f"[SCHEDULER] Assigned {best_emp.name} to event '{event.name}' ({assigned}/{event.people_needed})")
                else:
                    print(f"[SCHEDULER] No candidates found for event '{event.name}' (attempt {attempts})")
                    break
            
            print(f"[SCHEDULER] Event '{event.name}' staffing complete: {assigned}/{event.people_needed} assigned")
        
        # Phase 1-3: Regular Location Staffing
        print(f"[SCHEDULER] Location requirements: {location_requirements}")
        
        for day in self.day_order:
            for location, daily_req in location_requirements.items():
                needed = daily_req.get(day, 0)
                if needed == 0:
                    continue
                
                assigned = 0
                attempts = 0
                
                while assigned < needed and attempts < 50:
                    attempts += 1
                    
                    for start, end, hours in shift_patterns:
                        if assigned >= needed:
                            break
                        
                        candidates = []
                        # Skip managers in regular location staffing - they get management assignments only
                        regular_employees_phase1 = [e for e in employees if e.employee_type != EmployeeType.MANAGER]
                        for emp in regular_employees_phase1:
                            # Skip if employee has reached call center cap for this location
                            if location.lower() == 'call center' and call_center_hours.get(emp.id, 0) >= max_call_center_hours:
                                continue
                            
                            avail = availabilities.get(emp.id)
                            if not avail:
                                avail = Availability(
                                    id=str(uuid.uuid4()),
                                    employee_id=emp.id,
                                    week_start_date=week_start_date
                                )
                            
                            # Map location to job type
                            job_type = self._location_to_job_type(location)
                            
                            test_shift = Shift(
                                id="temp",
                                employee_id=emp.id,
                                day_of_week=day,
                                start_time=start,
                                end_time=end,
                                job_type=job_type,
                                location=location,
                                hours=hours
                            )
                            
                            can_assign, reason = self.can_assign_shift(emp, test_shift, schedule, avail, approved_requests)
                            if can_assign:
                                current_hours = self.get_employee_weekly_hours(schedule, emp.id)
                                score = self.score_employee_for_shift(emp, test_shift, avail, employee_preferences, historical_job_preferences, current_hours)
                                candidates.append((score, emp, avail, test_shift))
                        
                        candidates.sort(key=lambda x: x[0], reverse=True)
                        
                        if candidates:
                            _, best_emp, best_avail, shift = candidates[0]
                            shift.id = str(uuid.uuid4())
                            schedule.shifts.append(shift)
                            
                            current = schedule.total_hours.get(best_emp.id, 0)
                            schedule.total_hours[best_emp.id] = current + shift.hours
                            
                            # Track call center hours
                            if location.lower() == 'call center':
                                call_center_hours[best_emp.id] = call_center_hours.get(best_emp.id, 0) + shift.hours
                            
                            # Track unique locations for diversity
                            employee_locations[best_emp.id].add(location)
                            
                            assigned += 1
                            location_assignments[location][day] += 1
        
        # Phase 4: Fairness Phase - Ensure all employees reach max hours
        # Get historical hours for all employees (last 4 weeks)
        historical_hours = self.get_all_employee_historical_hours(employees, week_start_date)
        
        # Separate managers from regular employees
        managers = [e for e in employees if e.employee_type == EmployeeType.MANAGER]
        regular_employees = [e for e in employees if e.employee_type != EmployeeType.MANAGER]
        
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
                if current_hours >= emp.max_hours_per_week:
                    continue
                
                hours_remaining = emp.max_hours_per_week - current_hours
                if hours_remaining <= 0:
                    continue
                
                # Get availability, or use default if not submitted
                avail = availabilities.get(emp.id)
                if not avail:
                    # Employees without availability get default full-day availability
                    avail = Availability(
                        id=str(uuid.uuid4()),
                        employee_id=emp.id,
                        week_start_date=week_start_date
                    )
                
                # Try to mirror historical patterns first
                historical_patterns = self.get_historical_shift_patterns(emp.id, week_start_date)
                if historical_patterns and day in historical_patterns:
                    # Use historical shifts for this day as priority
                    for hist_shift in historical_patterns[day]:
                        hours_remaining = emp.max_hours_per_week - self.get_employee_weekly_hours(schedule, emp.id)
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
                            hours=hist_shift.hours
                        )
                        
                        can_assign, reason = self.can_assign_shift(emp, test_shift, schedule, avail, approved_requests)
                        if can_assign:
                            # Skip if this would exceed call center cap
                            if test_shift.location.lower() == 'call center':
                                current_cc_hours = call_center_hours.get(emp.id, 0)
                                if current_cc_hours + test_shift.hours > max_call_center_hours:
                                    continue
                            
                            # Prioritize location diversity: if employee already has this location, skip unless they need more hours
                            if test_shift.location in employee_locations.get(emp.id, set()):
                                # Only assign if they really need the hours (less than 80% of max)
                                current_hours = self.get_employee_weekly_hours(schedule, emp.id)
                                if current_hours >= emp.max_hours_per_week * 0.8:
                                    continue
                            
                            test_shift.id = str(uuid.uuid4())
                            schedule.shifts.append(test_shift)
                            
                            current = schedule.total_hours.get(emp.id, 0)
                            schedule.total_hours[emp.id] = current + test_shift.hours
                            
                            # Track call center hours
                            if test_shift.location.lower() == 'call center':
                                call_center_hours[emp.id] = call_center_hours.get(emp.id, 0) + test_shift.hours
                            
                            # Track unique locations for diversity
                            employee_locations[emp.id].add(test_shift.location)
                            
                            # Update location assignments
                            if test_shift.location in location_assignments:
                                location_assignments[test_shift.location][day] += 1
                
                # Then fill remaining hours with standard patterns
                for start, end, hours in shift_patterns:
                    # Re-check hours remaining before each shift
                    hours_remaining = emp.max_hours_per_week - self.get_employee_weekly_hours(schedule, emp.id)
                    if hours_remaining <= 0:
                        break
                    
                    if hours > hours_remaining:
                        continue
                    
                    # Try each regular location
                    for location in location_requirements.keys():
                        # Skip if location is event-related (events should not be overstaffed)
                        if location == 'event' or 'event' in location.lower():
                            continue
                        
                        # Skip if employee has reached call center cap
                        if location.lower() == 'call center' and call_center_hours.get(emp.id, 0) >= max_call_center_hours:
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
                            hours=hours
                        )
                        
                        can_assign, reason = self.can_assign_shift(emp, test_shift, schedule, avail, approved_requests)
                        if can_assign:
                            # Prioritize location diversity: if employee already has this location, skip unless they need more hours
                            if location in employee_locations.get(emp.id, set()):
                                # Only assign if they really need the hours (less than 80% of max)
                                current_hours = self.get_employee_weekly_hours(schedule, emp.id)
                                if current_hours >= emp.max_hours_per_week * 0.8:
                                    continue
                            
                            # Assign the shift
                            test_shift.id = str(uuid.uuid4())
                            schedule.shifts.append(test_shift)
                            
                            current = schedule.total_hours.get(emp.id, 0)
                            schedule.total_hours[emp.id] = current + test_shift.hours
                            
                            # Track call center hours
                            if location.lower() == 'call center':
                                call_center_hours[emp.id] = call_center_hours.get(emp.id, 0) + test_shift.hours
                            
                            # Track unique locations for diversity
                            employee_locations[emp.id].add(location)
                            
                            # Update location assignments (this allows overstaffing)
                            location_assignments[location][day] += 1
                            break  # Move to next shift pattern
        
        # Process managers separately (assign to management role, no location constraints)
        # Managers work Monday-Friday only (weekdays), one 8-hour shift per day
        weekday_order = ["monday", "tuesday", "wednesday", "thursday", "friday"]
        for manager in managers:
            current_hours = self.get_employee_weekly_hours(schedule, manager.id)
            hours_remaining = manager.max_hours_per_week - current_hours
            
            if hours_remaining <= 0:
                continue
            
            print(f"[SCHEDULER] Processing manager {manager.name}: max_hours={manager.max_hours_per_week}, current={current_hours}, remaining={hours_remaining}")
            
            # Assign one 8-hour shift per weekday
            for day in weekday_order:
                hours_remaining = manager.max_hours_per_week - self.get_employee_weekly_hours(schedule, manager.id)
                if hours_remaining < 8:
                    break
                
                avail = availabilities.get(manager.id)
                if not avail:
                    # Managers without availability get default full-day availability
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
                    hours=8.0
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
