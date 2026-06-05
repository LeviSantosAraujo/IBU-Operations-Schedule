import axios from 'axios'
import { auth } from './auth'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: `${API_URL}/api`,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add auth token to all requests
api.interceptors.request.use((config) => {
  const token = auth.getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Handle 401/403 errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      auth.logout()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// Employees
export const getEmployees = (activeOnly = false) => 
  api.get(`/employees?active_only=${activeOnly}`).then(r => r.data)

export const getEmployee = (id: string) => 
  api.get(`/employees/${id}`).then(r => r.data)

export const createEmployee = (data: any) => 
  api.post('/employees', data).then(r => r.data)

export const updateEmployee = (id: string, data: any) => 
  api.put(`/employees/${id}`, data).then(r => r.data)

export const deleteEmployee = (id: string) => 
  api.delete(`/employees/${id}`).then(r => r.data)

// Availability
export const getAvailabilities = (weekStartDate?: string, employeeId?: string) => {
  const params = new URLSearchParams()
  if (weekStartDate) params.append('week_start_date', weekStartDate)
  if (employeeId) params.append('employee_id', employeeId)
  return api.get(`/availability?${params}`).then(r => r.data)
}

export const getEmployeeAvailability = (employeeId: string, weekStartDate: string) => 
  api.get(`/availability/${employeeId}/${weekStartDate}`).then(r => r.data)

export const submitAvailability = (data: any) => 
  api.post('/availability', data).then(r => r.data)

export const getAvailabilityColors = () => 
  api.get('/availability/colors').then(r => r.data)

// Schedules
export const getSchedules = () => 
  api.get('/schedules').then(r => r.data)

export const getSchedule = (weekStartDate: string) => 
  api.get(`/schedules/${weekStartDate}`).then(r => r.data)

export const generateSchedule = (weekStartDate: string) => 
  api.post(`/schedules/generate/${weekStartDate}`).then(r => r.data)

export const saveSchedule = (data: any) => 
  api.post('/schedules', data).then(r => r.data)

export const updateScheduleShifts = (weekStartDate: string, shifts: any[]) => 
  api.put(`/schedules/${weekStartDate}/shifts`, shifts).then(r => r.data)

export const publishSchedule = (weekStartDate: string) => 
  api.post(`/schedules/${weekStartDate}/publish`).then(r => r.data)

export const deleteSchedule = (weekStartDate: string) => 
  api.delete(`/schedules/${weekStartDate}`).then(r => r.data)

// Floor Coverage
export const getFloorCoverage = (floor: string, dayOfWeek: string, timeSlot: string, weekStartDate: string) => 
  api.get(`/floor-coverage/${floor}/${dayOfWeek}/${timeSlot}?week_start_date=${weekStartDate}`).then(r => r.data)

export const getWeeklyFloorSummary = (weekStartDate: string) => 
  api.get(`/floor-coverage/summary/${weekStartDate}`).then(r => r.data)

// Analytics
export const getEmployeeHoursSummary = (weekStartDate: string) => 
  api.get(`/analytics/employee-hours/${weekStartDate}`).then(r => r.data)

// Config
export const getConfig = () => 
  api.get('/config').then(r => r.data)

export const updateConfig = (data: any) => 
  api.put('/config', data).then(r => r.data)

export default api
