import { useState, useEffect } from 'react'
import DatePicker from 'react-datepicker'
import { format, startOfWeek, addDays } from 'date-fns'
import { getWeeklyFloorSummary, getFloorCoverage } from '../api'
import { Building2, Users, Clock, ChevronDown, ChevronUp } from 'lucide-react'

const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
const timeSlots = ['morning', 'afternoon', 'evening']
const floors = [
  { id: 'ground', name: 'Ground Floor', color: 'bg-green-100 border-green-300' },
  { id: 'second', name: '2nd Floor', color: 'bg-blue-100 border-blue-300' },
  { id: 'sixth', name: '6th Floor', color: 'bg-purple-100 border-purple-300' }
]

export default function FloorCoverage() {
  const [weekStart, setWeekStart] = useState<Date>(startOfWeek(new Date(), { weekStartsOn: 1 }))
  const [summary, setSummary] = useState<any>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [detailData, setDetailData] = useState<any>(null)
  const [_loading, setLoading] = useState(false)

  useEffect(() => {
    loadSummary()
  }, [weekStart])

  const loadSummary = async () => {
    if (!weekStart) return
    setLoading(true)
    try {
      const formattedDate = format(weekStart, 'yyyy-MM-dd')
      const data = await getWeeklyFloorSummary(formattedDate)
      setSummary(data)
    } catch (err) {
      console.error('Error loading summary:', err)
    } finally {
      setLoading(false)
    }
  }

  const loadDetail = async (floor: string, day: string, slot: string) => {
    const key = `${floor}-${day}-${slot}`
    if (expanded === key) {
      setExpanded(null)
      return
    }
    
    try {
      const formattedDate = format(weekStart, 'yyyy-MM-dd')
      const data = await getFloorCoverage(floor, day, slot, formattedDate)
      setDetailData(data)
      setExpanded(key)
    } catch (err) {
      console.error('Error loading detail:', err)
    }
  }

  const getSlotLabel = (slot: string) => {
    const labels: any = {
      morning: 'Morning (8am-12pm)',
      afternoon: 'Afternoon (12pm-5pm)',
      evening: 'Evening (5pm-10pm)'
    }
    return labels[slot] || slot
  }

  const weekDates = days.map((_, index) => addDays(weekStart, index))

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Floor Coverage</h1>

      {/* Week Selector */}
      <div className="bg-white rounded-lg shadow p-4 mb-6">
        <div className="flex items-center gap-4">
          <label className="font-medium">Week Starting:</label>
          <DatePicker
            selected={weekStart}
            onChange={(date: Date | null) => date && setWeekStart(startOfWeek(date, { weekStartsOn: 1 }))}
            filterDate={(date: Date) => date.getDay() === 1}
            className="border rounded px-3 py-2"
            dateFormat="yyyy-MM-dd"
          />
          <span className="text-gray-500">
            {format(weekStart, 'MMMM d')} - {format(addDays(weekStart, 6), 'MMMM d, yyyy')}
          </span>
        </div>
      </div>

      {/* Coverage Summary */}
      {summary && (
        <div className="space-y-6">
          {floors.map(floor => (
            <div key={floor.id} className="bg-white rounded-lg shadow overflow-hidden">
              <div className={`p-4 ${floor.color} border-b`}>
                <div className="flex items-center gap-2">
                  <Building2 className="w-5 h-5" />
                  <h2 className="text-lg font-bold">{floor.name}</h2>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="bg-gray-50">
                      <th className="p-3 text-left text-sm font-medium">Time Slot</th>
                      {days.map((day, i) => (
                        <th key={day} className="p-3 text-center text-sm font-medium">
                          <div className="capitalize">{day.slice(0, 3)}</div>
                          <div className="text-xs text-gray-500">{format(weekDates[i], 'M/d')}</div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {timeSlots.map(slot => (
                      <tr key={slot} className="border-t">
                        <td className="p-3">
                          <div className="flex items-center gap-2">
                            <Clock className="w-4 h-4 text-gray-500" />
                            <span className="text-sm">{getSlotLabel(slot)}</span>
                          </div>
                        </td>
                        {days.map(day => {
                          const count = summary[floor.id]?.[day]?.[slot] || 0
                          const key = `${floor.id}-${day}-${slot}`
                          const isExpanded = expanded === key
                          
                          return (
                            <td key={`${floor.id}-${day}-${slot}`} className="p-3 text-center">
                              <button
                                onClick={() => loadDetail(floor.id, day, slot)}
                                className={`inline-flex items-center gap-1 px-3 py-1 rounded text-sm transition-colors ${
                                  count === 0 
                                    ? 'bg-red-100 text-red-800 hover:bg-red-200' 
                                    : count < 2 
                                      ? 'bg-yellow-100 text-yellow-800 hover:bg-yellow-200'
                                      : 'bg-green-100 text-green-800 hover:bg-green-200'
                                }`}
                              >
                                <Users className="w-3 h-3" />
                                {count}
                                {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                              </button>
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Detail Panel */}
              {expanded && detailData && expanded.startsWith(floor.id) && (
                <div className="p-4 bg-gray-50 border-t">
                  <h3 className="font-medium mb-2">
                    {floor.name} - {expanded.split('-')[1].charAt(0).toUpperCase() + expanded.split('-')[1].slice(1)} - {getSlotLabel(expanded.split('-')[2])}
                  </h3>
                  {detailData.employees && detailData.employees.length > 0 ? (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                      {detailData.employees.map((emp: any) => (
                        <div key={emp.id} className="bg-white p-2 rounded border text-sm">
                          <div className="font-medium">{emp.name}</div>
                          <div className="text-gray-500 text-xs">
                            {emp.shift?.start_time} - {emp.shift?.end_time}
                          </div>
                          <div className="text-gray-500 text-xs">{emp.shift?.hours}h</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-gray-500 text-sm">No employees scheduled</p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Legend */}
      <div className="mt-6 bg-white rounded-lg shadow p-4">
        <h3 className="font-medium mb-3">Coverage Legend</h3>
        <div className="flex flex-wrap gap-4">
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 bg-green-100 border border-green-300 rounded"></div>
            <span className="text-sm">Well staffed (2+)</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 bg-yellow-100 border border-yellow-300 rounded"></div>
            <span className="text-sm">Understaffed (1)</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 bg-red-100 border border-red-300 rounded"></div>
            <span className="text-sm">No coverage (0)</span>
          </div>
        </div>
      </div>
    </div>
  )
}
