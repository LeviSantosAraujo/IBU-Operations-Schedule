# Auto-Generate Schedule Tool Proposal

## Current State

The existing scheduler uses **floor-based requirements** (Ground, Second, Sixth floors) with fixed daily staffing numbers. It does not consider:
- Location-based staffing patterns
- Historical data from past schedules
- Employee hour limits as a primary constraint

## Proposed Enhancement

### 1. Location-Based Staffing Requirements

Based on the 4-week analysis (May 11 - June 7), the scheduler will use these average staffing targets:

| Location | Average Employees/Week | Daily Target (approx) |
|----------|----------------------|---------------------|
| Call Center | 23.0 | 4-5 per day |
| 2nd Floor | 17.3 | 3-4 per day |
| Ground Floor | 5.3 | 1-2 per day |
| Working From Home | 3.0 | 0-1 per day |
| 6th Floor | 1.0 | 0-1 per day |
| 80 Bloor | 1.0 | 0-1 per day |

**Note:** Daily targets are calculated as: (weekly average ÷ 5 weekdays) for Mon-Fri, with reduced weekend staffing.

### 2. Enhanced Scheduling Algorithm

The new algorithm will prioritize constraints in this order:

#### Priority 1: Employee Hour Limits
- **Check first:** Can the employee work this shift without exceeding their `max_hours_per_week`?
- If adding the shift would exceed the limit, skip this employee
- Goal: Ensure all employees reach their limits if possible

#### Priority 2: Day Off Constraints (Approved Requests)
- **Check second:** Does the employee have an approved Day Off request for this day?
- If yes, they cannot be assigned ANY shift for that day
- Day Off is treated as a hard constraint, not a location

#### Priority 3: Event Requirements
- **Check third:** Are there events that need staffing for this day?
- Events are created by managers with specified:
  - Number of people needed
  - Location where event happens
  - Time range
- Assign employees to events before regular locations
- Events take priority over regular location staffing

#### Priority 4: Regular Location Requirements
- **Check fourth:** Does this location need more staff for this day?
- Track assigned employees per location per day
- Stop assigning to a location once daily target is met
- Allow flexibility: if no other location needs staff, can exceed target

#### Priority 5: Approved Availability Requests (Non-Day-Off)
- **Check fifth:** Does the employee have an approved availability request for this day?
- If yes, the shift must fit within the approved time window
- Approved requests override general availability

#### Priority 6: General Availability
- **Check sixth:** Is the employee generally available for this day/time?
- Use their weekly availability submission
- Must fit within their availability window

#### Priority 7: Employee Preferences
- **Check seventh:** Does the employee prefer this job type/location?
- Higher preference score = higher priority for assignment
- Used as tiebreaker when multiple employees are eligible

### 3. Shift Assignment Strategy

#### Phase 0: Event Staffing (New)
1. **Before any regular locations**, check for events created by manager
2. For each event:
   - Assign specified number of employees
   - Consider availability, hour limits, preferences
   - Event location is where the employee will work
3. Events take priority over all regular location staffing
4. If no events exist, skip to Phase 1

#### Phase 1: High-Priority Locations
1. Start with Call Center (highest staffing need: 23/week)
2. Assign shifts to fill daily targets (4-5 per day)
3. Prioritize employees with high Call Center preferences

#### Phase 2: Medium-Priority Locations
1. Move to 2nd Floor (17.3/week)
2. Assign shifts to fill daily targets (3-4 per day)
3. Prioritize employees with high 2nd Floor preferences

#### Phase 3: Low-Priority Locations
1. Fill Ground Floor (5.3/week), WFH (3/week), 6th Floor (1/week), 80 Bloor (1/week)
2. These are often filled by specific employees or as overflow

#### Phase 4: Fill Employee Hour Gaps
1. After location targets are met, check which employees haven't reached their hour limits
2. Assign additional shifts to help them reach their limits
3. Only if consistent with availability and preferences

### 4. Event Creation Workflow (New)

Before auto-generating a schedule, managers can create events for the week:

#### Event Creation UI
Manager clicks "Create Event" and fills in:
```
Event Name: [Summer Party]
Date: [Monday, June 8]
Time Range: [18:00] to [22:00]
Location: [Ground Floor]
People Needed: [3]
Description: [Optional: Annual summer celebration]
```

#### Multiple Events
- Managers can create multiple events for the same week
- Events can be on different days/times/locations
- Each event specifies its own staffing needs

#### Event Storage
- Events are stored per week
- Visible in the schedule grid with special styling
- Can be edited or deleted before schedule generation

### 5. User Interface for Managers

#### Step 1: Event Creation (Optional but Recommended)
When manager opens ScheduleManager for a new week:
```
⚠️ No events created for this week
Would you like to create events before generating the schedule?

[Create Events] [Skip Events] [Generate Without Events]
```

- **Create Events:** Opens event creation modal
- **Skip Events:** Proceeds to generation without events (regular staffing only)
- **Generate Without Events:** Skips event creation, generates schedule with regular location targets only

#### Step 2: Auto-Generate Options

#### Option A: Quick Generate (One-Click)
- **Action:** Manager clicks "Auto-Generate Schedule"
- **Behavior:** Uses the 4-week averages automatically
- **If events exist:** Assigns employees to events first, then regular locations
- **If no events:** Assigns to regular locations only
- **Output:** Full schedule generated with location-based staffing
- **Best for:** Standard weeks with no special events

