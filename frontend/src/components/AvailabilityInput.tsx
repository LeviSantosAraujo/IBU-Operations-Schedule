import { useState, useEffect } from 'react'
import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'
import { format, addDays, startOfWeek } from 'date-fns'
import { getEmployees, createAvailabilityRequest, getMyAvailabilityRequests } from '../api'
import { auth } from '../auth'
import { Save, Check, Calendar } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

const availabilityOptions = [
  { value: 'blank', label: 'Anytime / All day', color: '#FFFFFF' },
  { value: 'until_12pm', label: 'Until 12pm', color: '#90EE90' },
  { value: 'until_3pm', label: 'Until 3pm', color: '#87CEEB' },
  { value: 'after_330pm', label: 'After 3:30pm', color: '#FFB6C1' },
  { value: '12_3', label: '12pm - 3pm', color: '#ADD8E6' },
  { value: 'after_12_eod', label: 'After 12pm', color: '#FFDAB9' },
  { value: 'before_12_after_330', label: 'Before 12 & After 3:30', color: '#DDA0DD' },
  { value: 'off', label: 'OFF / Not available', color: '#333333' },
]

interface AvailabilityInputProps {
  initialDate?: Date | null
}

export default function AvailabilityInput({ initialDate }: AvailabilityInputProps) {
  const navigate = useNavigate()
  const [employees, setEmployees] = useState<any[]>([])
  const [selectedEmployee, setSelectedEmployee] = useState('')
  const [weekStart, setWeekStart] = useState<Date>(initialDate || startOfWeek(new Date(), { weekStartsOn: 1 }))
  const [availability, setAvailability] = useState<any>({})
  const [loading, setLoading] = useState(false)
  const [saved, setSaved] = useState(false)
  const [notes, setNotes] = useState('')
  const [isManager, setIsManager] = useState(false)
  const [error, setError] = useState('')
  const [currentUserId, setCurrentUserId] = useState('')

  useEffect(() => {
    const user = auth.getUser()
    if (user) {
      setIsManager(user.role?.toLowerCase() === 'manager')
      setCurrentUserId(user.employee_id)
      
      // Non-managers auto-select themselves
      if (user.role !== 'manager') {
        setSelectedEmployee(user.employee_id)
      } else {
        loadEmployees()
      }
    }
  }, [])

  useEffect(() => {
    if (selectedEmployee && weekStart) {
      loadAvailability()
    }
  }, [selectedEmployee, weekStart])

  const loadEmployees = async () => {
    const data = await getEmployees(true)
    setEmployees(data)
    if (data.length > 0 && !selectedEmployee) {
      setSelectedEmployee(data[0].id)
    }
  }

  const loadAvailability = async () => {
    if (!selectedEmployee || !weekStart) return
    const formattedDate = format(weekStart, 'yyyy-MM-dd')
    try {
      const data = await getMyAvailabilityRequests()
      const weekEnd = format(addDays(weekStart, 6), 'yyyy-MM-dd')
      const weekRequests = data.filter((r: any) => 
        r.start_date <= weekEnd && r.end_date >= formattedDate
      )
      
      const availMap: any = {}
      days.forEach(day => {
        availMap[day] = 'blank'
      })
      
      weekRequests.forEach((req: any) => {
        req.days_of_week.forEach((day: string) => {
          if (req.request_type === 'day_off') {
            availMap[day] = 'off'
          } else {
            availMap[day] = 'blank'
          }
        })
      })
      
      setAvailability(availMap)
      setNotes('')
    } catch (err) {
      // No existing availability, set defaults
      const defaultAvail: any = {}
      days.forEach(day => {
        defaultAvail[day] = day === 'saturday' || day === 'sunday' ? 'off' : 'blank'
      })
      setAvailability(defaultAvail)
      setNotes('')
    }
  }

  const handleCellClick = (day: string) => {
    const currentIndex = availabilityOptions.findIndex(opt => opt.value === availability[day])
    const nextIndex = (currentIndex + 1) % availabilityOptions.length
    const nextOption = availabilityOptions[nextIndex]
    
    setAvailability({ ...availability, [day]: nextOption.value })
    setSaved(false)
  }

  const handleSubmit = async () => {
    if (!selectedEmployee || !weekStart) return
    
    setLoading(true)
    setError('')
    try {
      const formattedDate = format(weekStart, 'yyyy-MM-dd')
      const weekEnd = format(addDays(weekStart, 6), 'yyyy-MM-dd')
      
      // Get enabled days (not blank or off)
      const enabledDays = days.filter(day => availability[day] !== 'blank' && availability[day] !== 'off')
      
      if (enabledDays.length === 0) {
        setError('Please select at least one day with availability')
        setLoading(false)
        return
      }
      
      // Submit availability request for each enabled day
      for (const day of enabledDays) {
        await createAvailabilityRequest({
          request_type: 'availability',
          start_date: formattedDate,
          end_date: weekEnd,
          days_of_week: [day],
          start_time: '09:00',
          end_time: '17:00',
          employee_comment: notes
        })
      }
      
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err: any) {
      setError('Error submitting availability request. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const getWeekDates = () => {
    return days.map((_, index) => addDays(weekStart, index))
  }

  const weekDates = getWeekDates()

  return (
    <div className="max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Submit Your Availability</h1>
      
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          {/* Only managers can select other employees */}
          {isManager && (
            <div>
              <label className="block text-sm font-medium mb-2">Select Employee</label>
              <select 
                value={selectedEmployee} 
                onChange={(e) => setSelectedEmployee(e.target.value)}
                className="w-full border rounded px-3 py-2"
              >
                {employees.map(emp => (
                  <option key={emp.id} value={emp.id}>{emp.name}</option>
                ))}
              </select>
            </div>
          )}
          
          {/* Non-managers see their name displayed */}
          {!isManager && (
            <div>
              <label className="block text-sm font-medium mb-2">Employee</label>
              <div className="px-3 py-2 bg-gray-100 border rounded text-gray-700">
                {employees.find(e => e.id === currentUserId)?.name || 'You'}
              </div>
            </div>
          )}
          
          <div>
            <label className="block text-sm font-medium mb-2">Week Starting (Monday)</label>
            <DatePicker
              selected={weekStart}
              onChange={(date: Date | null) => date && setWeekStart(date)}
              filterDate={(date: Date) => date.getDay() === 1}
              className="w-full border rounded px-3 py-2"
              dateFormat="yyyy-MM-dd"
            />
          </div>
        </div>

        {/* Week Preview */}
        <div className="mb-6">
          <h3 className="font-medium mb-2">
            Week of {format(weekStart, 'MMMM d, yyyy')}
          </h3>
          <div className="grid grid-cols-7 gap-2 text-sm text-gray-600">
            {days.map((day, i) => (
              <div key={day} className="text-center">
                <div className="font-medium capitalize">{day.slice(0, 3)}</div>
                <div>{format(weekDates[i], 'M/d')}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Availability Grid */}
        <div className="grid grid-cols-7 gap-2 mb-6">
          {days.map((day) => {
            const availValue = availability[day] || 'blank'
            const option = availabilityOptions.find(opt => opt.value === availValue)
            const isOff = availValue === 'off'
            
            return (
              <div
                key={day}
                onClick={() => handleCellClick(day)}
                className={`availability-cell rounded cursor-pointer transition-all ${isOff ? 'text-white' : 'text-black'}`}
                style={{ backgroundColor: option?.color }}
              >
                <div className="text-xs font-medium capitalize mb-1">{day.slice(0, 3)}</div>
                <div className="text-xs">{option?.label}</div>
              </div>
            )
          })}
        </div>

        {/* Notes */}
        <div className="mb-6">
          <label className="block text-sm font-medium mb-2">Notes (optional)</label>
          <textarea
            value={notes}
            onChange={(e) => { setNotes(e.target.value); setSaved(false); }}
            className="w-full border rounded px-3 py-2 h-20"
            placeholder="Any special requests or notes..."
          />
        </div>

        {/* Legend */}
        <div className="mb-6 p-4 bg-gray-50 rounded">
          <h4 className="font-medium mb-3">Click cells to cycle through options:</h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
            {availabilityOptions.map(opt => (
              <div key={opt.value} className="flex items-center gap-2">
                <div 
                  className="w-4 h-4 border rounded"
                  style={{ backgroundColor: opt.color, borderColor: opt.value === 'off' ? '#666' : '#ccc' }}
                />
                <span>{opt.label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Submit Button */}
        <div className="flex items-center gap-4">
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="flex items-center gap-2 bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? 'Saving...' : <><Save className="w-4 h-4" /> Save Availability</>}
          </button>
          
          {saved && (
            <button
              onClick={() => navigate('/my-schedule')}
              className="flex items-center gap-2 bg-green-600 text-white px-6 py-2 rounded hover:bg-green-700"
            >
              <Calendar className="w-4 h-4" />
              View Schedule
            </button>
          )}
          
          {saved && (
            <div className="flex items-center gap-2 text-green-600">
              <Check className="w-4 h-4" />
              Saved successfully!
            </div>
          )}
        </div>

        {/* Error Message */}
        {error && (
          <div className="mt-4 p-4 bg-orange-50 border border-orange-200 rounded-lg">
            <p className="text-orange-800 text-sm">{error}</p>
          </div>
        )}
      </div>
    </div>
  )
}
