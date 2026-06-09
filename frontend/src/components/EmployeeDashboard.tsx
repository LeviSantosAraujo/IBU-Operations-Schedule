import { useState } from 'react'
import { Calendar, LayoutGrid } from 'lucide-react'
import EmployeeScheduleView from './EmployeeScheduleView'
import AvailabilityInput from './AvailabilityInput'

export default function EmployeeDashboard() {
  const [activeTab, setActiveTab] = useState<'schedule' | 'availability'>('schedule')
  const [initialDate] = useState<Date | null>(null)

  return (
    <div>
      {/* Tab Navigation */}
      <div className="mb-6">
        <div className="flex gap-2 border-b">
          <button
            onClick={() => setActiveTab('schedule')}
            className={`flex items-center gap-2 px-4 py-2 font-medium transition-colors ${
              activeTab === 'schedule'
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-600 hover:text-gray-800'
            }`}
          >
            <Calendar className="w-4 h-4" />
            Schedule
          </button>
          <button
            onClick={() => setActiveTab('availability')}
            className={`flex items-center gap-2 px-4 py-2 font-medium transition-colors ${
              activeTab === 'availability'
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-600 hover:text-gray-800'
            }`}
          >
            <LayoutGrid className="w-4 h-4" />
            My Availability
          </button>
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === 'schedule' && (
        <EmployeeScheduleView />
      )}
      {activeTab === 'availability' && (
        <AvailabilityInput initialDate={initialDate} />
      )}
    </div>
  )
}
