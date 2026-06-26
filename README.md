# IBU Operations team schedule

A comprehensive automated scheduling system built with Python (FastAPI) and React. This system handles employee availability, weighted auto-scheduling, location-based staffing, event management, and multi-week storage.

## Deployment Notes
- Uses Vercel for hosting with two separate projects:
  - Backend: `ibu-operations-schedule` (Python FastAPI)
  - Frontend: `ibu-operations-schedule-frontend` (React/Vite)
- Python dependencies in root requirements.txt
- Frontend built with Vite
- Data stored in GitHub (data branch) for persistence
- Authentication uses JWT tokens (stateless, works with serverless)
- Mobile-responsive design with card-based views on small screens

**Important for Vercel Deployment:**

**Backend Project (`ibu-operations-schedule`):**
- Set `GITHUB_TOKEN` environment variable in Vercel for GitHub data storage
- Set `GITHUB_REPO` environment variable (e.g., "LeviSantosAraujo/IBU-Operations-Schedule")
- Set `GITHUB_DATA_BRANCH` environment variable (default: "data")
- Set `JWT_SECRET` environment variable in Vercel for secure JWT token signing (REQUIRED - no default)
  - Generate a secure random secret: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
  - This secret is used to sign and verify JWT tokens for authentication
  - The application will fail to start without it

**Frontend Project (`ibu-operations-schedule-frontend`):**
- Set `VITE_API_URL` environment variable to point to backend API URL
- Root Directory: `frontend`
- Framework Preset: Vite
- Build Command: `npm run build`
- Output Directory: `dist`

**Architecture Overview:**
The system uses GitHub JSON files as the single source of truth for all data:
1. **GitHub JSON Storage** (`json_store.py`): Per-entity JSON files stored on GitHub data branch
   - employees.json, schedules.json, availabilities.json, availability_requests.json, notifications.json, system_config.json
   - Optimistic locking with SHA caching to handle concurrent writes safely
   - Fast read/write operations via GitHub Contents API
2. **Excel Export** (`/api/excel/download`): On-demand Excel generation from GitHub JSON
3. **Nightly Excel Commit** (Vercel Cron): Automated Excel generation and commit to GitHub at midnight

This ensures:
- Single source of truth (GitHub JSON files)
- Fast user feedback (direct writes to GitHub JSON)
- Data integrity (optimistic locking prevents race conditions)
- Excel export available on-demand for historical records

## Features

### For Employees
- **Availability Input**: Submit weekly availability with color-coded time slots
- **7 availability types** matching your original sheet:
  - Blank (Anytime/all day)
  - Until 12pm
  - Until 3pm
  - After 3:30pm
  - 12-3pm
  - After 12pm (EOD)
  - Before 12 & After 3:30
  - OFF
- **Availability Requests**: Request specific availability changes with manager approval
  - Set date ranges for each weekday
  - Choose request type: "Available" or "Day Off"
  - Specify time ranges for availability
  - Set job preferences (e.g., prefer Call Center, 2nd Floor)
  - View request history with status (Pending/Approved/Rejected)
  - **Day off requests now correctly register for the selected day** (fixed date mapping issue)
- **Schedule View**: View your own schedule with other employees' shifts dimmed if not assigned
- **Locked Shifts Display**: Approved availability requests appear as locked shifts (🔒) in your schedule
  - Day off requests show as black boxes with "🔒 Day Off"
  - Availability requests show as gray boxes with time range
  - These locked shifts cannot be overridden by managers

### For Managers
- **Auto-Schedule Generation**: Enhanced algorithm with 4 phases:
  - Phase 0: Event staffing (exact number needed, no overstaffing)
  - Phase 1-3: Regular location staffing (based on configurable staffing targets)
  - Phase 4: Fairness phase (ensures all employees reach max hours)
  - Considers last 4 weeks of historical data to balance workload
  - Prioritizes employees with fewer recent hours
  - Respects hour limits, Day Off, availability, and preferences
  - Manager-set preferences have highest priority over employee-set preferences
- **Staffing Targets Configuration**: Set how many people needed per location per day
  - Access via "Auto-Generate" modal before generating schedule
  - Configure targets for all locations: Ground Floor, 2nd Floor, 6th Floor, 80 Bloor
  - Call Center is a role/flag that can be combined with any location (e.g., "2nd Floor + Call Center")
  - The number represents people needed each day (applies to every day of the week)
  - Working from Home is not included in auto-generation (manager assigns on-demand)
  - Settings are saved and persist for future schedule generations
  - Manager can adjust targets at any time before generating
  - Event creation now uses staffing targets automatically (no manual people_needed input)
