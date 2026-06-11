import { useState, useEffect } from 'react'
import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'
import { format, startOfWeek, addDays } from 'date-fns'
import {
  getSchedule, generateSchedule, saveSchedule,
  getEmployees, updateEmployee, publishSchedule, getAvailabilityRequests,
  approveAvailabilityRequest, rejectAvailabilityRequest,
  getEvents, createEvent, updateEvent, deleteEvent, clearSchedule,
  getStaffingTargets, updateStaffingTargets
} from '../api'
import { 
  Plus, Trash2, Save, Play, Calendar, ChevronLeft, ChevronRight, 
  Check, Clock, MapPin, Bell, X, Eraser
} from 'lucide-react'

const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
const baseLocationColors: any = {
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

const baseLocations = [
  { id: 'all', name: 'All Locations', dotColor: '' },
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
  floor?: string
  location?: string
  hours: number
  is_event?: boolean
  event_name?: string
  color?: string
  comment?: string
  description?: string
  locked?: boolean
  locked_availability_type?: string
}

export default function ScheduleManager() {
  const [weekStart, setWeekStart] = useState<Date>(startOfWeek(new Date(), { weekStartsOn: 1 }))
  const [schedule, setSchedule] = useState<any>(null)
  const [employees, setEmployees] = useState<any[]>([])
  const [_loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [selectedLocation, setSelectedLocation] = useState<string>('all')
  const [draggedShift, setDraggedShift] = useState<Shift | null>(null)
  const [history, setHistory] = useState<any[]>([])
  const [showEditModal, setShowEditModal] = useState(false)
  const [editingShift, setEditingShift] = useState<Shift | null>(null)
  const [editForm, setEditForm] = useState({
    start_time: '',
    end_time: '',
    location: '',
    description: ''
  })
  const [showAddShift, setShowAddShift] = useState(false)
  const [newShift, setNewShift] = useState<Partial<Shift>>({
    day_of_week: 'monday',
    start_time: '09:00',
    end_time: '17:00',
    floor: 'ground',
    job_type: 'ground_floor',
    location: '',
    description: ''
  })
  const [saved, setSaved] = useState(false)
  const [availabilityRequests, setAvailabilityRequests] = useState<any[]>([])
  const [showApprovalModal, setShowApprovalModal] = useState(false)
  const [selectedRequest, setSelectedRequest] = useState<any>(null)
  const [managerComment, setManagerComment] = useState('')
  const [events, setEvents] = useState<any[]>([])
  const [showEventModal, setShowEventModal] = useState(false)
  const [eventForm, setEventForm] = useState({
    name: '',
    date: new Date(),
    start_time: '18:00',
    end_time: '22:00',
    location: 'ground floor',
    description: ''
  })
  const [showEventAdvisory, setShowEventAdvisory] = useState(false)
  const [eventToast, setEventToast] = useState<{ message: string; events: any[] } | null>(null)
  const [editingEventId, setEditingEventId] = useState<string | null>(null)
  const [editingEventName, setEditingEventName] = useState('')
  const [generationStatus, setGenerationStatus] = useState<string>('')
  const [progressPercent, setProgressPercent] = useState<number>(0)
  const [generationTime, setGenerationTime] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState<'schedule' | 'preferences'>('schedule')
  const [employeePreferences, setEmployeePreferences] = useState<Record<string, Record<string, number>>>({})
  const [approvedRequests, setApprovedRequests] = useState<any[]>([])
  const [allRequests, setAllRequests] = useState<any[]>([])
  const [showAutoGenerateModal, setShowAutoGenerateModal] = useState(false)
  const [staffingTargets, setStaffingTargets] = useState<Record<string, number>>({
    'ground_floor': 2,
    'second_floor': 3,
    'sixth_floor': 1,
    'call_center': 4,
    '80_bloor': 1,
    'working_from_home': 1
  })

  // Dynamic locations - base locations + event locations
  const locations = [
    ...baseLocations,
    ...events.map((e: any) => ({
      id: e.name.toLowerCase().replace(/\s+/g, '_'),
      name: e.name,
      dotColor: '#F97316',
      isEvent: true
    }))
  ]

  // Dynamic location colors - base colors + event colors
  const locationColors: any = {
    ...baseLocationColors,
    ...events.reduce((acc: any, e: any) => {
      acc[e.name.toLowerCase().replace(/\s+/g, '_')] = 'loc-event'
      acc[e.name] = 'loc-event'
      return acc
    }, {})
  }

  useEffect(() => {
    loadEmployees()
    loadAvailabilityRequests()
    loadEvents()
    loadEmployeePreferences()
    loadApprovedRequests()
    loadStaffingTargets()
  }, [weekStart])

  useEffect(() => {
    loadSchedule()
  }, [weekStart])

  const loadEmployees = async () => {
    const data = await getEmployees(true)
    const employeeList = Array.isArray(data) ? data : Array.isArray(data?.employees) ? data.employees : []
    setEmployees(employeeList)
  }

  const loadEmployeePreferences = async () => {
    try {
      const data = await getEmployees(true)
      const employeeList = Array.isArray(data) ? data : Array.isArray(data?.employees) ? data.employees : []
      const prefs: Record<string, Record<string, number>> = {}
      employeeList.forEach((emp: any) => {
        if (emp.employee_type !== 'manager' && emp.preferences) {
          prefs[emp.id] = emp.preferences
        }
      })
      setEmployeePreferences(prefs)
    } catch (err) {
      console.error('Error loading employee preferences:', err)
    }
  }

  const handleSaveEmployeePreferences = async (employeeId: string, preferences: Record<string, number>) => {
    try {
      await updateEmployee(employeeId, { preferences })
      setEmployeePreferences(prev => ({ ...prev, [employeeId]: preferences }))
    } catch (err) {
      alert('Error saving preferences. Please try again.')
    }
  }

  const loadApprovedRequests = async () => {
    try {
      const data = await getAvailabilityRequests()
      const approved = data.filter((r: any) =>
        r.status === 'approved' || r.status === 'AvailabilityRequestStatus.APPROVED'
      )
      setApprovedRequests(approved)
      setAllRequests(data)
    } catch (err) {
      console.error('Error loading approved requests:', err)
    }
  }

  const loadStaffingTargets = async () => {
    try {
      const data = await getStaffingTargets()
      if (data && Object.keys(data).length > 0) {
        setStaffingTargets(data)
      }
    } catch (err) {
      console.error('Error loading staffing targets:', err)
    }
  }

  const loadAvailabilityRequests = async () => {
    try {
      const data = await getAvailabilityRequests()
      // Only load pending requests - approved requests already have locked shifts
      const formattedDate = format(weekStart, 'yyyy-MM-dd')
      const weekEnd = format(addDays(weekStart, 6), 'yyyy-MM-dd')

      const weekRequests = data.filter((r: any) => {
        // Only include pending requests
        const status = r.status?.toLowerCase() || ''
        if (status !== 'pending' && status !== 'availabilityrequeststatus.pending') {
          return false
        }

        // Handle new schema with start_date/end_date
        if (r.start_date && r.end_date) {
          return r.start_date <= weekEnd && r.end_date >= formattedDate
        }
        // Handle old schema with week_start_date
        if (r.week_start_date) {
          return r.week_start_date === formattedDate
        }
        // If no date info, include it (for backward compatibility)
        return true
      })
      setAvailabilityRequests(weekRequests)
    } catch (err) {
      console.error('Failed to load availability requests:', err)
    }
  }

  const loadEvents = async () => {
    try {
      const data = await getEvents()
      // Filter events for current week on frontend
      const formattedDate = format(weekStart, 'yyyy-MM-dd')
      const weekEvents = data.filter((e: any) => e.week_start_date === formattedDate)
      setEvents(weekEvents)
    } catch (err) {
      console.error('Failed to load events:', err)
    }
  }

  const handleApproveRequest = async (requestId: string, comment?: string) => {
    try {
      await approveAvailabilityRequest(requestId, comment)
      loadAvailabilityRequests()
      setShowApprovalModal(false)
      setManagerComment('')
      setSelectedRequest(null)
    } catch (err) {
      alert('Failed to approve request')
    }
  }

  const handleRejectRequest = async (requestId: string, comment: string) => {
    try {
      await rejectAvailabilityRequest(requestId, comment)
      loadAvailabilityRequests()
      setShowApprovalModal(false)
      setManagerComment('')
      setSelectedRequest(null)
    } catch (err) {
      alert('Failed to reject request')
    }
  }

  const openApprovalModal = (request: any) => {
    setSelectedRequest(request)
    setManagerComment('')
    setShowApprovalModal(true)
  }

  const handleCreateEvent = async () => {
    try {
      const formattedDate = format(weekStart, 'yyyy-MM-dd')
      const eventData = {
        ...eventForm,
        date: format(eventForm.date, 'yyyy-MM-dd'),
        week_start_date: formattedDate,
        people_needed: staffingTargets[eventForm.location.replace(' ', '_')] || 3
      }
      await createEvent(eventData)
      await loadEvents()
      setShowEventModal(false)
      setEventForm({
        name: '',
        date: new Date(),
        start_time: '18:00',
        end_time: '22:00',
        location: 'ground floor',
        description: ''
      })
      // Show toast with refreshed events
      const allData = await getEvents()
      const updatedEvents = allData.filter((e: any) => e.week_start_date === formattedDate)
      setEventToast({ message: 'Event created', events: updatedEvents })
      setTimeout(() => setEventToast(null), 5000)
    } catch (err) {
      alert('Failed to create event')
    }
  }

  const handleDeleteEvent = async (eventId: string) => {
    if (!confirm('Are you sure you want to delete this event?')) return
    try {
      await deleteEvent(eventId)
      await loadEvents()
      setEventToast({ message: 'Event deleted', events: events.filter((e: any) => e.id !== eventId) })
      setTimeout(() => setEventToast(null), 5000)
    } catch (err) {
      alert('Failed to delete event')
    }
  }

  const handleGenerateWithoutEvents = async () => {
    setShowEventAdvisory(false)
    setGenerating(true)
    try {
      const formattedDate = format(weekStart, 'yyyy-MM-dd')
      const data = await generateSchedule(formattedDate)
      setSchedule(data)
    } catch (err) {
      alert('Error generating schedule')
    } finally {
      setGenerating(false)
    }
  }

  const loadSchedule = async () => {
    if (!weekStart) return
    setLoading(true)
    try {
      const formattedDate = format(weekStart, 'yyyy-MM-dd')
      const data = await getSchedule(formattedDate)
      setSchedule(data)
    } catch (err) {
      console.error('Error loading schedule:', err)
      setSchedule(null)
    } finally {
      setLoading(false)
    }
  }

  const handleGenerate = async () => {
    if (!weekStart) return

    // Show auto-generate modal with staffing targets and event creation
    setShowAutoGenerateModal(true)
  }

  const handleAutoGenerate = async () => {
    // Save staffing targets
    await updateStaffingTargets(staffingTargets)
    setShowAutoGenerateModal(false)

    setGenerating(true)
    setGenerationStatus('Initializing scheduler...')
    setProgressPercent(0)

    // Estimated time: ~52 seconds total for generation
    // Distribute progress updates across estimated duration
    const statuses = [
      { message: 'Loading employee data...', delay: 2000 },
      { message: 'Analyzing last 4 weeks of schedules...', delay: 6000 },
      { message: 'Calculating historical job preferences...', delay: 10000 },
      { message: 'Checking availability submissions...', delay: 14000 },
      { message: 'Processing approved requests...', delay: 18000 },
      { message: 'Staffing events...', delay: 22000 },
      { message: 'Assigning call center shifts...', delay: 26000 },
      { message: 'Assigning 2nd floor shifts...', delay: 30000 },
      { message: 'Assigning ground floor shifts...', delay: 34000 },
      { message: 'Assigning 6th floor shifts...', delay: 38000 },
      { message: 'Applying fairness algorithm...', delay: 42000 },
      { message: 'Distributing manager hours...', delay: 46000 },
      { message: 'Validating shift assignments...', delay: 49000 },
      { message: 'Finalizing schedule...', delay: 52000 }
    ]
    
    const startTime = Date.now()
    
    const updateProgress = () => {
      const elapsed = Date.now() - startTime
      const currentStatus = statuses.find(s => elapsed < s.delay)
      if (currentStatus) {
        setGenerationStatus(currentStatus.message)
        // Calculate progress percentage
        const progress = Math.min((elapsed / 52000) * 100, 95)
        setProgressPercent(progress)
      } else {
        setProgressPercent(100)
      }
    }
    
    const progressInterval = setInterval(updateProgress, 100)
    
    try {
      const formattedDate = format(weekStart, 'yyyy-MM-dd')
      const data = await generateSchedule(formattedDate)
      setSchedule(data)
      setGenerationStatus('Schedule generated successfully!')
      if (data.metadata?.generation_time_seconds) {
        setGenerationTime(data.metadata.generation_time_seconds)
      }
    } catch (err) {
      alert('Error generating schedule')
      setGenerationStatus('Error during generation')
    } finally {
      clearInterval(progressInterval)
      setTimeout(() => {
        setGenerating(false)
        setGenerationStatus('')
      }, 500)
    }
  }

  const handleSave = async () => {
    if (!schedule) return
    try {
      await saveSchedule(schedule)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err) {
      alert('Error saving schedule')
    }
  }

  const handleUndo = () => {
    if (history.length === 0) return
    const previousState = history[history.length - 1]
    setSchedule(previousState)
    setHistory(history.slice(0, -1))
  }

  const saveToHistory = () => {
    if (schedule) {
      setHistory([...history, { ...schedule }])
    }
  }

  const handlePublish = async () => {
    if (!weekStart || !schedule) return
    try {
      const formattedDate = format(weekStart, 'yyyy-MM-dd')
      await publishSchedule(formattedDate)
      alert('Schedule published!')
      loadSchedule()
    } catch (err) {
      alert('Error publishing schedule')
    }
  }

  const handleClearSchedule = async () => {
    if (!weekStart || !schedule) return
    if (!confirm('Are you sure you want to clear all shifts for this week? Events and locations will be preserved.')) return
    try {
      const formattedDate = format(weekStart, 'yyyy-MM-dd')
      await clearSchedule(formattedDate)
      alert('Schedule cleared! Events and locations have been preserved.')
      loadSchedule()
    } catch (err) {
      alert('Error clearing schedule')
    }
  }

  const handleDeleteShift = (shiftId: string) => {
    if (!schedule) return
    const updatedShifts = schedule.shifts.filter((s: Shift) => s.id !== shiftId)
    setSchedule({ ...schedule, shifts: updatedShifts, total_hours: recalculateHours(updatedShifts) })
  }

  const handleAddShift = () => {
    if (!schedule) return
    
    const startH = parseInt(newShift.start_time?.split(':')[0] || '9')
    const startM = parseInt(newShift.start_time?.split(':')[1] || '0')
    const endH = parseInt(newShift.end_time?.split(':')[0] || '17')
    const endM = parseInt(newShift.end_time?.split(':')[1] || '0')
    const hours = (endH + endM / 60) - (startH + startM / 60)

    const shift: Shift = {
      id: `shift_${Date.now()}`,
      employee_id: newShift.employee_id || '',
      day_of_week: newShift.day_of_week || 'monday',
      start_time: newShift.start_time || '09:00',
      end_time: newShift.end_time || '17:00',
      job_type: newShift.job_type || 'ground_floor',
      floor: newShift.floor as any,
      location: newShift.location,
      comment: newShift.description,
      hours: Math.round(hours * 10) / 10
    }

    saveToHistory()
    const updatedShifts = [...schedule.shifts, shift]
    setSchedule({ ...schedule, shifts: updatedShifts, total_hours: recalculateHours(updatedShifts) })
    setShowAddShift(false)
  }

  const recalculateHours = (shifts: Shift[]) => {
    const totals: any = {}
    shifts.forEach(shift => {
      // Skip day off shifts - they should not count toward hours
      if (shift.location === 'day off' || shift.locked_availability_type === 'Day Off') {
        return
      }
      totals[shift.employee_id] = (totals[shift.employee_id] || 0) + shift.hours
    })
    return totals
  }

  const getShiftColorClass = (shift: Shift) => {
    if (shift.locked) return ''
    // For event shifts, use event name for color
    if (shift.is_event && shift.event_name) {
      const eventKey = shift.event_name.toLowerCase().replace(/\s+/g, '_')
      return locationColors[eventKey] || locationColors[shift.event_name.toLowerCase()] || 'loc-event'
    }
    const loc = shift.location || shift.floor || 'ground'
    const firstLoc = loc.split(',')[0].toLowerCase().trim()
    return locationColors[firstLoc] || locationColors[loc.toLowerCase().trim()] || 'loc-ground'
  }

  const isShiftHighlighted = (shift: Shift) => {
    if (selectedLocation === 'all') return true
    // Check by location
    if (shift.location) {
      const shiftLocs = shift.location.split(',').map((l: string) => l.toLowerCase().trim())
      if (shiftLocs.includes(selectedLocation.toLowerCase())) return true
    }
    // Check by event name for event shifts
    if (shift.is_event && shift.event_name && shift.event_name.toLowerCase().replace(/\s+/g, '_') === selectedLocation.toLowerCase()) {
      return true
    }
    return false
  }

  const getHoursColorClass = (emp: any, hours: number) => {
    const maxHours = emp.max_hours_per_week || 0
    const diff = hours - maxHours
    if (diff <= 0) return 'text-green-600'
    if (diff > 0 && diff < 2) return 'text-orange-600'
    if (diff >= 2) return 'text-red-600'
    return 'text-gray-900'
  }

  const handleDragStart = (shift: Shift) => {
    setDraggedShift(shift)
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
  }

  const isLockedCell = (employeeId: string, day: string) => {
    if (!schedule) return false
    return schedule.shifts.some((s: Shift) => s.locked && s.employee_id === employeeId && s.day_of_week === day)
  }

  const handleDrop = (targetEmployeeId: string, targetDay: string) => {
    if (!draggedShift || !schedule) return
    if (draggedShift.locked) return

    // Allow managers to override locked shifts by removing them first
    const lockedShiftsToRemove = schedule.shifts.filter((s: Shift) =>
      s.locked && s.employee_id === targetEmployeeId && s.day_of_week === targetDay
    )

    // Save current state to history before making changes
    saveToHistory()

    // Remove locked shifts for this cell (manager override)
    let shiftsWithoutLocked = schedule.shifts
    if (lockedShiftsToRemove.length > 0) {
      shiftsWithoutLocked = schedule.shifts.filter((s: Shift) =>
        !(s.locked && s.employee_id === targetEmployeeId && s.day_of_week === targetDay)
      )
    }

    // Remove the original shift from the schedule (this is a move operation)
    const shiftsWithoutOriginal = shiftsWithoutLocked.filter((s: Shift) => s.id !== draggedShift.id)

    // Create a new shift with the target employee and day, preserving all other data
    const updatedShift = {
      ...draggedShift,
      employee_id: targetEmployeeId,
      day_of_week: targetDay,
      id: `${targetEmployeeId}-${targetDay}-${Date.now()}` // Generate new ID for the moved shift
    }

    // Update the schedule with the shift moved to new location
    const updatedShifts = [...shiftsWithoutOriginal, updatedShift]

    setSchedule({ ...schedule, shifts: updatedShifts, total_hours: recalculateHours(updatedShifts) })
    setDraggedShift(null)
  }

  const normalizeTimeForInput = (timeStr: string): string => {
    if (!timeStr) return '09:00'
    
    // If already in HH:MM format, return as-is
    if (/^\d{2}:\d{2}$/.test(timeStr)) {
      return timeStr
    }
    
    // Try to parse 12-hour format with AM/PM (e.g., "9:00 AM", "5:00 PM")
    const match12Hour = timeStr.match(/(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)/i)
    if (match12Hour) {
      let hour = parseInt(match12Hour[1])
      const minute = match12Hour[2]
      const meridiem = match12Hour[3].toUpperCase()
      
      if (meridiem === 'PM' && hour !== 12) {
        hour += 12
      } else if (meridiem === 'AM' && hour === 12) {
        hour = 0
      }
      
      return `${hour.toString().padStart(2, '0')}:${minute}`
    }
    
    // Try to parse H:MM or HH:MM without AM/PM (assume 24-hour)
    const match24Hour = timeStr.match(/(\d{1,2}):(\d{2})/)
    if (match24Hour) {
      const hour = parseInt(match24Hour[1])
      const minute = match24Hour[2]
      return `${hour.toString().padStart(2, '0')}:${minute}`
    }
    
    return '09:00' // Default fallback
  }

  const handleCellDoubleClick = (shiftId: string) => {
    if (!schedule) return
    
    // Find the specific shift by ID
    const existingShift = schedule.shifts.find((s: Shift) => s.id === shiftId)
    
    if (existingShift) {
      // Edit existing shift - normalize times for HTML input
      setEditingShift(existingShift)
      setEditForm({
        start_time: normalizeTimeForInput(existingShift.start_time),
        end_time: normalizeTimeForInput(existingShift.end_time),
        location: existingShift.location || '',
        description: existingShift.comment || ''
      })
      setShowEditModal(true)
    }
  }

  const handleCellClick = (employeeId: string, day: string) => {
    if (!schedule) return
    
    // Always create a new shift when clicking on a cell
    // This allows adding multiple shifts to the same cell
    const newShift: Shift = {
      id: `${employeeId}-${day}-${Date.now()}`,
      employee_id: employeeId,
      day_of_week: day,
      start_time: '09:00',
      end_time: '17:00',
      job_type: 'cashier',
      hours: 8,
      is_event: false
    }
    setEditingShift(newShift)
    setEditForm({
      start_time: '09:00',
      end_time: '17:00',
      location: '',
      description: ''
    })
    setShowEditModal(true)
  }

  const handleEditShift = () => {
    if (!editingShift || !schedule) return
    
    saveToHistory()
    
    // Calculate hours from start and end time
    const hours = calculateHours(editForm.start_time, editForm.end_time)
    
    // Update or add the shift
    const updatedShift = {
      ...editingShift,
      start_time: editForm.start_time,
      end_time: editForm.end_time,
      hours: hours,
      location: editForm.location,
      comment: editForm.description
    }
    
    // Check if this is an edit or add
    const existingIndex = schedule.shifts.findIndex((s: Shift) => s.id === editingShift.id)
    
    let updatedShifts
    if (existingIndex >= 0) {
      // Edit existing shift
      updatedShifts = schedule.shifts.map((s: Shift) => 
        s.id === editingShift.id ? updatedShift : s
      )
    } else {
      // Add new shift
      updatedShifts = [...schedule.shifts, updatedShift]
    }
    
    setSchedule({ ...schedule, shifts: updatedShifts, total_hours: recalculateHours(updatedShifts) })
    setShowEditModal(false)
    setEditingShift(null)
    setDraggedShift(null)
  }

  const formatTime12Hour = (timeStr: string): string => {
    if (!timeStr) return ''
    
    // Check if time already has AM/PM (e.g., "9:00 AM", "5:00 PM")
    const match12Hour = timeStr.match(/(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)/i)
    if (match12Hour) {
      const hour = match12Hour[1]
      const minute = match12Hour[2]
      const meridiem = match12Hour[3].toUpperCase()
      return `${hour}:${minute} ${meridiem}`
    }
    
    // Parse 24-hour HH:MM format
    const [hourStr, minute] = timeStr.split(':')
    const hour = parseInt(hourStr)
    
    if (isNaN(hour)) return timeStr
    
    const meridiem = hour >= 12 ? 'PM' : 'AM'
    const hour12 = hour > 12 ? hour - 12 : (hour === 0 ? 12 : hour)
    
    return `${hour12}:${minute} ${meridiem}`
  }

  const calculateHours = (startTime: string, endTime: string): number => {
    try {
      const [startHour, startMin] = startTime.split(':').map(Number)
      const [endHour, endMin] = endTime.split(':').map(Number)
      
      const startMinutes = startHour * 60 + startMin
      const endMinutes = endHour * 60 + endMin
      
      let diff = endMinutes - startMinutes
      if (diff < 0) {
        // Handle overnight shifts (end time is next day)
        diff += 24 * 60
      }
      
      return Math.round((diff / 60) * 100) / 100 // Round to 2 decimal places
    } catch {
      return 8 // Default fallback
    }
  }

  const handleEditShiftCancel = () => {
    setShowEditModal(false)
    setEditingShift(null)
    setDraggedShift(null)
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

  const weekDates = getWeekDates()

  return (
    <div className="flex flex-col lg:flex-row gap-6">
      {/* Location Sidebar - collapsible on mobile */}
      <div className="w-full lg:w-48 flex-shrink-0">
        <div className="bg-white rounded-lg shadow p-4 sticky top-4">
          <h2 className="font-bold mb-4 text-sm">Locations</h2>
          <div className="grid grid-cols-4 lg:grid-cols-1 gap-2">
            {locations.map((loc: any) => {
              const matchedEvent = loc.isEvent ? events.find((e: any) =>
                e.name.toLowerCase().replace(/\s+/g, '_') === loc.id
              ) : null
              const isEditing = matchedEvent && editingEventId === matchedEvent.id

              return (
                <div
                  key={loc.id}
                  className={`rounded text-xs lg:text-sm transition-colors border-2 ${
                    selectedLocation === loc.id
                      ? 'bg-blue-100 border-blue-500'
                      : 'hover:bg-gray-100 border-transparent'
                  }`}
                >
                  {/* Location row */}
                  <button
                    onClick={() => setSelectedLocation(loc.id)}
                    className="w-full text-left px-2 lg:px-3 py-2"
                  >
                    <div className="flex items-center gap-1 lg:gap-2">
                      {loc.dotColor && (
                        <div className="w-2 h-2 lg:w-3 lg:h-3 rounded-full flex-shrink-0" style={{ backgroundColor: loc.dotColor }}></div>
                      )}
                      <span className="truncate font-medium">{loc.name}</span>
                    </div>
                  </button>

                  {/* Edit/Delete controls – only for event locations */}
                  {matchedEvent && (
                    <div className="px-2 pb-2">
                      {isEditing ? (
                        <div className="flex flex-col gap-1">
                          <input
                            type="text"
                            value={editingEventName}
                            onChange={e => setEditingEventName(e.target.value)}
                            className="w-full border rounded px-2 py-1 text-xs"
                            autoFocus
                          />
                          <div className="flex gap-1">
                            <button
                              onClick={async () => {
                                if (!editingEventName.trim()) return
                                try {
                                  await updateEvent(matchedEvent.id, { ...matchedEvent, name: editingEventName.trim() })
                                  await loadEvents()
                                  setEditingEventId(null)
                                } catch { alert('Failed to update event') }
                              }}
                              className="flex-1 text-xs bg-blue-600 text-white py-1 rounded hover:bg-blue-700"
                            >
                              Save
                            </button>
                            <button
                              onClick={() => setEditingEventId(null)}
                              className="flex-1 text-xs border border-gray-300 py-1 rounded hover:bg-gray-100"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex gap-1">
                          <button
                            onClick={() => {
                              setEditingEventId(matchedEvent.id)
                              setEditingEventName(matchedEvent.name)
                            }}
                            className="flex-1 text-xs text-blue-600 hover:text-blue-800 py-0.5"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleDeleteEvent(matchedEvent.id)}
                            className="flex-1 text-xs text-red-500 hover:text-red-700 py-0.5"
                          >
                            Delete
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Availability Requests Panel - Only show pending */}
      {availabilityRequests.filter((r: any) => r.status === 'pending' || r.status === 'AvailabilityRequestStatus.PENDING').length > 0 && (
        <div className="w-full lg:w-64 flex-shrink-0">
          <div className="bg-white rounded-lg shadow p-4 sticky top-4">
            <div className="flex items-center gap-2 mb-4">
              <Bell className="w-4 h-4 text-orange-500" />
              <h2 className="font-bold text-sm">Pending Requests</h2>
              <span className="bg-orange-500 text-white text-xs px-2 py-1 rounded-full">
                {availabilityRequests.filter((r: any) => r.status === 'pending' || r.status === 'AvailabilityRequestStatus.PENDING').length}
              </span>
            </div>
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {availabilityRequests.filter((r: any) => r.status === 'pending' || r.status === 'AvailabilityRequestStatus.PENDING').map((request: any) => {
                const emp = employees.find((e: any) => e.id === request.employee_id)

                // Handle both new and old schema
                const requestType = request.request_type || 'availability'
                const daysDisplay = Array.isArray(request.days_of_week) && request.days_of_week.length > 0
                  ? request.days_of_week.map((d: string) => d.charAt(0).toUpperCase() + d.slice(1)).join(', ')
                  : request.day_of_week || 'N/A'

                let description = ''
                if (requestType === 'day_off') {
                  description = `Day Off for ${daysDisplay}`
                } else {
                  const timeRange = request.start_time && request.end_time
                    ? ` (${request.start_time} - ${request.end_time})`
                    : ''
                  description = `Available on ${daysDisplay}${timeRange}`
                }

                const dateRange = request.start_date && request.end_date
                  ? `${request.start_date} to ${request.end_date}`
                  : ''

                return (
                  <div key={request.id} className="p-3 bg-gray-50 rounded border">
                    <div className="font-medium text-sm">{emp?.name || request.employee_id}</div>
                    <div className="text-xs text-gray-600 capitalize">{description}</div>
                    {dateRange && <div className="text-xs text-gray-500">{dateRange}</div>}
                    <div className="mt-2 flex gap-2">
                      <button
                        onClick={() => openApprovalModal(request)}
                        className="flex-1 text-xs bg-blue-600 text-white py-1 rounded hover:bg-blue-700"
                      >
                        Review
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* Events Toast Notification */}
      {eventToast && (
        <div className="fixed top-6 right-6 z-50 w-80 bg-white rounded-lg shadow-xl border border-purple-200 overflow-hidden animate-in">
          <div className="flex items-center justify-between px-4 py-3 bg-purple-600">
            <div className="flex items-center gap-2 text-white">
              <Calendar className="w-4 h-4" />
              <span className="font-semibold text-sm">Events This Week</span>
              <span className="bg-white text-purple-600 text-xs font-bold px-2 py-0.5 rounded-full">
                {eventToast.events.length}
              </span>
            </div>
            <button onClick={() => setEventToast(null)} className="text-white hover:text-purple-200">
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="px-4 py-3 space-y-2 max-h-64 overflow-y-auto">
            {eventToast.events.length === 0 ? (
              <p className="text-xs text-gray-500">No events for this week.</p>
            ) : (
              eventToast.events.map((event: any) => (
                <div key={event.id} className="p-2 bg-purple-50 rounded border border-purple-100">
                  <div className="font-medium text-sm">{event.name}</div>
                  <div className="text-xs text-gray-600">
                    {format(new Date(event.date), 'MMM dd')} • {event.start_time}–{event.end_time}
                  </div>
                  <div className="text-xs text-gray-500 capitalize">{event.location}</div>
                  <button
                    onClick={() => handleDeleteEvent(event.id)}
                    className="mt-1 text-xs text-red-500 hover:text-red-700"
                  >
                    Delete
                  </button>
                </div>
              ))
            )}
          </div>
          <div className="h-1 bg-purple-100">
            <div className="h-1 bg-purple-500" style={{ animation: 'shrink 5s linear forwards' }} />
          </div>
        </div>
      )}

      {/* Main Content */}
      <div className="flex-1 min-w-0">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-center justify-between mb-6 gap-4">
          <h1 className="text-2xl font-bold">Schedule Manager</h1>
          
          <div className="flex items-center gap-4">
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
                onChange={(date: Date | null) => date && setWeekStart(startOfWeek(date, { weekStartsOn: 1 }))}
                filterDate={(date: Date) => date.getDay() === 1}
                className="border rounded px-3 py-1"
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
        </div>

        {/* Actions */}
        <div className="flex flex-wrap gap-2 mb-6">
          <button
            onClick={() => setShowEventModal(true)}
            className="flex items-center gap-2 bg-purple-600 text-white px-4 py-2 rounded hover:bg-purple-700"
          >
            <Plus className="w-4 h-4" />
            Create Event
          </button>
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="flex items-center gap-2 bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 disabled:opacity-50"
          >
            <Play className="w-4 h-4" />
            {generating ? 'Generating...' : 'Auto-Generate'}
          </button>
          
          {schedule && (
            <>
              <button
                onClick={() => setShowAddShift(true)}
                className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
              >
                <Plus className="w-4 h-4" />
                Add Shift
              </button>
              
              <button
                onClick={handleUndo}
                disabled={history.length === 0}
                className="flex items-center gap-2 bg-gray-500 text-white px-4 py-2 rounded hover:bg-gray-600 disabled:opacity-50"
              >
                <ChevronLeft className="w-4 h-4" />
                Undo
              </button>
              
              <button
                onClick={handleSave}
                className="flex items-center gap-2 bg-gray-600 text-white px-4 py-2 rounded hover:bg-gray-700"
              >
                <Save className="w-4 h-4" />
                Save
              </button>
              
              <button
                onClick={handleClearSchedule}
                className="flex items-center gap-2 bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700"
              >
                <Eraser className="w-4 h-4" />
                Clear Schedule
              </button>
              
              <button
                onClick={handlePublish}
                className="flex items-center gap-2 bg-purple-600 text-white px-4 py-2 rounded hover:bg-purple-700"
              >
                <Check className="w-4 h-4" />
                Publish
              </button>
            </>
          )}
          
          {saved && (
            <span className="flex items-center gap-1 text-green-600">
              <Check className="w-4 h-4" /> Saved!
            </span>
          )}
          
          {generating && (
            <div className="w-full mt-4">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
                <span className="text-sm text-blue-600">{generationStatus}</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div className="bg-blue-600 h-2 rounded-full transition-all duration-300" style={{ width: `${progressPercent}%` }}></div>
              </div>
            </div>
          )}
          
          {generationTime && !generating && (
            <div className="text-xs text-gray-500 mt-2">
              Generated in {generationTime.toFixed(2)}s
            </div>
          )}
        </div>

        <div className="bg-white rounded-lg shadow p-4 lg:p-6 mb-6">
          {/* Tabs */}
          <div className="flex gap-4 mb-4 border-b">
            <button
              onClick={() => setActiveTab('schedule')}
              className={`pb-2 px-4 font-medium ${activeTab === 'schedule' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-500'}`}
            >
              Schedule
            </button>
            <button
              onClick={() => setActiveTab('preferences')}
              className={`pb-2 px-4 font-medium ${activeTab === 'preferences' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-500'}`}
            >
              Employee Preferences
            </button>
          </div>

          {activeTab === 'schedule' && (
            <>
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
              // Check by location
              if (s.location && s.location.split(',').map((l: string) => l.toLowerCase().trim()).includes(selectedLocation.toLowerCase())) {
                return true
              }
              // Check by event name for event shifts
              if (s.is_event && s.event_name && s.event_name.toLowerCase().replace(/\s+/g, '_') === selectedLocation.toLowerCase()) {
                return true
              }
              return false
            })
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
                              <div className="text-gray-600">{formatTime12Hour(shift.start_time)} – {formatTime12Hour(shift.end_time)}</div>
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
                          // Get all availability requests for this employee and day
                          const empDayRequests = availabilityRequests
                            .filter((r: any) => {
                              if (r.employee_id !== emp.id) return false
                              // Handle new schema (days_of_week array)
                              if (Array.isArray(r.days_of_week) && r.days_of_week.length > 0) {
                                return r.days_of_week.some((d: string) => d.toLowerCase() === day)
                              }
                              // Handle old schema (day_of_week string)
                              if (r.day_of_week) {
                                return r.day_of_week.toLowerCase() === day
                              }
                              return false
                            })
                            .sort((a: any, b: any) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime())

                          const hasShifts = shifts.length > 0
                          const showRequests = empDayRequests.length > 0 && !hasShifts
                          
                          return (
                            <td
                              key={`${emp.id}-${day}`}
                              className="p-1 schedule-cell align-top cursor-pointer"
                              style={isLockedCell(emp.id, day) ? { background: 'repeating-linear-gradient(45deg, #f3f4f6, #f3f4f6 4px, #e5e7eb 4px, #e5e7eb 8px)' } : {}}
                              onDragOver={handleDragOver}
                              onDrop={() => handleDrop(emp.id, day)}
                              onDoubleClick={() => {
                                setNewShift({
                                  employee_id: emp.id,
                                  day_of_week: day,
                                  start_time: '09:00',
                                  end_time: '17:00',
                                  job_type: 'ground_floor',
                                  location: 'Ground Floor',
                                  description: ''
                                })
                                setShowAddShift(true)
                              }}
                            >
                              {shifts.map((shift: Shift) => (
                                shift.locked ? (
                                  <div
                                    key={shift.id}
                                    className={`p-2 rounded mb-1 text-xs border relative group ${
                                      shift.location === 'day off' ? 'border-black bg-black text-white' : 'border-gray-400 bg-gray-200 text-gray-600'
                                    }`}
                                    title={`Approved availability: ${shift.locked_availability_type} (click trash to override)`}
                                  >
                                    <div className="font-semibold">🔒 {shift.locked_availability_type}</div>
                                    {shift.comment && <div className="italic text-xs mt-1">{shift.comment}</div>}
                                    <button
                                      onClick={(e) => { e.stopPropagation(); handleDeleteShift(shift.id) }}
                                      className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 text-red-500 hover:text-red-700 bg-white rounded-full p-1"
                                      title="Remove locked shift (manager override)"
                                    >
                                      <Trash2 className="w-3 h-3" />
                                    </button>
                                  </div>
                                ) : (
                                <div 
                                  key={shift.id} 
                                  draggable
                                  onDragStart={() => handleDragStart(shift)}
                                  onClick={(e) => e.stopPropagation()}
                                  onDoubleClick={(e) => { e.stopPropagation(); handleCellDoubleClick(shift.id) }}
                                  className={`shift-card p-2 rounded mb-1 text-xs border relative group cursor-move ${getShiftColorClass(shift)} ${!isShiftHighlighted(shift) ? 'opacity-30' : ''}`}
                                >
                                  <div className="flex justify-between items-start">
                                    <div>
                                      <div className="font-medium">{formatTime12Hour(shift.start_time)} - {formatTime12Hour(shift.end_time)}</div>
                                      <div className="text-gray-600 flex items-center gap-1">
                                        <Clock className="w-3 h-3" />
                                        {shift.hours}h
                                      </div>
                                      {shift.location && (
                                        <div className="text-gray-600 flex items-center gap-1">
                                          <MapPin className="w-3 h-3" />
                                          {shift.location}
                                        </div>
                                      )}
                                      {shift.comment && (
                                        <div className="text-gray-500 italic mt-1">{shift.comment}</div>
                                      )}
                                    </div>
                                    <button
                                      onClick={(e) => { e.stopPropagation(); handleDeleteShift(shift.id) }}
                                      className="opacity-0 group-hover:opacity-100 text-red-500 hover:text-red-700"
                                    >
                                      <Trash2 className="w-3 h-3" />
                                    </button>
                                  </div>
                                </div>
                                )
                              ))}
                              {showRequests && (() => {
                                const latest = empDayRequests[0]
                                const latestStatus = latest?.status || ''
                                const isApproved = latestStatus === 'AvailabilityRequestStatus.APPROVED' || latestStatus === 'approved'
                                const isRejected = latestStatus === 'AvailabilityRequestStatus.REJECTED' || latestStatus === 'rejected'
                                const isPending = latestStatus === 'AvailabilityRequestStatus.PENDING' || latestStatus === 'pending'
                                const statusLabel = isApproved ? '✅ Approved' : isRejected ? '❌ Rejected' : isPending ? '⏳ Pending' : ''
                                const statusColor = isApproved ? 'bg-green-100 text-green-700' :
                                                   isRejected ? 'bg-red-100 text-red-700' :
                                                   isPending ? 'bg-yellow-100 text-yellow-700' : ''
                                const count = empDayRequests.length
                                return (
                                  <div className={`text-xs font-medium p-1 rounded ${statusColor}`}>
                                    <div>{statusLabel}</div>
                                    {count > 1 && <div className="text-[10px] opacity-70">{count}x submitted</div>}
                                  </div>
                                )
                              })()}
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
              <p className="text-gray-500 mb-4">No schedule for this week yet.</p>
              <div className="flex gap-3 justify-center">
                <button
                  onClick={() => setShowEventModal(true)}
                  className="bg-green-600 text-white px-6 py-2 rounded hover:bg-green-700"
                >
                  Create Event
                </button>
                <button
                  onClick={handleGenerate}
                  disabled={generating}
                  className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700"
                >
                  {generating ? 'Generating...' : 'Generate Schedule'}
                </button>
              </div>
            </div>
          )}
          </>
          )}

          {activeTab === 'preferences' && (
            <>
              <h3 className="font-medium mb-4">
                Employee Preferences (Manager Set)
              </h3>
              <div className="space-y-4">
                {employees.filter((e: any) => e.employee_type !== 'manager').map((emp: any) => (
                  <div key={emp.id} className="border rounded-lg p-4">
                    <h4 className="font-semibold mb-3">{emp.name}</h4>

                    {/* Job Preferences */}
                    <div>
                      <h5 className="text-sm font-medium mb-2 text-gray-600">Job Preferences (Manager Set)</h5>
                      <div className="space-y-2">
                        {['ground_floor', 'second_floor', 'sixth_floor', 'call_center', '80_bloor', 'working_from_home', 'event'].map(jobType => (
                          <div key={jobType} className="flex items-center gap-3">
                            <span className="flex-1 text-sm capitalize">{jobType.replace('_', ' ')}</span>
                            <div className="flex items-center gap-1">
                              {[1,2,3,4,5,6,7,8,9,10].map(num => (
                                <button
                                  key={num}
                                  onClick={() => {
                                    const newPrefs = { ...(employeePreferences[emp.id] || {}), [jobType]: num }
                                    handleSaveEmployeePreferences(emp.id, newPrefs)
                                  }}
                                  className={`w-6 h-6 rounded text-xs font-medium ${
                                    (employeePreferences[emp.id] || {})[jobType] === num ? 'bg-blue-600 text-white' : 'bg-gray-200 hover:bg-gray-300'
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
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Edit Shift Modal */}
        {showEditModal && editingShift && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg p-6 w-96">
              <h3 className="text-lg font-bold mb-4">Edit Shift</h3>
              
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="block text-sm font-medium mb-1">Start</label>
                    <input
                      type="time"
                      value={editForm.start_time}
                      onChange={(e) => setEditForm({...editForm, start_time: e.target.value})}
                      className="w-full border rounded px-3 py-2"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">End</label>
                    <input
                      type="time"
                      value={editForm.end_time}
                      onChange={(e) => setEditForm({...editForm, end_time: e.target.value})}
                      className="w-full border rounded px-3 py-2"
                    />
                  </div>
                </div>
                
                <div>
                  <label className="block text-sm font-medium mb-1">Location</label>
                  <select
                    value={editForm.location}
                    onChange={(e) => setEditForm({...editForm, location: e.target.value})}
                    className="w-full border rounded px-3 py-2"
                  >
                    <option value="">Select...</option>
                    <option value="Event">Event</option>
                    <option value="Ground Floor">Ground Floor</option>
                    <option value="2nd Floor">2nd Floor</option>
                    <option value="6th Floor">6th Floor</option>
                    <option value="Call Center">Call Center</option>
                    <option value="80 Bloor">80 Bloor</option>
                    <option value="Working from Home">Working from Home</option>
                  </select>
                </div>
                
                <div>
                  <label className="block text-sm font-medium mb-1">Description</label>
                  <textarea
                    value={editForm.description}
                    onChange={(e) => setEditForm({...editForm, description: e.target.value})}
                    className="w-full border rounded px-3 py-2"
                    rows={2}
                    placeholder="Additional notes..."
                  />
                </div>
              </div>
              
              <div className="flex gap-2 mt-6">
                <button
                  onClick={handleEditShift}
                  className="flex-1 bg-blue-600 text-white py-2 rounded hover:bg-blue-700"
                >
                  Save
                </button>
                <button
                  onClick={handleEditShiftCancel}
                  className="flex-1 bg-gray-300 py-2 rounded hover:bg-gray-400"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Add Shift Modal */}
        {showAddShift && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg p-6 w-96">
              <h3 className="text-lg font-bold mb-4">Add Shift</h3>
              
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium mb-1">Employee</label>
                  <select
                    value={newShift.employee_id}
                    onChange={(e) => setNewShift({...newShift, employee_id: e.target.value})}
                    className="w-full border rounded px-3 py-2"
                  >
                    <option value="">Select...</option>
                    {employees.map(emp => (
                      <option key={emp.id} value={emp.id}>{emp.name}</option>
                    ))}
                  </select>
                </div>
                
                <div>
                  <label className="block text-sm font-medium mb-1">Day</label>
                  <select
                    value={newShift.day_of_week}
                    onChange={(e) => setNewShift({...newShift, day_of_week: e.target.value})}
                    className="w-full border rounded px-3 py-2"
                  >
                    {days.map(day => (
                      <option key={day} value={day}>{day.charAt(0).toUpperCase() + day.slice(1)}</option>
                    ))}
                  </select>
                </div>
                
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="block text-sm font-medium mb-1">Start</label>
                    <input
                      type="time"
                      value={newShift.start_time}
                      onChange={(e) => setNewShift({...newShift, start_time: e.target.value})}
                      className="w-full border rounded px-3 py-2"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">End</label>
                    <input
                      type="time"
                      value={newShift.end_time}
                      onChange={(e) => setNewShift({...newShift, end_time: e.target.value})}
                      className="w-full border rounded px-3 py-2"
                    />
                  </div>
                </div>
                
                <div>
                  <label className="block text-sm font-medium mb-1">Location</label>
                  <select
                    value={newShift.location}
                    onChange={(e) => setNewShift({...newShift, location: e.target.value})}
                    className="w-full border rounded px-3 py-2"
                  >
                    <option value="">Select...</option>
                    <option value="Event">Event</option>
                    <option value="Ground Floor">Ground Floor</option>
                    <option value="2nd Floor">2nd Floor</option>
                    <option value="6th Floor">6th Floor</option>
                    <option value="Call Center">Call Center</option>
                    <option value="80 Bloor">80 Bloor</option>
                    <option value="Working from Home">Working from Home</option>
                  </select>
                </div>
                
                <div>
                  <label className="block text-sm font-medium mb-1">Description</label>
                  <textarea
                    value={newShift.description}
                    onChange={(e) => setNewShift({...newShift, description: e.target.value})}
                    className="w-full border rounded px-3 py-2"
                    rows={2}
                    placeholder="Additional notes..."
                  />
                </div>
              </div>
              
              <div className="flex gap-2 mt-6">
                <button
                  onClick={handleAddShift}
                  disabled={!newShift.employee_id}
                  className="flex-1 bg-blue-600 text-white py-2 rounded hover:bg-blue-700 disabled:opacity-50"
                >
                  Add
                </button>
                <button
                  onClick={() => setShowAddShift(false)}
                  className="flex-1 bg-gray-300 py-2 rounded hover:bg-gray-400"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Approval Modal */}
      {showApprovalModal && selectedRequest && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold">Review Availability Request</h3>
              <button 
                onClick={() => setShowApprovalModal(false)}
                className="p-1 hover:bg-gray-100 rounded"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-3 mb-4">
              <div>
                <span className="text-sm text-gray-600">Employee:</span>
                <span className="ml-2 font-medium">
                  {employees.find((e: any) => e.id === selectedRequest.employee_id)?.name || selectedRequest.employee_id}
                </span>
              </div>
              {/* Handle both new and old schema */}
              {(() => {
                const requestType = selectedRequest.request_type || 'availability'
                const daysDisplay = Array.isArray(selectedRequest.days_of_week) && selectedRequest.days_of_week.length > 0
                  ? selectedRequest.days_of_week.map((d: string) => d.charAt(0).toUpperCase() + d.slice(1)).join(', ')
                  : selectedRequest.day_of_week || 'N/A'

                let description = ''
                if (requestType === 'day_off') {
                  description = `Day Off for ${daysDisplay}`
                } else {
                  const timeRange = selectedRequest.start_time && selectedRequest.end_time
                    ? ` (${selectedRequest.start_time} - ${selectedRequest.end_time})`
                    : ''
                  description = `Available on ${daysDisplay}${timeRange}`
                }

                const dateRange = selectedRequest.start_date && selectedRequest.end_date
                  ? `${selectedRequest.start_date} to ${selectedRequest.end_date}`
                  : ''

                return (
                  <>
                    <div>
                      <span className="text-sm text-gray-600">Request:</span>
                      <span className="ml-2 font-medium">{description}</span>
                    </div>
                    {dateRange && (
                      <div>
                        <span className="text-sm text-gray-600">Date Range:</span>
                        <span className="ml-2 font-medium">{dateRange}</span>
                      </div>
                    )}
                    {selectedRequest.employee_comment && (
                      <div>
                        <span className="text-sm text-gray-600">Employee Comment:</span>
                        <span className="ml-2 font-medium italic">"{selectedRequest.employee_comment}"</span>
                      </div>
                    )}
                  </>
                )
              })()}
              <div>
                <label className="block text-sm font-medium mb-1">Manager Comment (optional for approval, required for rejection)</label>
                <textarea
                  value={managerComment}
                  onChange={(e) => setManagerComment(e.target.value)}
                  className="w-full border rounded px-3 py-2"
                  rows={3}
                  placeholder="Add a comment..."
                />
              </div>
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => handleApproveRequest(selectedRequest.id, managerComment || undefined)}
                className="flex-1 bg-green-600 text-white py-2 rounded hover:bg-green-700"
              >
                Approve
              </button>
              <button
                onClick={() => {
                  if (managerComment.trim()) {
                    handleRejectRequest(selectedRequest.id, managerComment)
                  } else {
                    alert('Please provide a comment for rejection')
                  }
                }}
                className="flex-1 bg-red-600 text-white py-2 rounded hover:bg-red-700"
              >
                Reject
              </button>
              <button
                onClick={() => setShowApprovalModal(false)}
                className="flex-1 border border-gray-300 py-2 rounded hover:bg-gray-100"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Auto-Generate Modal */}
      {showAutoGenerateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold">Auto-Generate Schedule</h3>
              <button
                onClick={() => setShowAutoGenerateModal(false)}
                className="p-1 hover:bg-gray-100 rounded"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Staffing Targets */}
            <div className="mb-6">
              <h4 className="font-semibold mb-3">Staffing Targets (people per day)</h4>
              <div className="grid grid-cols-2 gap-3">
                {Object.entries(staffingTargets).map(([location, target]) => (
                  <div key={location} className="flex items-center gap-2">
                    <label className="flex-1 text-sm capitalize">{location.replace('_', ' ')}</label>
                    <input
                      type="number"
                      min="0"
                      max="10"
                      value={target}
                      onChange={(e) => setStaffingTargets({
                        ...staffingTargets,
                        [location]: parseInt(e.target.value) || 0
                      })}
                      className="w-20 px-2 py-1 border rounded text-center"
                    />
                  </div>
                ))}
              </div>
            </div>

            {/* Events Section */}
            <div className="mb-6">
              <div className="flex items-center justify-between mb-3">
                <h4 className="font-semibold">Events for {format(weekStart, 'MMM d, yyyy')}</h4>
                <button
                  onClick={() => setShowEventModal(true)}
                  className="text-sm bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700"
                >
                  + Add Event
                </button>
              </div>
              {events.length === 0 ? (
                <p className="text-sm text-gray-500 italic">No events created yet</p>
              ) : (
                <div className="space-y-2">
                  {events.map((event: any) => (
                    <div key={event.id} className="flex items-center justify-between bg-gray-50 p-2 rounded">
                      <div>
                        <div className="font-medium">{event.name}</div>
                        <div className="text-xs text-gray-600">
                          {format(new Date(event.date), 'MMM d')} • {event.start_time}-{event.end_time} • {event.location}
                        </div>
                      </div>
                      <button
                        onClick={() => handleDeleteEvent(event.id)}
                        className="text-red-600 hover:text-red-700"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="flex gap-3">
              <button
                onClick={handleAutoGenerate}
                className="flex-1 bg-green-600 text-white py-2 rounded hover:bg-green-700"
              >
                Generate Schedule
              </button>
              <button
                onClick={() => setShowAutoGenerateModal(false)}
                className="flex-1 bg-gray-600 text-white py-2 rounded hover:bg-gray-700"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Event Creation Modal */}
      {showEventModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold">Create Event</h3>
              <button 
                onClick={() => setShowEventModal(false)}
                className="p-1 hover:bg-gray-100 rounded"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">Event Name</label>
                <input
                  type="text"
                  value={eventForm.name}
                  onChange={(e) => setEventForm({...eventForm, name: e.target.value})}
                  className="w-full border rounded px-3 py-2"
                  placeholder="e.g., Summer Party"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Date</label>
                <DatePicker
                  selected={eventForm.date}
                  onChange={(date: Date | null) => setEventForm({...eventForm, date: date || new Date()})}
                  className="w-full border rounded px-3 py-2"
                  minDate={weekStart}
                  maxDate={addDays(weekStart, 6)}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1">Start Time</label>
                  <input
                    type="time"
                    value={eventForm.start_time}
                    onChange={(e) => setEventForm({...eventForm, start_time: e.target.value})}
                    className="w-full border rounded px-3 py-2"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">End Time</label>
                  <input
                    type="time"
                    value={eventForm.end_time}
                    onChange={(e) => setEventForm({...eventForm, end_time: e.target.value})}
                    className="w-full border rounded px-3 py-2"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Location</label>
                <select
                  value={eventForm.location}
                  onChange={(e) => setEventForm({...eventForm, location: e.target.value})}
                  className="w-full border rounded px-3 py-2"
                >
                  <option value="ground floor">Ground Floor</option>
                  <option value="2nd floor">2nd Floor</option>
                  <option value="6th floor">6th Floor</option>
                  <option value="call center">Call Center</option>
                  <option value="80 bloor">80 Bloor</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Description (optional)</label>
                <textarea
                  value={eventForm.description}
                  onChange={(e) => setEventForm({...eventForm, description: e.target.value})}
                  className="w-full border rounded px-3 py-2"
                  rows={2}
                  placeholder="Event details..."
                />
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={handleCreateEvent}
                disabled={!eventForm.name}
                className="flex-1 bg-blue-600 text-white py-2 rounded hover:bg-blue-700 disabled:opacity-50"
              >
                Create Event
              </button>
              <button
                onClick={() => setShowEventModal(false)}
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
