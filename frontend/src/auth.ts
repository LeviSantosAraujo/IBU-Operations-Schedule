// Authentication utilities
const TOKEN_KEY = 'ibu_schedule_token'
const USER_KEY = 'ibu_schedule_user'
const API_URL = import.meta.env.VITE_API_URL || ''
const API_BASE_URL = `${API_URL}/api`

export interface User {
  employee_id: string
  employee_name: string
  role: 'admin' | 'manager' | 'employee' | 'intern' | 'student_worker'
}

export const auth = {
  login: async (employeeId: string): Promise<User> => {
    const response = await fetch(`${API_BASE_URL}/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ employee_id: employeeId })
    })
    
    if (!response.ok) {
      throw new Error('Login failed')
    }
    
    const data = await response.json()
    localStorage.setItem(TOKEN_KEY, data.token)
    localStorage.setItem(USER_KEY, JSON.stringify({
      employee_id: data.employee.id,
      employee_name: data.employee.name,
      role: data.role
    }))
    
    return {
      employee_id: data.employee.id,
      employee_name: data.employee.name,
      role: data.role
    }
  },
  
  logout: async () => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (token) {
      await fetch(`${API_BASE_URL}/logout`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      })
    }
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  },
  
  getToken: (): string | null => {
    return localStorage.getItem(TOKEN_KEY)
  },
  
  getUser: (): User | null => {
    const userStr = localStorage.getItem(USER_KEY)
    return userStr ? JSON.parse(userStr) : null
  },
  
  isAuthenticated: (): boolean => {
    return !!localStorage.getItem(TOKEN_KEY)
  },
  
  isManager: (): boolean => {
    const user = auth.getUser()
    return user?.role === 'manager'
  },
  
  getAuthHeaders: (): Record<string, string> => {
    const token = auth.getToken()
    return token ? { 'Authorization': `Bearer ${token}` } : {}
  }
}