- **Employee Preferences Management**: Set job preferences for each employee
  - Access via "Employee Preferences" tab in Schedule view
  - Set 1-10 preference for all locations: Ground Floor, 2nd Floor, 6th Floor, Call Center, 80 Bloor, Working from Home, Event
  - Event preference determines priority for event staffing
  - Manager-set preferences override employee-set preferences in auto-generation
  - Managers can only modify manager_preferences (their choices for employees)
  - Managers cannot modify employee-submitted preferences (can only view them)
  - Employee choices are visually distinguished in red with border in the manager preferences UI
  - Changes are saved immediately
- **Event Management**: Create and manage events for the week
  - Specify event name, date, time range, and location
  - People needed is automatically set from staffing targets configuration
  - Events appear as dynamic filterable locations in sidebar
  - Toast notification shows events for 5 seconds after create/delete
  - Edit/delete event locations directly from sidebar
  - Events take priority over regular location staffing
  - Create events directly from the Auto-Generate modal
- **Manual Schedule Editing**: Add/remove shifts easily
- **Clear Schedule**: Remove all timeshifts for a week while preserving events and locations
  - Useful for starting fresh with the same events
  - Only clears employee shifts, not event definitions
- **Location Coverage Tracking**: View staffing across all locations
- **Hours Tracking**: Visual indicators for employees approaching hour limits
- **Multi-week Storage**: Access historical schedules
- **Availability Request Management**: Approve/reject employee availability requests
  - View pending requests in the notification bell (top right corner)
  - Click the bell icon to see pending requests with approve/reject buttons
  - Approvals create locked shifts for the entire date range in the schedule
  - Locked shifts appear as 🔒 in the schedule (black for day off, gray for availability)
  - Employee preferences are stored in locked shifts and used by scheduler
  - Optional manager comments for approvals (required for rejections)
  - Schedule automatically refreshes after approval to show locked shifts
  - **"Mark all read" button** - Quickly mark all notifications as read with one click
  - **Optimistic UI updates** - Notifications dismiss immediately with background sync
- **Employee Management**: Add, edit, and delete employees
  - Delete employees automatically cleans up associated availability requests from both staging and Excel
  - Deletion works even if employee only exists in staging layer
  - Loading indicators for all employee CRUD operations
- **Availabilities Tab**: View employee availabilities and approved requests
  - Shows detailed time ranges for approved availability requests (e.g., "09:00 - 12:00")
  - Displays both actual availabilities and approved availability requests
  - Day off requests show as "OFF"

### System Monitoring Dashboard (Admin)
- **Access**: `/admin/dashboard` (requires admin authentication with employee ID and password)
- **Real-time System Health**: Monitor backend, frontend, GitHub, and system metrics
- **Backend Logs**: View last 500 backend log entries in real-time
  - Logs are stored in-memory and reset on server restart
  - Newest logs appear first
  - Color-coded by log level (ERROR in red, WARNING in yellow, INFO in blue)
- **GitHub Health**: Monitor GitHub API status, rate limits, and file update timestamps
- **System Metrics**: Track cache performance, active sessions, and error rates
- **Per-Card Status Indicators**: Green/red status dots for each dashboard section
- **Auto-Refresh**: Dashboard refreshes every 5 minutes automatically
- **Session Tracking**: In-memory tracking of active user sessions (last 5 minutes)
- **Timestamp Display**: All timestamps shown in Toronto timezone (HH:MM:SS YYYY-MM-DD)
- **Frontend Start Time**: Shows last GitHub commit timestamp as proxy for deploy time

## Recent Improvements

### Cache Consistency (Serverless)
- Implemented SHA-based cache invalidation in `json_store.py`
- Fetches current SHA from GitHub on read to detect changes
- Prevents stale data across ephemeral serverless instances
- Ensures immediate data consistency after employee deletions/updates

### Employee View Privacy
- Fixed EmployeeScheduleView to show all employees' schedules
- Hides locked availability blocks (Pending/Approved/Rejected) for other employees
- Only shows own availability status to maintain privacy
- Managers still see all data

