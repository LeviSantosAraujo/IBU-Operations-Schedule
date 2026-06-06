import { BrowserRouter as Router, Routes, Route, Link, useNavigate, Navigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { Calendar, Users, LayoutGrid, LogOut, Shield, User, Bell, FileSpreadsheet } from 'lucide-react'
import { auth } from './auth'
import Login from './components/Login'
import ExcelSetup from './components/ExcelSetup'
import AvailabilityInput from './components/AvailabilityInput'
import ScheduleManager from './components/ScheduleManager'
import EmployeeManagement from './components/EmployeeManagement'
import FloorCoverage from './components/FloorCoverage'
import DatabaseManagement from './components/DatabaseManagement'

// Protected Route Component
function ProtectedRoute({ 
  children, 
  requireManager = false 
}: { 
  children: React.ReactNode
  requireManager?: boolean 
}) {
  if (!auth.isAuthenticated()) {
    return <Navigate to="/login" replace />
  }
  
  if (requireManager && !auth.isManager()) {
    return <Navigate to="/availability" replace />
  }
  
  return <>{children}</>
}

// Main App Layout
function AppLayout() {
  const navigate = useNavigate()
  const user = auth.getUser()
  const isManager = auth.isManager()
  const [pendingApprovals, setPendingApprovals] = useState(0)
  
  useEffect(() => {
    if (isManager) {
      // Check for pending approvals
      const checkPending = async () => {
        try {
          const response = await fetch('/api/availability/pending')
          if (response.ok) {
            const pending = await response.json()
            setPendingApprovals(pending.length)
          }
        } catch (err) {
          console.error('Failed to check pending approvals')
        }
      }
      checkPending()
      // Poll every 30 seconds
      const interval = setInterval(checkPending, 30000)
      return () => clearInterval(interval)
    }
  }, [isManager])
  
  const handleLogout = async () => {
    await auth.logout()
    navigate('/login')
  }
  
  return (
    <div className="min-h-screen">
      {/* Navigation */}
      <nav className="bg-blue-900 text-white shadow-lg">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center">
              <div className="flex-shrink-0 font-bold text-xl">IBU Schedule System</div>
              <div className="ml-10 flex space-x-4">
                {/* Managers see full menu */}
                {isManager && (
                  <>
                    <Link to="/" className="flex items-center px-3 py-2 rounded hover:bg-blue-800">
                      <Calendar className="w-4 h-4 mr-2" />
                      Schedule
                    </Link>
                    <Link to="/floor-coverage" className="flex items-center px-3 py-2 rounded hover:bg-blue-800">
                      <LayoutGrid className="w-4 h-4 mr-2" />
                      Floor Coverage
                    </Link>
                    <Link to="/employees" className="flex items-center px-3 py-2 rounded hover:bg-blue-800">
                      <Users className="w-4 h-4 mr-2" />
                      Employees
                    </Link>
                    <Link to="/database" className="flex items-center px-3 py-2 rounded hover:bg-blue-800">
                      <FileSpreadsheet className="w-4 h-4 mr-2" />
                      Database
                    </Link>
                  </>
                )}
                {/* Everyone sees availability */}
                <Link to="/availability" className="flex items-center px-3 py-2 rounded hover:bg-blue-800">
                  <LayoutGrid className="w-4 h-4 mr-2" />
                  My Availability
                </Link>
              </div>
            </div>
            
            {/* User Info & Logout */}
            <div className="flex items-center gap-4">
              {/* Pending Approvals Alert for Managers */}
              {isManager && pendingApprovals > 0 && (
                <div className="flex items-center gap-2 bg-orange-500 px-3 py-1 rounded-full animate-pulse">
                  <Bell className="w-4 h-4" />
                  <span className="text-sm font-medium">{pendingApprovals} pending approval{pendingApprovals > 1 ? 's' : ''}</span>
                </div>
              )}
              
              <div className="flex items-center gap-2 text-sm">
                {isManager ? (
                  <Shield className="w-4 h-4 text-yellow-400" />
                ) : (
                  <User className="w-4 h-4" />
                )}
                <span>{user?.employee_name}</span>
                <span className="text-blue-300">({user?.role})</span>
              </div>
              <button
                onClick={handleLogout}
                className="flex items-center px-3 py-2 rounded hover:bg-blue-800 text-sm"
              >
                <LogOut className="w-4 h-4 mr-1" />
                Logout
              </button>
            </div>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 py-6">
        <Routes>
          <Route path="/" element={
            <ProtectedRoute requireManager>
              <ScheduleManager />
            </ProtectedRoute>
          } />
          <Route path="/availability" element={
            <ProtectedRoute>
              <AvailabilityInput />
            </ProtectedRoute>
          } />
          <Route path="/floor-coverage" element={
            <ProtectedRoute requireManager>
              <FloorCoverage />
            </ProtectedRoute>
          } />
          <Route path="/employees" element={
            <ProtectedRoute requireManager>
              <EmployeeManagement />
            </ProtectedRoute>
          } />
          <Route path="/database" element={
            <ProtectedRoute requireManager>
              <DatabaseManagement />
            </ProtectedRoute>
          } />
        </Routes>
      </main>
    </div>
  )
}

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(auth.isAuthenticated())
  
  const handleLogin = () => {
    setIsLoggedIn(true)
  }
  
  return (
    <Router>
      <Routes>
        <Route 
          path="/login" 
          element={
            isLoggedIn ? <Navigate to="/" replace /> : 
            <Login onLogin={handleLogin} />
          } 
        />
        <Route 
          path="/setup" 
          element={
            <ExcelSetup onSetupComplete={() => {}} />
          } 
        />
        <Route 
          path="/*" 
          element={
            isLoggedIn ? <AppLayout /> : <Navigate to="/login" replace />
          } 
        />
      </Routes>
    </Router>
  )
}

export default App
