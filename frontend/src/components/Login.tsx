import { useState, useEffect } from 'react'
import { getEmployees } from '../api'
import { LogIn, User, Shield, Lock, Key } from 'lucide-react'

interface LoginProps {
  onLogin: () => void
}

export default function Login({ onLogin }: LoginProps) {
  const [employees, setEmployees] = useState<any[]>([])
  const [selectedEmployee, setSelectedEmployee] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [needsPassword, setNeedsPassword] = useState(false)
  const [isManager, setIsManager] = useState(false)
  const [showPasswordSetup, setShowPasswordSetup] = useState(false)
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  useEffect(() => {
    loadEmployees()
  }, [])

  useEffect(() => {
    // Check if selected employee is a manager and if they need password setup
    if (selectedEmployee) {
      const emp = employees.find(e => e.id === selectedEmployee)
      if (emp) {
        setIsManager(emp.employee_type === 'manager')
        checkManagerPasswordStatus(emp.id)
      }
    }
  }, [selectedEmployee])

  const loadEmployees = async () => {
    try {
      const data = await getEmployees(true)
      setEmployees(data)
    } catch (err) {
      setError('Failed to load employees')
    }
  }

  const checkManagerPasswordStatus = async (employeeId: string) => {
    try {
      const response = await fetch(`/api/managers/has-password/${employeeId}`)
      const data = await response.json()
      setNeedsPassword(!data.has_password)
    } catch (err) {
      // Default to not needing password if check fails
      setNeedsPassword(false)
    }
  }

  const handleLogin = async () => {
    if (!selectedEmployee) {
      setError('Please select an employee')
      return
    }

    setLoading(true)
    setError('')
    
    try {
      // For managers, include password
      const loginData = {
        employee_id: selectedEmployee,
        password: isManager ? password : undefined
      }
      
      const response = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(loginData)
      })
      
      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Login failed')
      }
      
      const data = await response.json()
      
      // If manager needs password setup, show that first
      if (data.requires_password_setup) {
        setShowPasswordSetup(true)
        setLoading(false)
        return
      }
      
      // Normal login flow
      localStorage.setItem('ibu_schedule_token', data.token)
      localStorage.setItem('ibu_schedule_user', JSON.stringify({
        employee_id: data.employee.id,
        employee_name: data.employee.name,
        role: data.role
      }))
      
      onLogin()
    } catch (err: any) {
      setError(err.message || 'Login failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleSetPassword = async () => {
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match')
      return
    }
    
    if (newPassword.length < 4) {
      setError('Password must be at least 4 characters')
      return
    }

    setLoading(true)
    setError('')

    try {
      const response = await fetch('/api/managers/set-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          employee_id: selectedEmployee,
          password: newPassword
        })
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to set password')
      }

      // Now login with the new password
      await handleLogin()
    } catch (err: any) {
      setError(err.message || 'Failed to set password')
      setLoading(false)
    }
  }

  const managers = employees.filter(e => e.employee_type === 'manager')
  const staff = employees.filter(e => e.employee_type !== 'manager')

  // Password setup screen for first-time manager login
  if (showPasswordSetup) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <div className="bg-white p-8 rounded-lg shadow-lg w-full max-w-md">
          <div className="text-center mb-6">
            <div className="w-16 h-16 bg-yellow-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <Key className="w-8 h-8 text-yellow-600" />
            </div>
            <h1 className="text-2xl font-bold text-blue-900">Set Your Password</h1>
            <p className="text-gray-600 mt-2">
              As a manager, you need to set a password for secure access.
            </p>
          </div>

          {error && (
            <div className="mb-4 p-3 bg-red-100 text-red-700 rounded">
              {error}
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">New Password</label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full border rounded px-3 py-2"
                placeholder="Enter password (min 4 characters)"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Confirm Password</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full border rounded px-3 py-2"
                placeholder="Confirm your password"
              />
            </div>

            <button
              onClick={handleSetPassword}
              disabled={loading}
              className="w-full bg-blue-600 text-white py-3 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2"
            >
              <Lock className="w-4 h-4" />
              {loading ? 'Setting Password...' : 'Set Password & Login'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100">
      <div className="bg-white p-8 rounded-lg shadow-lg w-full max-w-md">
        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold text-blue-900">IBU Schedule System</h1>
          <p className="text-gray-600 mt-2">Please select your name to continue</p>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-100 text-red-700 rounded">
            {error}
          </div>
        )}

        <div className="space-y-4">
          {/* Managers Section */}
          {managers.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-gray-500 mb-2 flex items-center gap-1">
                <Shield className="w-4 h-4" />
                Managers
              </h3>
              <div className="space-y-1">
                {managers.map(emp => (
                  <button
                    key={emp.id}
                    onClick={() => setSelectedEmployee(emp.id)}
                    className={`w-full p-3 text-left rounded border flex items-center gap-2 transition-colors ${
                      selectedEmployee === emp.id
                        ? 'bg-blue-50 border-blue-500'
                        : 'bg-white border-gray-200 hover:bg-gray-50'
                    }`}
                  >
                    <Shield className="w-4 h-4 text-blue-600" />
                    <span className="font-medium">{emp.name}</span>
                    <span className="text-xs text-gray-500 ml-auto">Full Access</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Staff Section */}
          {staff.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-gray-500 mb-2 flex items-center gap-1">
                <User className="w-4 h-4" />
                Staff
              </h3>
              <div className="space-y-1 max-h-48 overflow-y-auto">
                {staff.map(emp => (
                  <button
                    key={emp.id}
                    onClick={() => setSelectedEmployee(emp.id)}
                    className={`w-full p-3 text-left rounded border flex items-center gap-2 transition-colors ${
                      selectedEmployee === emp.id
                        ? 'bg-green-50 border-green-500'
                        : 'bg-white border-gray-200 hover:bg-gray-50'
                    }`}
                  >
                    <User className="w-4 h-4 text-green-600" />
                    <span>{emp.name}</span>
                    <span className="text-xs text-gray-500 ml-auto capitalize">
                      {emp.employee_type.replace('_', ' ')}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Password field for managers */}
          {isManager && (
            <div className="pt-4 border-t">
              <label className="block text-sm font-medium mb-1">
                <Lock className="w-4 h-4 inline mr-1" />
                Password {needsPassword && <span className="text-orange-600">(First login - will set new password)</span>}
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full border rounded px-3 py-2"
                placeholder={needsPassword ? "Create new password" : "Enter your password"}
              />
            </div>
          )}

          <button
            onClick={handleLogin}
            disabled={!selectedEmployee || loading || (isManager && !password)}
            className="w-full bg-blue-600 text-white py-3 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            <LogIn className="w-4 h-4" />
            {loading ? 'Logging in...' : 'Login'}
          </button>
        </div>

        <div className="mt-6 text-center text-sm text-gray-500">
          <p>Managers: Full system access</p>
          <p>Staff: Availability submission only</p>
        </div>
      </div>
    </div>
  )
}