### Mobile Layout Improvements
- Shortened header title on mobile to prevent truncation
- Fixed NotificationBell dropdown positioning (fixed on mobile, absolute on desktop)
- Added proper spacing to location edit/delete controls
- All changes use responsive breakpoints (sm:, lg:) to preserve desktop layout

### Dashboard Enhancements
- Increased backend log retention from 200 to 500 rows
- Improved mobile responsiveness across all views

### Security Hardening
- Removed weak default ADMIN_SECRET_KEY (now requires environment variable)
- Removed wildcard CORS origin (only allows specific frontend domains)
- Added rate limiting to auth endpoints (10 attempts per 5 minutes per IP)
- Added ADMIN_SECRET_KEY to Vercel environment variables

### Locations
- Ground Floor (GR) - 7:30 AM - 6:00 PM
- 2nd Floor (2F) - 08:00 AM - 6:00 PM
- 6th Floor (6F) - 08:00 AM - 6:00 PM
- 80 Bloor - 08:30 AM - 6:00 PM
- Working From Home (WFH) - 08:00 AM - 6:00 PM
- Events (special location for event staffing - times defined per event)
- Call Center (CC) - Role/flag that can be combined with any location (e.g., "2nd Floor + Call Center")

## Tech Stack

- **Backend**: Python 3.9+, FastAPI, Pydantic, openpyxl
- **Frontend**: React 18, TypeScript, Tailwind CSS, Vite, react-datepicker
- **Data Storage**: Excel files (portable, no database needed)

## Installation

### Prerequisites
- Python 3.9 or higher
- Node.js 18 or higher
- npm or yarn

### Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment (recommended)
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set required environment variables
export JWT_SECRET="$(openssl rand -base64 32)"  # Generate secure secret
export GITHUB_TOKEN="your_github_token"
export GITHUB_REPO="owner/repo"

# Start the server
uvicorn main:app --reload --port 8000
```

The backend API will be available at `http://localhost:8000`

API documentation (auto-generated by FastAPI):
- **Local Development**: 
  - Swagger UI: `http://localhost:8000/docs`
  - ReDoc: `http://localhost:8000/redoc`
- **Production**:
  - Swagger UI: `https://ibu-operations-schedule.vercel.app/docs`
  - ReDoc: `https://ibu-operations-schedule.vercel.app/redoc`

### Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

The frontend will be available at `http://localhost:3000`

## Project Structure

```
Schedule Sheet IBU/
├── api/
│   ├── backend/
│   │   ├── uploads/              # Excel file uploads (local dev)
│   │   ├── main.py               # FastAPI application entry point
│   │   ├── models.py             # Pydantic data models (Employee, Event, etc.)
│   │   ├── excel_store.py        # Excel file operations (for export)
│   │   ├── data_store_excel.py   # Excel-based data operations (legacy)
│   │   ├── github_storage.py     # GitHub Contents API integration
│   │   ├── json_store.py         # GitHub JSON file operations (primary storage)
│   │   ├── storage.py            # Storage abstraction (blob/local/memory)
│   │   ├── scheduler.py          # Enhanced scheduling algorithm
│   │   ├── auth.py               # JWT-based authentication
│   │   └── requirements.txt      # Python dependencies
│   ├── index.py                  # Vercel serverless entry point
│   └── requirements.txt          # Root Python dependencies
├── frontend/
│   ├── src/
│   │   ├── components/       # React components
│   │   │   ├── AvailabilityInput.tsx
│   │   │   ├── ScheduleManager.tsx
│   │   │   ├── EmployeeScheduleView.tsx
│   │   │   ├── EmployeeManagement.tsx
│   │   │   ├── NotificationBell.tsx
│   │   │   └── FloorCoverage.tsx
│   │   ├── api.ts            # API client with Axios interceptors
│   │   ├── auth.ts           # Authentication utilities
│   │   ├── App.tsx           # Main app component with routing
│   │   └── main.tsx          # Entry point
│   ├── .env.production       # Production environment variables
│   ├── package.json          # Node dependencies
│   └── vite.config.ts        # Vite configuration
├── requirements.txt          # Root Python dependencies
└── README.md
```

## Usage Guide

### 1. Employee Management
Navigate to "Employees" to:
- Add new employees (student workers, interns, managers)
- Set maximum hours per week
- Edit or deactivate employees

