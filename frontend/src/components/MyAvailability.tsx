import { useState, useEffect } from 'react'
import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'
import { format, addDays, startOfWeek } from 'date-fns'
import { createAvailabilityRequest, getMyAvailabilityRequests } from '../api'
import { auth } from '../auth'
import { Plus, Calendar, Clock, X } from 'lucide-react'

const daysOfWeek = [
  { value: 'monday', label: 'Monday' },
  { value: 'tuesday', label: 'Tuesday' },
  { value: 'wednesday', label: 'Wednesday' },
  { value: 'thursday', label: 'Thursday' },
  { value: 'friday', label: 'Friday' },
  { value: 'saturday', label: 'Saturday' },
  { value: 'sunday', label: 'Sunday' },
]

const jobTypes = [
  { id: 'ground_floor', name: 'Ground Floor' },
  { id: 'second_floor', name: '2nd Floor' },
  { id: 'sixth_floor', name: '6th Floor' },
  { id: 'call_center', name: 'Call Center' },
  { id: 'event', name: 'Event' },
]

interface DayAvailability {
  enabled: boolean
  startTime: string
  endTime: string
}

export default function MyAvailability() {
  const [startDate, setStartDate] = useState<Date | null>(null)
  const [endDate, setEndDate] = useState<Date | null>(null)
  const [dayAvailabilities, setDayAvailabilities] = useState<Record<string, DayAvailability>>(() => {
    const initial: Record<string, DayAvailability> = {}
    daysOfWeek.forEach(day => {
      initial[day.value] = { enabled: false, startTime: '09:00', endTime: '17:00' }
    })
    return initial
  })
  const [comment, setComment] = useState('')
  const [jobPreferences, setJobPreferences] = useState<Record<string, number>>({})
  const [myRequests, setMyRequests] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [saved, setSaved] = useState(false)
  const [showDayOffModal, setShowDayOffModal] = useState(false)
  const [dayOffDate, setDayOffDate] = useState<Date | null>(null)
  const [dayOffComment, setDayOffComment] = useState('')

  useEffect(() => {
    loadMyRequests()
  }, [])

  const loadMyRequests = async () => {
    try {
      const data = await getMyAvailabilityRequests()
      setMyRequests(data || [])
    } catch (err) {
      console.error('Error loading requests:', err)
    }
  }

  const toggleDay = (day: string) => {
    setDayAvailabilities(prev => ({
      ...prev,
      [day]: { ...prev[day], enabled: !prev[day].enabled }
    }))
  }

  const updateTime = (day: string, field: 'startTime' | 'endTime', value: string) => {
    setDayAvailabilities(prev => ({
      ...prev,
      [day]: { ...prev[day], [field]: value }
    }))
  }

  const handleSubmitAvailability = async () => {
    const enabledDays = Object.entries(dayAvailabilities).filter(([_, avail]) => avail.enabled)
    if (enabledDays.length === 0) {
      alert('Please select at least one day')
      return
    }
    if (!startDate || !endDate) {
      alert('Please select start and end dates')
      return
    }

    setLoading(true)
    try {
      // Submit one request per enabled day
      for (const [day, avail] of enabledDays) {
        await createAvailabilityRequest({
          request_type: 'availability',
          start_date: format(startDate, 'yyyy-MM-dd'),
          end_date: format(endDate, 'yyyy-MM-dd'),
          days_of_week: [day],
          start_time: avail.startTime,
          end_time: avail.endTime,
          employee_comment: comment,
          preferences: jobPreferences,
        })
      }
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
      // Reset form
      const resetAvail: Record<string, DayAvailability> = {}
      daysOfWeek.forEach(day => {
        resetAvail[day.value] = { enabled: false, startTime: '09:00', endTime: '17:00' }
      })
      setDayAvailabilities(resetAvail)
      setComment('')
      setJobPreferences({})
      setStartDate(null)
      setEndDate(null)
      loadMyRequests()
    } catch (err) {
      alert('Error submitting request. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleSubmitDayOff = async () => {
    if (!dayOffDate) {
      alert('Please select a date for your day off')
      return
    }

    setLoading(true)
    try {
      const dayName = daysOfWeek[dayOffDate.getDay()].value
      await createAvailabilityRequest({
        request_type: 'day_off',
        start_date: format(dayOffDate, 'yyyy-MM-dd'),
        end_date: format(dayOffDate, 'yyyy-MM-dd'),
        days_of_week: [dayName],
        employee_comment: dayOffComment,
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
      setShowDayOffModal(false)
      setDayOffDate(null)
      setDayOffComment('')
      loadMyRequests()
    } catch (err) {
      alert('Error submitting day off request. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'approved': return 'bg-green-100 text-green-800'
      case 'rejected': return 'bg-red-100 text-red-800'
      default: return 'bg-yellow-100 text-yellow-800'
    }
  }

  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">My Availability</h1>

      {/* Availability Form */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4">Set Availability</h2>

        {/* Date Range */}
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium mb-2">Start Date</label>
            <DatePicker
              selected={startDate}
              onChange={setStartDate}
              className="w-full border rounded px-3 py-2"
              dateFormat="yyyy-MM-dd"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">End Date</label>
            <DatePicker
              selected={endDate}
              onChange={setEndDate}
              minDate={startDate || undefined}
              className="w-full border rounded px-3 py-2"
              dateFormat="yyyy-MM-dd"
            />
          </div>
        </div>

        {/* Day Availability Grid */}
        <div className="space-y-3 mb-6">
          {daysOfWeek.map((day) => (
            <div key={day.value} className="flex items-center gap-4 p-3 border rounded">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <input
                    type="checkbox"
                    checked={dayAvailabilities[day.value].enabled}
                    onChange={() => toggleDay(day.value)}
                    className="w-4 h-4"
                  />
                  <span className="font-medium">{day.label}</span>
                </div>
                {dayAvailabilities[day.value].enabled && (
                  <div className="flex items-center gap-2 ml-6">
                    <Clock className="w-4 h-4 text-gray-400" />
                    <input
                      type="time"
                      value={dayAvailabilities[day.value].startTime}
                      onChange={(e) => updateTime(day.value, 'startTime', e.target.value)}
                      className="border rounded px-2 py-1 text-sm"
                    />
                    <span>to</span>
                    <input
                      type="time"
                      value={dayAvailabilities[day.value].endTime}
                      onChange={(e) => updateTime(day.value, 'endTime', e.target.value)}
                      className="border rounded px-2 py-1 text-sm"
                    />
                  </div>
                )}
              </div>
            </div>
          ))}
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

        {/* Comment */}
        <div className="mb-4">
          <label className="block text-sm font-medium mb-2">Comment (optional)</label>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            className="w-full border rounded px-3 py-2 h-20"
            placeholder="Any special requests or notes..."
          />
        </div>

        {/* Submit Button */}
        <button
          onClick={handleSubmitAvailability}
          disabled={loading}
          className="flex items-center gap-2 bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Submitting...' : <><Plus className="w-4 h-4" /> Submit Availability</>}
        </button>

        {saved && (
          <div className="mt-2 text-green-600 text-sm">
            Request submitted successfully!
          </div>
        )}
      </div>

      {/* Request Day Off Button */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <button
          onClick={() => setShowDayOffModal(true)}
          className="flex items-center gap-2 bg-purple-600 text-white px-6 py-2 rounded hover:bg-purple-700"
        >
          <Calendar className="w-4 h-4" />
          Request a Day Off
        </button>
      </div>

      {/* Day Off Modal */}
      {showDayOffModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-96">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-bold">Request Day Off</h3>
              <button onClick={() => setShowDayOffModal(false)} className="text-gray-500 hover:text-gray-700">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Date</label>
                <DatePicker
                  selected={dayOffDate}
                  onChange={setDayOffDate}
                  className="w-full border rounded px-3 py-2"
                  dateFormat="yyyy-MM-dd"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">Reason (optional)</label>
                <textarea
                  value={dayOffComment}
                  onChange={(e) => setDayOffComment(e.target.value)}
                  className="w-full border rounded px-3 py-2 h-20"
                  placeholder="Reason for day off..."
                />
              </div>
              <button
                onClick={handleSubmitDayOff}
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 bg-purple-600 text-white px-6 py-2 rounded hover:bg-purple-700 disabled:opacity-50"
              >
                {loading ? 'Submitting...' : 'Submit Day Off Request'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* My Requests */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4">My Requests</h2>
        {myRequests.length === 0 ? (
          <p className="text-gray-500">No requests submitted yet.</p>
        ) : (
          <div className="space-y-3">
            {myRequests.map((request) => (
              <div key={request.id} className="p-4 border rounded">
                <div className="flex justify-between items-start mb-2">
                  <div>
                    <span className={`px-2 py-1 rounded text-xs font-medium capitalize ${getStatusColor(request.status)}`}>
                      {request.status}
                    </span>
                    <span className="ml-2 text-sm font-medium capitalize">
                      {request.request_type || 'availability'}
                    </span>
                  </div>
                  <div className="text-xs text-gray-500">
                    {new Date(request.created_at).toLocaleDateString()}
                  </div>
                </div>
                <div className="text-sm text-gray-700">
                  <div className="flex items-center gap-2 mb-1">
                    <Calendar className="w-4 h-4" />
                    <span>
                      {request.start_date} to {request.end_date}
                    </span>
                  </div>
                  <div className="mb-1">
                    <strong>Days:</strong> {request.days_of_week?.map((d: string) => d.charAt(0).toUpperCase() + d.slice(1)).join(', ') || request.day_of_week}
                  </div>
                  {request.request_type === 'availability' && request.start_time && request.end_time && (
                    <div className="flex items-center gap-2 mb-1">
                      <Clock className="w-4 h-4" />
                      <span>{request.start_time} - {request.end_time}</span>
                    </div>
                  )}
                  {request.employee_comment && (
                    <div className="text-gray-600 italic">
                      "{request.employee_comment}"
                    </div>
                  )}
                  {request.manager_comment && (
                    <div className="text-sm text-gray-600 mt-2">
                      <strong>Manager note:</strong> {request.manager_comment}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
