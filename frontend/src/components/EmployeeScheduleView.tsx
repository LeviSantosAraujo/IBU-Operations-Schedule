import { useState, useEffect } from 'react'
import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'
import { format, addDays, startOfWeek } from 'date-fns'
import { getSchedule, getEmployees, createAvailabilityRequest, getMyAvailabilityRequests } from '../api'
import { Calendar, ChevronLeft, ChevronRight, Clock, MapPin, X } from 'lucide-react'
import { auth } from '../auth'

const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

const availabilityTypes = [
  { id: 'blank', name: 'Anytime/All Day', color: '#FFFFFF' },
  { id: 'until_12pm', name: 'Until 12pm', color: '#90EE90' },
  { id: 'until_3pm', name: 'Until 3pm', color: '#87CEEB' },
  { id: 'after_330pm', name: 'After 3:30pm', color: '#FFB6C1' },
  { id: '12_3', name: '12-3pm', color: '#ADD8E6' },
  { id: 'after_12_eod', name: 'After 12pm - EOD', color: '#FFDAB9' },
  { id: 'before_12_after_330', name: 'Before 12pm & After 3:30pm', color: '#DDA0DD' },
  { id: 'off', name: 'Off', color: '#000000' },
  { id: 'day_off', name: 'Day Off', color: '#000000' },
]

const jobTypes = [
  { id: 'ground_floor', name: 'Ground Floor' },
  { id: 'second_floor', name: '2nd Floor' },
  { id: 'sixth_floor', name: '6th Floor' },
  { id: 'call_center', name: 'Call Center' },
  { id: 'event', name: 'Event' },
]
const locationColors: any = {
  'event': 'loc-event',
  'ground': 'loc-ground',
  'ground floor': 'loc-ground',
  'gf': 'loc-ground',
  'gr': 'loc-ground',
  'second': 'loc-second',
  '2nd floor': 'loc-second',
  '2f': 'loc-second',
  'f2': 'loc-second',
  'sixth': 'loc-sixth',
  '6th floor': 'loc-sixth',
  '6f': 'loc-sixth',
  'f6': 'loc-sixth',
  'call center': 'loc-call-center',
  'cc': 'loc-call-center',
  '80 bloor': 'loc-80-bloor',
  'bloor': 'loc-80-bloor',
  'wfh': 'loc-wfh',
  'working from home': 'loc-wfh',
  'day off': 'loc-day-off',
  'day_off': 'loc-day-off'
}

const locations = [
  { id: 'all', name: 'All Locations', dotColor: '' },
  { id: 'event', name: 'Event', dotColor: '#F97316' },
  { id: 'ground floor', name: 'Ground Floor', dotColor: '#3B82F6' },
  { id: '2nd floor', name: '2nd Floor', dotColor: '#10B981' },
  { id: '6th floor', name: '6th Floor', dotColor: '#EAB308' },
  { id: 'call center', name: 'Call Center', dotColor: '#6B7280' },
  { id: '80 bloor', name: '80 Bloor', dotColor: '#8B5CF6' },
  { id: 'working from home', name: 'Working from Home', dotColor: '#EF4444' },
  { id: 'day off', name: 'Day Off', dotColor: '#000000' },
]

interface Shift {
  id: string
  employee_id: string
  day_of_week: string
  start_time: string
  end_time: string
  job_type: string
  floor?: string  // Legacy
  location?: string  // New human-readable location
  hours: number
  is_event?: boolean
  event_name?: string
  color?: string
  comment?: string  // Unmapped text/comment from cell
  requires_break?: boolean  // Whether shift requires 30-min break
  break_provided?: boolean  // Whether break was provided
}