### 2. Submitting Availability
Navigate to "My Availability" to:
- Select your name from the dropdown
- For each weekday, set:
  - Date range (start and end dates)
  - Request type: "Available" or "Day Off"
  - Time range (for availability requests)
  - Job preferences (e.g., Call Center: 8, 2nd Floor: 5)
- Click "Submit Availability Request" to send to manager
- View your request history with status (Pending/Approved/Rejected)
- Submit before Thursday for next week's schedule

### 3. Creating Schedules (Manager)
Navigate to "Schedule" to:
1. Select the week starting date
2. Click **Auto-Generate** to open the configuration modal
3. **Configure Staffing Targets** (optional but recommended):
   - Set how many people needed per location per day
   - Settings persist for future schedule generations
   - Adjust as needed for each week
4. **Create Events** (optional):
   - Click "+ Add Event" in the modal
   - Enter event name, date, time range, and location
   - People needed is automatically set from staffing targets
   - Events take priority over regular location staffing
5. **Set Employee Preferences** (optional but recommended):
   - Click "Employee Preferences" tab
   - Set 1-10 preference for each location for each employee
   - Event preference determines priority for event staffing
   - Manager-set preferences override employee-set preferences
6. Click **Generate Schedule** to create initial schedule
   - Algorithm prioritizes: hour limits → Day Off → events → locations → availability → manager preferences → employee preferences
7. Review and adjust:
   - Click **Add Shift** to manually add shifts
   - Click trash icon on any shift to remove it
   - Click **Clear Schedule** to remove all shifts while preserving events (useful for starting fresh)
8. Click **Save** to save changes
9. Click **Publish** when finalized

### 4. Floor Coverage
Navigate to "Floor Coverage" to:
- View coverage for all floors across the week
- Click any cell (showing employee count) to see who's scheduled
- Red = no coverage, Yellow = 1 person, Green = 2+ people

### 5. Managing Availability Requests (Manager)
Navigate to "Schedule" and check the notification bell (top right):
- View all pending availability requests from employees
- Each request shows: employee name, request type, days, date range, time range, and comments
- Click "Approve" or "Reject" to process requests
- Approvals create locked shifts for the entire date range on the specific days requested
- Employee preferences are stored and used by the auto-scheduler
- Use "Mark all read" button to dismiss all notifications at once
- Notifications update optimistically (dismiss immediately, sync in background)

### 6. Employee Management (Manager)
Navigate to "Employees" to:
- Add new employees (student workers, interns, managers)
- Set maximum hours per week
- Edit or deactivate employees
- Delete employees (automatically cleans up associated availability requests)
- View employee availabilities in the "Availabilities" tab
  - Shows actual availabilities and approved requests
  - Displays detailed time ranges for approved requests

### 7. Hours Summary
At the bottom of the Schedule page, see:
- Hours scheduled per employee
- Remaining hours before hitting limits
- Over-limit warnings (red)

## Data Storage

The system uses GitHub JSON files as the single source of truth for all data:

### GitHub JSON Files (Primary Storage)
- Stored on GitHub data branch as per-entity JSON files:
  - `employees.json` - Employee records
  - `schedules.json` - Weekly schedules with shifts
  - `availabilities.json` - Employee availability data
  - `availability_requests.json` - Availability change requests
  - `notifications.json` - User notifications
  - `system_config.json` - System configuration including events and staffing targets
- Optimistic locking with SHA caching to handle concurrent writes safely
- Fast read/write operations via GitHub Contents API
- Single source of truth - no Excel fallback or sync needed

### Excel Export (On-Demand)
- Available via `/api/excel/download` endpoint
- Generates Excel file from current GitHub JSON data
- Contains all entities as separate sheets (Employees, Schedules, Availabilities, etc.)
- Used for historical records and data export

### Nightly Excel Commit (Automated)
- Vercel Cron job runs at midnight daily
- Generates Excel from GitHub JSON data
- Commits Excel file to GitHub data branch
- Provides daily Excel snapshots for backup purposes

**Benefits:**
- Single source of truth (GitHub JSON files)
- Fast user feedback (direct writes to GitHub JSON)
- Data integrity (optimistic locking prevents race conditions)
- Excel export available on-demand for historical records
- Automated daily Excel backups via cron job

## Scheduling Algorithm

