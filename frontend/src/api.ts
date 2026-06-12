import axios from 'axios'
import { auth } from './auth'

const API_URL = import.meta.env.VITE_API_URL || ''
export const API_BASE_URL = `${API_URL}/api`

const api = axios.create({
  baseURL: API_BASE_URL,
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

// Handle auth errors - only redirect on 401 for non-background requests
let isRedirecting = false
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && !isRedirecting) {
      const url = error.config?.url || ''
      // Don't redirect for background polling endpoints
      const pollingEndpoints = ['/notifications', '/availability-requests']
      const isPolling = pollingEndpoints.some(ep => url.includes(ep))
      if (!isPolling && window.location.pathname !== '/login') {
        isRedirecting = true
        auth.logout()
        window.location.replace('/login')
      }
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

export const updateManagerPassword = (employeeId: string, password: string) =>
  api.put('/managers/update-password', { employee_id: employeeId, password }).then(r => r.data)

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

export function clearSchedule(weekStartDate: string) {
  return api.post(`/schedules/${weekStartDate}/clear`).then(r => r.data)
}

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

// Staffing Targets
export const getStaffingTargets = () =>
  api.get('/staffing-targets').then(r => r.data)

export const updateStaffingTargets = (targets: Record<string, number>) =>
  api.put('/staffing-targets', targets).then(r => r.data)

// Availability Requests
export function getAvailabilityRequests() {
  return api.get('/availability-requests').then(r => r.data)
}

export function getMyAvailabilityRequests() {
  return api.get('/availability-requests/my').then(r => r.data)
}

export function createAvailabilityRequest(data: any) {
  return api.post('/availability-requests', data).then(r => r.data)
}

export function approveAvailabilityRequest(requestId: string, comment?: string) {
  return api.put(`/availability-requests/${requestId}/approve`, { comment }).then(r => r.data)
}

export function rejectAvailabilityRequest(requestId: string, comment: string) {
  return api.put(`/availability-requests/${requestId}/reject`, { comment }).then(r => r.data)
}

// Notifications
export const getNotifications = () => 
  api.get('/notifications').then(r => r.data)

export const markNotificationAsRead = (notificationId: string) => 
  api.put(`/notifications/${notificationId}/read`).then(r => r.data)

// Events
export function getEvents() {
  return api.get('/events/list').then(r => r.data)
}

export function createEvent(data: any) {
  return api.post('/events', data).then(r => r.data)
}

export function updateEvent(eventId: string, data: any) {
  return api.put(`/events/${eventId}`, data).then(r => r.data)
}

export function deleteEvent(eventId: string) {
  return api.delete(`/events/${eventId}`).then(r => r.data)
}

export default api
