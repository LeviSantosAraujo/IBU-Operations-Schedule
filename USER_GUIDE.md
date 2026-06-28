# IBU Operations Schedule - User Guide

## Table of Contents
- [For Employees](#for-employees)
- [For Managers](#for-managers)
- [FAQ](#faq)

---

## For Employees

### Accessing the System
1. Go to the IBU Operations Schedule URL
2. Select your name from the dropdown
3. If you're a manager, enter your password
4. Click "Login"

### Submitting Availability
Navigate to "My Availability" to submit your weekly availability:

1. **Select Your Name** from the dropdown
2. **Choose Availability Type** for each day:
   - **Blank** - Available anytime/all day
   - **Until 12pm** - Available until 12:00 PM
   - **Until 3pm** - Available until 3:00 PM
   - **After 3:30pm** - Available after 3:30 PM
   - **12-3pm** - Available between 12:00 PM and 3:00 PM
   - **After 12pm (EOD)** - Available after 12:00 PM until end of day
   - **Before 12 & After 3:30** - Available before 12:00 PM and after 3:30 PM
   - **OFF** - Not available (day off)

3. **Submit Before Thursday** for next week's schedule

### Availability Requests
Request specific availability changes with manager approval:

1. Click "Request Availability Change"
2. **Set Date Range** - Choose start and end dates
3. **Choose Request Type**:
   - **Available** - Request to be available during specific times
   - **Day Off** - Request a day off
4. **Select Days** - Check the days this request applies to
5. **Set Time Range** (for availability requests)
6. **Set Job Preferences** - Rank locations 1-10 (higher = preferred)
7. **Add Comments** (optional) - Explain your request
8. Click "Submit Availability Request"

**View Request History:**
- See all your requests with status (Pending/Approved/Rejected)
- Approved requests appear as locked shifts (🔒) in your schedule
- Day off requests show as black boxes with "🔒 Day Off"
- Availability requests show as gray boxes with time range

### Viewing Your Schedule
Navigate to "Schedule" to view your assigned shifts:
- See your shifts for the selected week
- Other employees' shifts are dimmed (privacy)
- Locked availability requests (🔒) cannot be overridden
- Color-coded by location
- Time ranges shown clearly

---

## For Managers

### Accessing the System
1. Go to the IBU Operations Schedule URL
2. Select your name from the dropdown
3. Enter your password
4. Click "Login"

### Creating Schedules

#### Step 1: Select Week
Choose the week starting date from the date picker

#### Step 2: Auto-Generate Schedule
Click "Auto-Generate" to open the configuration modal

**Configure Staffing Targets (Recommended):**
- Set how many people needed per location per day
- Locations: Call Center, 2nd Floor, Ground Floor, 6th Floor, 80 Bloor, WFH
- Settings persist for future schedule generations
- Adjust as needed for each week

**Create Events (Optional):**
- Click "+ Add Event"
- Enter event name, date, time range, and location
- People needed is automatically set from staffing targets
- Events take priority over regular location staffing

**Set Employee Preferences (Optional but Recommended):**
- Click "Employee Preferences" tab
- Set 1-10 preference for each location for each employee
- Event preference determines priority for event staffing
- Manager-set preferences override employee-set preferences
- Employee choices are shown in red with border

**Generate Schedule:**
- Click "Generate Schedule"
- Algorithm prioritizes: hour limits → Day Off → events → locations → availability → manager preferences → employee preferences

#### Step 3: Review and Adjust
- **Add Shift** - Manually add shifts
- **Remove Shift** - Click trash icon on any shift
- **Clear Schedule** - Remove all shifts while preserving events
- **Floor Coverage** - View coverage for all floors (red = no coverage, yellow = 1 person, green = 2+ people)

#### Step 4: Save and Publish
- Click "Save" to save changes
- Click "Publish" when finalized

### Managing Availability Requests
Check the notification bell (top right corner):
- View all pending availability requests
- Each request shows: employee name, request type, days, date range, time range, and comments
- Click "Approve" or "Reject" to process requests
- Approvals create locked shifts for the entire date range
- Employee preferences are stored and used by the auto-scheduler
- Use "Mark all read" button to dismiss all notifications at once

### Employee Management
Navigate to "Employees" to:
- **Add Employee** - Add new employees (student workers, interns, managers)
- **Set Max Hours** - Set maximum hours per week (interns: 15h, students: 24h, managers: 80h)
- **Edit Employee** - Update employee details
- **Delete Employee** - Remove employees (automatically cleans up associated availability requests)
- **View Availabilities** - See employee availabilities and approved requests in the "Availabilities" tab

### Database Export
Navigate to "Database" to:
- **Export to Excel** - Download current data as Excel file
- Excel uses weekly sheet format (e.g., "June 15-21")
- Shifts formatted as "9a-5p" for readability
- Used for historical records and offline viewing
- **Note:** Excel import functionality has been removed for data integrity (only GitHub JSON is the source of truth)

### Hours Summary
At the bottom of the Schedule page:
- See hours scheduled per employee
- View remaining hours before hitting limits
- Over-limit warnings shown in red

### System Monitoring Dashboard (Admin)
Access via `/admin/dashboard` (requires admin authentication):
- **Real-time System Health** - Monitor backend, frontend, GitHub, and system metrics
- **Backend Logs** - View last 500 backend log entries in real-time
- **GitHub Health** - Monitor GitHub API status, rate limits, and file update timestamps
- **System Metrics** - Track cache performance, active sessions, and error rates
- **Auto-Refresh** - Dashboard refreshes every 5 minutes automatically

---

## FAQ

### For Employees

**Q: When should I submit my availability?**
A: Submit before Thursday for next week's schedule.

**Q: What if I need to change my availability?**
A: Submit an availability request with the new times and date range. Your manager will review and approve/reject it.

**Q: How do I request a day off?**
A: Use the availability request feature, select "Day Off" as the request type, and choose the dates.

**Q: Can I see other employees' schedules?**
A: No, for privacy reasons you can only see your own schedule. Other employees' shifts are dimmed.

**Q: What do the locked shifts (🔒) mean?**
A: These are approved availability requests that cannot be overridden by managers.

### For Managers

**Q: How do I set staffing targets?**
A: Click "Auto-Generate" and configure staffing targets in the modal. Settings persist for future generations.

**Q: What's the difference between manager and employee preferences?**
A: Manager-set preferences override employee-set preferences in the auto-generation algorithm.

**Q: How do events work?**
A: Events are special locations with specific staffing needs. They take priority over regular location staffing and are staffed with the exact number needed.

**Q: Can I manually edit the auto-generated schedule?**
A: Yes, you can add, remove, or clear shifts after auto-generation.

**Q: What happens when I approve an availability request?**
A: It creates locked shifts for the entire date range on the specific days requested. These cannot be overridden.

**Q: Where is the Excel import feature?**
A: Excel import has been removed for data integrity. The system now uses GitHub JSON files as the single source of truth. You can still export to Excel for historical records.

**Q: How do I access the admin dashboard?**
A: Go to `/admin/dashboard` and authenticate with your employee ID and password.

---

## Technical Support

For issues or questions:
- **Developer**: Levi Araujo
- **Email**: laraujo.8304@myibu.ca

---

## Version History

**Current Version:**
- Excel import functionality removed (data integrity)
- Excel export uses weekly sheet format (e.g., "June 15-21")
- Shifts formatted as "9a-5p" for readability
- GitHub JSON files as single source of truth
- CORS wildcard origin (temporary fix for Excel download)