The enhanced auto-scheduler uses a priority-based approach with 4 phases:

### Phase 0: Event Staffing
- Assigns employees to manager-created events first
- Staffs events with the exact number of people needed (no overstaffing for events)
- Events take priority over all regular location staffing

### Phase 1-3: Regular Location Staffing
- Fills daily staffing targets based on manager configuration:
  - 2nd Floor: configurable (default 3 employees/day)
  - Ground Floor: configurable (default 1 employee/day)
  - 6th Floor: configurable (default 2 employees/day)
  - 80 Bloor: configurable (default 0-1 employees/day)
- Staffing targets are set via Auto-Generate modal and persist for future generations
- Respects all constraints: hour limits, Day Off, availability requests, preferences
- Each employee assigned to only one shift per location per day
- Working from Home is not included in auto-generation (manager assigns on-demand)

### Call Center Role Assignment
- After location staffing, assigns call center role to existing shifts
- Call Center is a role/flag that can be combined with any location
- Number of call center roles is set via staffing target (people per day)
- Assigned based on employee call center preferences (higher preference = priority)
- Respects call center hour cap (max 16 hours per week per employee)
- Displayed as blue "CC" badge next to location in schedule

### Phase 4: Fairness Phase (Maximization)
- Skipped when manager staffing targets are provided (only assigns specified staffing)
- When enabled, ensures all employees reach their maximum hours capacity
- Considers last 4 weeks of historical schedule data
- Prioritizes employees who have worked fewer hours recently
- Adds extra shifts to regular locations (can overstaff locations)
- Does NOT add shifts to events (events stay at exact staffing)
- Goal: Every employee works up to their max hours (interns: 15h, students: 24h, managers: 80h)

### Priority Order (within each phase)
1. **Employee Hour Limits** - Ensures no employee exceeds their max hours per week
2. **Day Off Constraints** - Approved Day Off requests block all shifts for that day
3. **Approved Availability Requests** - Respects approved availability changes
4. **General Availability** - Fits shifts within employee availability windows
5. **Employee Preferences** - Uses job preferences as tiebreaker

### Event Handling
- Events are created by managers with specific staffing needs
- Events are staffed with the exact number needed (no overstaffing)
- If no events exist, system advises manager but allows proceeding without events
- Event shifts are marked with event name and location
- Events appear as dynamic filterable locations in the sidebar

## Configuration

The system uses configurable staffing targets for each location. These are set by managers via the Auto-Generate modal and persist for future schedule generations.

Default staffing targets (can be customized):
- Call Center: 4 employees/day
- 2nd Floor: 3 employees/day
- Ground Floor: 1 employee/day
- 6th Floor: 2 employees/day
- WFH: 1 employee/day
- 80 Bloor: 1 employee/day

Staffing targets are stored in the Config sheet of the Excel file and can be adjusted at any time before generating a schedule.

## Future Enhancements

- Drag-and-drop shift reassignment
- Email notifications when schedule is published
- Excel export/import
- Recurring availability templates
- Shift swap requests between employees
- Mobile app
- Conflict detection UI
- Visual schedule comparison across weeks

## Troubleshooting

**Backend won't start:**
- Check Python version: `python --version` (need 3.9+)
- Verify port 8000 is free: `lsof -i :8000`

**Frontend won't start:**
- Check Node version: `node --version` (need 18+)
- Try clearing npm cache: `npm cache clean --force`
- Delete node_modules and reinstall: `rm -rf node_modules && npm install`

**API connection errors:**
- Ensure backend is running on port 8000
- Check CORS settings in `backend/main.py`
- Verify proxy config in `frontend/vite.config.ts`

## Development

### Adding New Job Types
Edit `backend/models.py`:
```python
class JobType(str, Enum):
    # ... existing types
    NEW_TYPE = "new_type"
```

### Modifying Availability Types
Edit the `AvailabilityType` enum and `AVAILABILITY_COLORS` in `backend/models.py`, then update the frontend's `availabilityOptions` in `frontend/src/components/AvailabilityInput.tsx`.

### API Testing
Use the built-in Swagger UI at `http://localhost:8000/docs` to test all endpoints.

## License

Internal use only for IBU scheduling operations.

## Support

For issues or feature requests, contact:
- **Developer**: Levi Araujo
- **Email**: laraujo.8304@myibu.ca