export default function EmployeeScheduleView() {
  const [weekStart, setWeekStart] = useState<Date>(startOfWeek(new Date(), { weekStartsOn: 1 }))
  const [schedule, setSchedule] = useState<any>(null)
  const [employees, setEmployees] = useState<any[]>([])
  const [selectedLocation, setSelectedLocation] = useState<string>('all')
  const [showAvailabilityModal, setShowAvailabilityModal] = useState(false)
  const [selectedDay, setSelectedDay] = useState<string>('')
  const [selectedAvailability, setSelectedAvailability] = useState<string>('')
  const [availabilityDescription, setAvailabilityDescription] = useState<string>('')
  const [jobPreferences, setJobPreferences] = useState<Record<string, number>>({})
  const [myAvailabilityRequests, setMyAvailabilityRequests] = useState<any[]>([])

  const user = auth.getUser()

  useEffect(() => {
    loadEmployees()
    loadSchedule()
    loadMyAvailabilityRequests()
  }, [weekStart])

  const loadEmployees = async () => {
    const data = await getEmployees(true)
    // Filter out 'Availabilities' entry
    const filtered = data.filter((emp: any) => 
      emp.name.toLowerCase() !== 'availabilities' && 
      emp.name.toLowerCase() !== 'availability'
    )
    setEmployees(filtered)
  }

  const loadMyAvailabilityRequests = async () => {
    if (!user) return
    try {
      const allRequests = await getMyAvailabilityRequests()
      const formattedDate = format(weekStart, 'yyyy-MM-dd')
      const myRequests = allRequests.filter((r: any) => 
        r.week_start_date === formattedDate
      )
      setMyAvailabilityRequests(myRequests)
    } catch (err) {
      console.error('Failed to load availability requests:', err)
    }
  }

  const loadSchedule = async () => {
    if (!weekStart) return
    try {
      // Send the actual date for schedule lookup (backend will find matching sheet)
      const formattedDate = format(weekStart, 'yyyy-MM-dd')
      const data = await getSchedule(formattedDate)
      setSchedule(data)
    } catch (err) {
      setSchedule(null)
    }
  }

  const getWeekDates = () => {
    return days.map((_, index) => addDays(weekStart, index))
  }

  const getShiftsForCell = (employeeId: string, day: string) => {
    if (!schedule) return []
    return schedule.shifts.filter((s: Shift) => s.employee_id === employeeId && s.day_of_week === day)
  }

  const getEmployeeHours = (employeeId: string) => {
    if (!schedule) return 0
    return schedule.total_hours?.[employeeId] || 0
  }

  const getHoursColorClass = (emp: any, hours: number) => {
    const maxHours = emp.max_hours_per_week || 0
    const diff = hours - maxHours
    if (diff <= 0) return 'text-green-600'
    if (diff > 0 && diff < 2) return 'text-orange-600'
    if (diff >= 2) return 'text-red-600'
    return 'text-gray-900'
  }

  const getShiftColorClass = (shift: Shift) => {
    const loc = shift.location || shift.floor || 'ground'
    // For multi-location (e.g. "6th Floor, Call Center"), use the first one for color
    const firstLoc = loc.split(',')[0].toLowerCase().trim()
    return locationColors[firstLoc] || locationColors[loc.toLowerCase().trim()] || 'loc-ground'
  }

  const isShiftHighlighted = (shift: Shift) => {
    if (selectedLocation === 'all') return true
    if (!shift.location) return false
    // Match if ANY of the comma-separated locations matches the selected one
    const shiftLocs = shift.location.split(',').map(l => l.toLowerCase().trim())
    return shiftLocs.includes(selectedLocation.toLowerCase())
  }

  const handleCellClick = (day: string) => {
    if (!user) return
    setSelectedDay(day)
    setSelectedAvailability('blank')
    setShowAvailabilityModal(true)
  }

  const handleAvailabilitySubmit = async () => {
    if (!user || !selectedDay || !selectedAvailability) return
    
    try {
      const formattedDate = format(weekStart, 'yyyy-MM-dd')
      await createAvailabilityRequest({
        day_of_week: selectedDay,
        availability_type: selectedAvailability,
        week_start_date: formattedDate,
        description: availabilityDescription,
        preferences: jobPreferences
      })
      setShowAvailabilityModal(false)
      setAvailabilityDescription('')
      setJobPreferences({})
      loadMyAvailabilityRequests()
      alert('Availability request submitted for manager approval')
    } catch (err: any) {
      console.error('Failed to submit availability request:', err)
      alert(`Failed to submit availability request: ${err.response?.data?.detail || err.message}`)
    }
  }

  const weekDates = getWeekDates()

  return (
    <div className="flex flex-col lg:flex-row gap-6">
      {/* Location Sidebar - collapsible on mobile */}
      <div className="w-full lg:w-48 flex-shrink-0">
        <div className="bg-white rounded-lg shadow p-4 sticky top-4">
          <h2 className="font-bold mb-4 text-sm">Locations</h2>
          <div className="grid grid-cols-4 lg:grid-cols-1 gap-2">
            {locations.map(loc => (
              <button
                key={loc.id}
                onClick={() => setSelectedLocation(loc.id)}
                className={`text-left px-2 lg:px-3 py-2 rounded text-xs lg:text-sm transition-colors ${
                  selectedLocation === loc.id
                    ? 'bg-blue-100 border-2 border-blue-500 font-medium'
                    : 'hover:bg-gray-100 border-2 border-transparent'
                }`}
              >
                <div className="flex items-center gap-1 lg:gap-2">
                  {loc.dotColor && (
                    <div className="w-2 h-2 lg:w-3 lg:h-3 rounded-full flex-shrink-0" style={{ backgroundColor: loc.dotColor }}></div>
                  )}
                  <span className="truncate">{loc.name}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 min-w-0">
        <h1 className="text-2xl font-bold mb-6">Schedule</h1>
        
        {/* Week Navigation */}
        <div className="bg-white rounded-lg shadow p-4 lg:p-6 mb-6">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 mb-6">
          <button 
            onClick={() => setWeekStart(addDays(weekStart, -7))}
            className="p-2 border rounded hover:bg-gray-100"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4" />
            <DatePicker
              selected={weekStart}
              onChange={(date: Date | null) => date && setWeekStart(date)}
              filterDate={(date: Date) => date.getDay() === 1}
              className="border rounded px-2 py-1 lg:px-3 lg:py-1 text-sm"
              dateFormat="yyyy-MM-dd"
            />
          </div>
          
          <button 
            onClick={() => setWeekStart(addDays(weekStart, 7))}
            className="p-2 border rounded hover:bg-gray-100"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>

        <h3 className="font-medium mb-4">
          Week of {format(weekStart, 'MMMM d, yyyy')}
        </h3>

        {/* Schedule Status */}
        {schedule && (
          <div className="mb-4 p-3 bg-blue-50 rounded flex items-center gap-2">
            <span className="text-sm">
              Status: <strong className="capitalize">{schedule.status}</strong> | 
              Shifts: {schedule.shifts?.length || 0}
            </span>
          </div>
        )}

        {/* Focused Location Panel */}
        {schedule && selectedLocation !== 'all' && (() => {
          const locLabel = locations.find(l => l.id === selectedLocation)?.name || selectedLocation
          const filteredShifts = schedule.shifts.filter((s: Shift) => {
            if (!s.location) return false
            return s.location.split(',').map((l: string) => l.toLowerCase().trim()).includes(selectedLocation.toLowerCase())
          })
          // Group by day
          const byDay: Record<string, Shift[]> = {}
          days.forEach(d => { byDay[d] = [] })
          filteredShifts.forEach((s: Shift) => { byDay[s.day_of_week]?.push(s) })

          return (
            <div className="mb-6 rounded-lg border-2 p-4"
              style={{ borderColor: locations.find(l => l.id === selectedLocation)?.dotColor || '#E5E7EB' }}>
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-bold text-base flex items-center gap-2">
                  <MapPin className="w-4 h-4" />
                  {locLabel} — {filteredShifts.length} shift{filteredShifts.length !== 1 ? 's' : ''} this week
                </h3>
              </div>
              <div className="grid grid-cols-7 gap-2">
                {days.map((day, i) => (
                  <div key={day}>
                    <div className="text-xs font-semibold text-gray-500 capitalize mb-1">
                      {day.slice(0, 3)} <span className="text-gray-400">{format(weekDates[i], 'M/d')}</span>
                    </div>
                    {byDay[day].length === 0 ? (
                      <div className="text-xs text-gray-300 italic">—</div>
                    ) : (
                      byDay[day].map((shift: Shift) => {
                        const emp = employees.find((e: any) => e.id === shift.employee_id)
                        return (
                          <div key={shift.id} className="bg-white bg-opacity-70 rounded p-1 mb-1 text-xs border border-white shadow-sm">
                            <div className="font-semibold">{emp?.name || shift.employee_id}</div>
                            <div className="text-gray-600">{shift.start_time} – {shift.end_time}</div>
                            {shift.comment && <div className="text-gray-500 italic">{shift.comment}</div>}
                          </div>
                        )
                      })
                    )}
                  </div>
                ))}
              </div>
            </div>
          )
        })()}

        {/* Main Schedule Grid */}
        {schedule ? (
          <div className="bg-white rounded-lg shadow overflow-x-auto">
            <table className="w-full min-w-[1200px]">
              <thead>
                <tr className="bg-gray-100">
                  <th className="p-2 text-left font-medium text-sm sticky left-0 bg-gray-100 z-10 min-w-32">Employee</th>
                  <th className="p-2 text-center font-medium text-sm min-w-16">HRS</th>
                  {days.map((day, i) => (
                    <th key={day} className="p-2 text-center font-medium text-sm min-w-32">
                      <div className="capitalize">{day.slice(0, 3)}</div>
                      <div className="text-xs text-gray-500">{format(weekDates[i], 'M/d')}</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {employees.map(emp => {
                  const empHours = getEmployeeHours(emp.id)
                  
                  return (
                    <tr key={emp.id} className="border-t hover:bg-gray-50">
                      <td className="p-2 sticky left-0 bg-white z-10 font-medium text-sm">
                        {emp.name}
                        <div className="text-xs text-gray-500">{emp.employee_type}</div>
                      </td>
                      <td className={`p-2 text-center text-sm font-bold ${getHoursColorClass(emp, empHours)}`}>
                        {empHours.toFixed(1)}
                      </td>
                      {days.map(day => {
                        const shifts = getShiftsForCell(emp.id, day)
                        const isCurrentUser = user && emp.id === user.employee_id
                        // Get all requests for this day and sort by created_at descending (most recent first)
                        const dayRequests = isCurrentUser ? myAvailabilityRequests
                          .filter((r: any) => r.day_of_week.toLowerCase() === day)
                          .sort((a: any, b: any) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()) : []
                        
                        // Only show request history if no shifts are set
                        const showRequestHistory = dayRequests.length > 0 && shifts.length === 0
                        
                        // Dim other employees only if they have no shifts
                        const shouldDim = !isCurrentUser && shifts.length === 0
                        
                        return (
                          <td 
                            key={`${emp.id}-${day}`} 
                            className={`p-1 schedule-cell align-top ${isCurrentUser ? 'cursor-pointer hover:bg-gray-100' : 'cursor-default'} ${showRequestHistory ? 'bg-gray-50' : ''}`}
                            style={shouldDim ? { backgroundColor: '#E5E7EB' } : {}}
                            onClick={() => isCurrentUser && handleCellClick(day)}
                          >
                            {shifts.map((shift: Shift) => (
                              <div 
                                key={shift.id} 
                                className={`shift-card p-2 rounded mb-1 text-xs border relative ${getShiftColorClass(shift)} ${!isShiftHighlighted(shift) ? 'opacity-30' : ''}`}
                              >
                                <div className="font-medium">{shift.start_time} - {shift.end_time}</div>
                                <div className="text-gray-700 flex items-center gap-1">
                                  <Clock className="w-3 h-3" />
                                  {shift.hours}h
                                </div>
                                {shift.location && (
                                  <div className="text-gray-700 flex items-center gap-1">
                                    <MapPin className="w-3 h-3" />
                                    {shift.location}
                                  </div>
                                )}
                                {shift.comment && (
                                  <div className="text-gray-600 italic mt-1">{shift.comment}</div>
                                )}
                              </div>
                            ))}
                            {showRequestHistory && (
                              <div className="space-y-1">
                                {dayRequests.map((req: any, idx: number) => {
                                  const status = req.status || ''
                                  const statusLabel = status === 'AvailabilityRequestStatus.APPROVED' || status === 'approved' ? '✅ Approved' :
                                                   status === 'AvailabilityRequestStatus.REJECTED' || status === 'rejected' ? '❌ Rejected' :
                                                   status === 'AvailabilityRequestStatus.PENDING' || status === 'pending' ? '⏳ Pending' : ''
                                  const statusColor = status === 'AvailabilityRequestStatus.APPROVED' || status === 'approved' ? 'bg-green-100 text-green-700' :
                                                   status === 'AvailabilityRequestStatus.REJECTED' || status === 'rejected' ? 'bg-red-100 text-red-700' :
                                                   status === 'AvailabilityRequestStatus.PENDING' || status === 'pending' ? 'bg-yellow-100 text-yellow-700' : ''
                                  return (
                                    <div key={req.id || idx} className={`text-xs font-medium p-1 rounded ${statusColor}`}>
                                      {statusLabel}
                                    </div>
                                  )
                                })}
                              </div>
                            )}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-12 bg-white rounded-lg shadow">
            <p className="text-gray-500">No schedule for this week yet.</p>
          </div>
        )}
      </div>
      </div>

      {/* Availability Modal */}
      {showAvailabilityModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold">Set Availability for {selectedDay}</h3>
              <button 
                onClick={() => setShowAvailabilityModal(false)}
                className="p-1 hover:bg-gray-100 rounded"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            {/* Availability Type Selection */}
            <div className="mb-4">
              <label className="block text-sm font-medium mb-2">Availability Type</label>
              <div className="space-y-2">
                {availabilityTypes.map(type => (
                  <button
                    key={type.id}
                    onClick={() => setSelectedAvailability(type.id)}
                    className={`w-full p-3 rounded border-2 text-left flex items-center gap-3 ${
                      selectedAvailability === type.id ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <div 
                      className="w-6 h-6 rounded border border-gray-300"
                      style={{ backgroundColor: type.color }}
                    />
                    <span className="font-medium">{type.name}</span>
                  </button>
                ))}
              </div>
            </div>
            
            {/* Description Field */}
            <div className="mb-4">
              <label className="block text-sm font-medium mb-2">Reason (optional)</label>
              <textarea
                value={availabilityDescription}
                onChange={(e) => setAvailabilityDescription(e.target.value)}
                placeholder="Let the manager know why you need this availability..."
                className="w-full p-2 border rounded text-sm"
                rows={3}
              />
            </div>
            
            {/* Job Preferences */}
            <div className="mb-4">
              <label className="block text-sm font-medium mb-2">Job Preferences (1-10, higher = prefer)</label>
              <p className="text-xs text-gray-500 mb-2 italic">We value your input! Your preferences help us create a schedule that works for everyone. While business needs come first, we'll do our best to accommodate your preferences when possible.</p>
              <div className="space-y-2">
                {jobTypes.map(job => (
                  <div key={job.id} className="flex items-center gap-3">
                    <span className="flex-1 text-sm">{job.name}</span>
                    <div className="flex items-center gap-1">
                      {[1,2,3,4,5,6,7,8,9,10].map(num => (
                        <button
                          key={num}
                          onClick={() => setJobPreferences(prev => ({ ...prev, [job.id]: num }))}
                          className={`w-6 h-6 rounded text-xs font-medium ${
                            jobPreferences[job.id] === num ? 'bg-blue-600 text-white' : 'bg-gray-200 hover:bg-gray-300'
                          }`}
                        >
                          {num}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            
            <div className="mt-6 flex gap-3">
              <button
                onClick={handleAvailabilitySubmit}
                className="flex-1 bg-blue-600 text-white py-2 rounded hover:bg-blue-700"
              >
                Submit Request
              </button>
              <button
                onClick={() => setShowAvailabilityModal(false)}
                className="flex-1 border border-gray-300 py-2 rounded hover:bg-gray-100"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
