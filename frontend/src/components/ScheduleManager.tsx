import { useState, useEffect } from 'react'
import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'
import { format, startOfWeek, addDays, parseISO } from 'date-fns'
import { 
  getSchedules, getSchedule, generateSchedule, saveSchedule, 
  getEmployees, getEmployeeAvailability, updateScheduleShifts, publishSchedule,
  deleteSchedule, getEmployeeHoursSummary
} from '../api'
import { 
  Plus, Trash2, Save, Play, Calendar, ChevronLeft, ChevronRight, 
  Check, AlertCircle, Clock, MapPin
} from 'lucide-react'

const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
const floors = ['ground', 'second', 'sixth']
const floorColors: any = {
  'ground': 'floor-ground',
  'second': 'floor-second',
  'sixth': 'floor-sixth'
}

interface Shift {
  id: string
  employee_id: string
  day_of_week: string
  start_time: string
  end_time: string
  job_type: string
  floor?: string
  hours: number
  is_event?: boolean
  event_name?: string
}

export default function ScheduleManager() {
  const [weekStart, setWeekStart] = useState<Date>(startOfWeek(addDays(new Date(), 7), { weekStartsOn: 1 }))
  const [schedule, setSchedule] = useState<any>(null)
  const [employees, setEmployees] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [selectedEmployee, setSelectedEmployee] = useState('')
  const [showAddShift, setShowAddShift] = useState(false)
  const [newShift, setNewShift] = useState<Partial<Shift>>({
    day_of_week: 'monday',
    start_time: '09:00',
    end_time: '17:00',
    floor: 'ground',
    job_type: 'ground_floor'
  })
  const [hoursSummary, setHoursSummary] = useState<any[]>([])
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    loadEmployees()
  }, [])

  useEffect(() => {
    loadSchedule()
  }, [weekStart])

  const loadEmployees = async () => {
    const data = await getEmployees(true)
    setEmployees(data)
  }

  const loadSchedule = async () => {
    if (!weekStart) return
    setLoading(true)
    try {
      const formattedDate = format(weekStart, 'yyyy-MM-dd')
      const data = await getSchedule(formattedDate)
      setSchedule(data)
      loadHoursSummary()
    } catch (err) {
      setSchedule(null)
    } finally {
      setLoading(false)
    }
  }

  const loadHoursSummary = async () => {
    if (!weekStart) return
    try {
      const formattedDate = format(weekStart, 'yyyy-MM-dd')
      const data = await getEmployeeHoursSummary(formattedDate)
      setHoursSummary(data)
    } catch (err) {
      setHoursSummary([])
    }
  }

  const handleGenerate = async () => {
    if (!weekStart) return
    setGenerating(true)
    try {
      const formattedDate = format(weekStart, 'yyyy-MM-dd')
      const data = await generateSchedule(formattedDate)
      setSchedule(data)
      loadHoursSummary()
    } catch (err) {
      alert('Error generating schedule')
    } finally {
      setGenerating(false)
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

  const handleDeleteShift = (shiftId: string) => {
    if (!schedule) return
    const updatedShifts = schedule.shifts.filter((s: Shift) => s.id !== shiftId)
    setSchedule({ ...schedule, shifts: updatedShifts })
    recalculateHours(updatedShifts)
  }

  const handleAddShift = () => {
    if (!schedule || !selectedEmployee) return
    
    const startH = parseInt(newShift.start_time?.split(':')[0] || '9')
    const startM = parseInt(newShift.start_time?.split(':')[1] || '0')
    const endH = parseInt(newShift.end_time?.split(':')[0] || '17')
    const endM = parseInt(newShift.end_time?.split(':')[1] || '0')
    const hours = (endH + endM / 60) - (startH + startM / 60)

    const shift: Shift = {
      id: `shift_${Date.now()}`,
      employee_id: selectedEmployee,
      day_of_week: newShift.day_of_week || 'monday',
      start_time: newShift.start_time || '09:00',
      end_time: newShift.end_time || '17:00',
      job_type: newShift.job_type || 'ground_floor',
      floor: newShift.floor as any,
      hours: Math.round(hours * 10) / 10
    }

    const updatedShifts = [...schedule.shifts, shift]
    setSchedule({ ...schedule, shifts: updatedShifts })
    recalculateHours(updatedShifts)
    setShowAddShift(false)
  }

  const recalculateHours = (shifts: Shift[]) => {
    const totals: any = {}
    shifts.forEach(shift => {
      totals[shift.employee_id] = (totals[shift.employee_id] || 0) + shift.hours
    })
    setSchedule((prev: any) => ({ ...prev, total_hours: totals }))
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
  const formattedWeekStart = format(weekStart, 'yyyy-MM-dd')

  return (
    <div>
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between mb-6 gap-4">
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
              onChange={(date) => date && setWeekStart(startOfWeek(date, { weekStartsOn: 1 }))}
              filterDate={(date) => date.getDay() === 1}
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
              onClick={handleSave}
              className="flex items-center gap-2 bg-gray-600 text-white px-4 py-2 rounded hover:bg-gray-700"
            >
              <Save className="w-4 h-4" />
              Save
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
      </div>

      {/* Schedule Status */}
      {schedule && (
        <div className="mb-4 p-3 bg-blue-50 rounded flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-blue-600" />
          <span className="text-sm">
            Status: <strong className="capitalize">{schedule.status}</strong> | 
            Shifts: {schedule.shifts?.length || 0} | 
            Updated: {format(parseISO(schedule.updated_at), 'MMM d, h:mm a')}
          </span>
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
                  value={selectedEmployee}
                  onChange={(e) => setSelectedEmployee(e.target.value)}
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
                <label className="block text-sm font-medium mb-1">Floor</label>
                <select
                  value={newShift.floor}
                  onChange={(e) => setNewShift({...newShift, floor: e.target.value})}
                  className="w-full border rounded px-3 py-2"
                >
                  <option value="ground">Ground Floor</option>
                  <option value="second">2nd Floor</option>
                  <option value="sixth">6th Floor</option>
                </select>
              </div>
            </div>
            
            <div className="flex gap-2 mt-6">
              <button
                onClick={handleAddShift}
                disabled={!selectedEmployee}
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
                const isOverLimit = empHours > emp.max_hours_per_week
                
                return (
                  <tr key={emp.id} className="border-t hover:bg-gray-50">
                    <td className="p-2 sticky left-0 bg-white z-10 font-medium text-sm">
                      {emp.name}
                      <div className="text-xs text-gray-500">{emp.employee_type}</div>
                    </td>
                    <td className={`p-2 text-center text-sm font-bold ${isOverLimit ? 'text-red-600' : ''}`}>
                      {empHours.toFixed(1)}
                    </td>
                    {days.map(day => {
                      const shifts = getShiftsForCell(emp.id, day)
                      return (
                        <td key={`${emp.id}-${day}`} className="p-1 schedule-cell align-top">
                          {shifts.map(shift => (
                            <div 
                              key={shift.id} 
                              className={`shift-card ${floorColors[shift.floor || 'ground']} relative group`}
                            >
                              <div className="flex justify-between items-start">
                                <div>
                                  <div className="font-medium">{shift.start_time}-{shift.end_time}</div>
                                  <div className="text-gray-600 flex items-center gap-1">
                                    <Clock className="w-3 h-3" />
                                    {shift.hours}h
                                  </div>
                                  {shift.floor && (
                                    <div className="text-gray-600 flex items-center gap-1">
                                      <MapPin className="w-3 h-3" />
                                      {shift.floor}
                                    </div>
                                  )}
                                </div>
                                <button
                                  onClick={() => handleDeleteShift(shift.id)}
                                  className="opacity-0 group-hover:opacity-100 text-red-500 hover:text-red-700"
                                >
                                  <Trash2 className="w-3 h-3" />
                                </button>
                              </div>
                            </div>
                          ))}
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
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700"
          >
            {generating ? 'Generating...' : 'Generate Schedule'}
          </button>
        </div>
      )}

      {/* Hours Summary */}
      {hoursSummary.length > 0 && (
        <div className="mt-6 bg-white rounded-lg shadow p-4">
          <h3 className="font-bold mb-4">Hours Summary</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
            {hoursSummary.map((emp: any) => (
              <div 
                key={emp.employee_id} 
                className={`p-3 rounded border ${emp.scheduled_hours > emp.max_hours ? 'border-red-500 bg-red-50' : 'border-gray-200'}`}
              >
                <div className="font-medium text-sm">{emp.name}</div>
                <div className="text-2xl font-bold">{emp.scheduled_hours}h</div>
                <div className="text-xs text-gray-500">
                  of {emp.max_hours}h max
                </div>
                <div className="text-xs">
                  Remaining: <span className={emp.remaining_hours < 0 ? 'text-red-600 font-bold' : ''}>
                    {emp.remaining_hours}h
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
