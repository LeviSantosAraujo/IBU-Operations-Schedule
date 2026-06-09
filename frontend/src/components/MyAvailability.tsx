import { useState, useEffect } from 'react'
import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'
import { format } from 'date-fns'
import { createAvailabilityRequest, getMyAvailabilityRequests } from '../api'
import { auth } from '../auth'
import { Save, Plus, Trash2, Calendar, Clock } from 'lucide-react'

const daysOfWeek = [
  { value: 'monday', label: 'Monday' },
  { value: 'tuesday', label: 'Tuesday' },
  { value: 'wednesday', label: 'Wednesday' },
  { value: 'thursday', label: 'Thursday' },
  { value: 'friday', label: 'Friday' },
  { value: 'saturday', label: 'Saturday' },
  { value: 'sunday', label: 'Sunday' },
]

export default function MyAvailability() {
  const [requestType, setRequestType] = useState<'availability' | 'day_off'>('availability')
  const [startDate, setStartDate] = useState<Date | null>(null)
  const [endDate, setEndDate] = useState<Date | null>(null)
  const [selectedDays, setSelectedDays] = useState<string[]>([])
  const [startTime, setStartTime] = useState('09:00')
  const [endTime, setEndTime] = useState('17:00')
  const [comment, setComment] = useState('')
  const [myRequests, setMyRequests] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [saved, setSaved] = useState(false)

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
    setSelectedDays(prev =>
      prev.includes(day) ? prev.filter(d => d !== day) : [...prev, day]
    )
  }

  const handleSubmit = async () => {
    if (!startDate || !endDate || selectedDays.length === 0) {
      alert('Please select date range and at least one day')
      return
    }

    if (requestType === 'availability' && (!startTime || !endTime)) {
      alert('Please select time range for availability request')
      return
    }

    setLoading(true)
    try {
      await createAvailabilityRequest({
        request_type: requestType,
        start_date: format(startDate, 'yyyy-MM-dd'),
        end_date: format(endDate, 'yyyy-MM-dd'),
        days_of_week: selectedDays,
        start_time: requestType === 'availability' ? startTime : null,
        end_time: requestType === 'availability' ? endTime : null,
        employee_comment: comment,
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
      // Reset form
      setStartDate(null)
      setEndDate(null)
      setSelectedDays([])
      setComment('')
      loadMyRequests()
    } catch (err) {
      alert('Error submitting request. Please try again.')
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

      {/* Request Form */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4">Submit New Request</h2>

        {/* Request Type */}
        <div className="mb-4">
          <label className="block text-sm font-medium mb-2">Request Type</label>
          <div className="flex gap-4">
            <label className="flex items-center gap-2">
              <input
                type="radio"
                value="availability"
                checked={requestType === 'availability'}
                onChange={(e) => setRequestType(e.target.value as any)}
                className="w-4 h-4"
              />
              <span>Time Range Availability</span>
            </label>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                value="day_off"
                checked={requestType === 'day_off'}
                onChange={(e) => setRequestType(e.target.value as any)}
                className="w-4 h-4"
              />
              <span>Day Off</span>
            </label>
          </div>
        </div>

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

        {/* Days of Week */}
        <div className="mb-4">
          <label className="block text-sm font-medium mb-2">Days of Week</label>
          <div className="flex flex-wrap gap-2">
            {daysOfWeek.map(day => (
              <button
                key={day.value}
                onClick={() => toggleDay(day.value)}
                className={`px-3 py-2 rounded border ${
                  selectedDays.includes(day.value)
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                }`}
              >
                {day.label}
              </button>
            ))}
          </div>
        </div>

        {/* Time Range (for availability requests only) */}
        {requestType === 'availability' && (
          <div className="grid grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium mb-2">Start Time</label>
              <input
                type="time"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                className="w-full border rounded px-3 py-2"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">End Time</label>
              <input
                type="time"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                className="w-full border rounded px-3 py-2"
              />
            </div>
          </div>
        )}

        {/* Comment */}
        <div className="mb-4">
          <label className="block text-sm font-medium mb-2">Comment (optional)</label>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            className="w-full border rounded px-3 py-2 h-20"
            placeholder="Reason for this request..."
          />
        </div>

        {/* Submit Button */}
        <button
          onClick={handleSubmit}
          disabled={loading}
          className="flex items-center gap-2 bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Submitting...' : <><Plus className="w-4 h-4" /> Submit Request</>}
        </button>

        {saved && (
          <div className="mt-2 text-green-600 text-sm">
            Request submitted successfully!
          </div>
        )}
      </div>

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