#### Option B: Custom Requirements
- **Action:** Manager adjusts location targets before generating
- **UI:** Sliders or input fields for each location:
  ```
  Call Center: [4] employees/day (default: 4-5)
  2nd Floor: [3] employees/day (default: 3-4)
  Ground Floor: [1] employees/day (default: 1-2)
  WFH: [0] employees/day (default: 0-1)
  6th Floor: [0] employees/day (default: 0-1)
  80 Bloor: [0] employees/day (default: 0-1)
  ```
- **Behavior:** Generates schedule with custom targets
- **Best for:** Weeks with events, reduced staffing, or special needs

#### Option C: Week-by-Week Adjustment
- **Action:** Manager can set different targets for each day
- **UI:** Calendar view with location targets per day
- **Example:**
  ```
  Monday: CC=5, 2F=4, GF=2
  Tuesday: CC=4, 2F=3, GF=1 (event day)
  Wednesday: CC=5, 2F=4, GF=2
  ...
  ```
- **Behavior:** Generates schedule with day-specific targets
- **Best for:** Weeks with varying daily needs

### 6. Validation & Warnings

The system will warn managers if:
- **No events created:** Advises manager to create events before generating (but allows skipping)
- **Insufficient staff for events:** Not enough employees available to meet event staffing needs
- **Insufficient staff for locations:** Not enough employees available to meet location targets
- **Under-utilized staff:** Many employees won't reach their hour limits
- **Over-utilized staff:** Some employees would exceed their limits to meet targets
- **Availability conflicts:** Many approved requests conflict with targets/events

**Example warnings:**
```
⚠️ No events created for this week
Would you like to create events before generating the schedule?
[Create Events] [Skip Events] [Generate Without Events]

⚠️ Warning: Cannot meet event "Summer Party" staffing of 3 people
- Only 2 employees are available for Monday 18:00-22:00
- Consider: Reducing event staffing or checking availability

⚠️ Warning: Cannot meet Call Center target of 5 employees on Monday
- Only 3 employees are available for Call Center shifts (after event staffing)
- Consider: Reducing target or checking availability
```

### 7. Implementation Plan

#### Step 1: Update Data Model
- Add `Event` model for storing events (name, date, time, location, people_needed)
- Add `location` field to Shift model (already exists)
- Add `location_requirements` to system config
- Store historical location staffing data
- Add events storage per week

#### Step 2: Enhance Scheduler Algorithm
- Replace floor-based requirements with location-based
- Implement priority order (limits → day off → events → location → availability → preferences)
- Add event staffing phase (Phase 0)
- Add location tracking per day
- Handle Day Off as hard constraint (not location)

#### Step 3: Update API Endpoints
- Add endpoint to create/edit/delete events
- Add endpoint to get events for a week
- Add endpoint to get/set location requirements
- Add endpoint to get historical location averages
- Update generate schedule endpoint to accept location targets and events

#### Step 4: Update Frontend
- Add event creation modal UI
- Add event list/edit/delete UI
- Add location target configuration UI
- Add validation warnings display (including event staffing warnings)
- Update ScheduleManager to show location-based generation with event support

### 8. Example Workflow

**Manager wants to generate schedule for week of June 8-14:**

1. Manager opens ScheduleManager
2. System shows advisory:
   ```
   ⚠️ No events created for this week
   Would you like to create events before generating the schedule?
   
   [Create Events] [Skip Events] [Generate Without Events]
   ```
3. Manager clicks "Create Events"
4. Manager creates event:
   ```
   Event Name: Summer Party
   Date: Monday, June 8
   Time Range: 18:00 to 22:00
   Location: Ground Floor
   People Needed: 3
   Description: Annual summer celebration
   [Save Event]
   ```
5. Manager clicks "Auto-Generate Schedule"
6. System shows:
   ```
   Using 4-week average staffing targets:
   - Call Center: 4-5 employees/day
   - 2nd Floor: 3-4 employees/day
   - Ground Floor: 1-2 employees/day
   - WFH: 0-1 employees/day
   - 6th Floor: 0-1 employees/day
   - 80 Bloor: 0-1 employees/day
   
   Events for this week:
   - Summer Party (Mon 18:00-22:00, Ground Floor, 3 people)
   
   [Adjust Targets] [Generate with Defaults]
   ```
7. Manager clicks "Generate with Defaults"
8. System generates schedule, showing:
   ```
   ✅ Assigned 3 employees to "Summer Party" event
   ✅ Generated 20 shifts for Call Center (reduced due to event)
   ✅ Generated 14 shifts for 2nd Floor (reduced due to event)
   ✅ Generated 2 shifts for Ground Floor (reduced due to event)
   ✅ Generated 3 shifts for WFH
   ✅ Generated 1 shift for 6th Floor
   ✅ Generated 1 shift for 80 Bloor
   
   📊 Employee Hour Utilization:
   - 15/20 employees reached their hour limits
   - 5 employees are under by 2-5 hours (availability constraints)
   ```
9. Manager reviews and adjusts as needed
10. Manager saves/publishes schedule

## User Decisions

Based on user feedback:

1. **Location targets per day of week:** NO - Use consistent daily targets based on 4-week averages
2. **Weekend staffing ratios:** NO - Use same ratios as weekdays
3. **Manager event creation:** YES - Managers can create/personalize events for the week with staffing needs
4. **Learning from adjustments:** OPTIONAL - Can be implemented if not too complex (no AI processing required)
5. **Day Off handling:** Option B - Treat as hard constraint (approved Day Off requests prevent any shift assignment that day)
