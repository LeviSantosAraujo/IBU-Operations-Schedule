import { BrowserRouter as Router, Routes, Route, Link, useNavigate, Navigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { Users, LayoutGrid, LogOut, Shield, User, FileSpreadsheet, Calendar, Menu, X } from 'lucide-react'
import { auth } from './auth'
import Login from './components/Login'
import ExcelSetup from './components/ExcelSetup'
import ScheduleManager from './components/ScheduleManager'
import EmployeeManagement from './components/EmployeeManagement'
import DatabaseManagement from './components/DatabaseManagement'
import EmployeeScheduleView from './components/EmployeeScheduleView'
import MyAvailability from './components/MyAvailability'
import NotificationBell from './components/NotificationBell'
import { ErrorBoundary } from './components/ErrorBoundary'

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
    return <Navigate to="/my-schedule" replace />
  }
  
  return <>{children}</>
}

// Main App Layout
function AppLayout({ onLogout }: { onLogout: () => void }) {
  const navigate = useNavigate()
  const user = auth.getUser()
  const isManager = auth.isManager()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const handleLogoutClick = async () => {
    await auth.logout()
    onLogout()
    navigate('/login')
  }

  const handleMobileNavClick = (path: string) => {
    navigate(path)
    setMobileMenuOpen(false)
  }

  return (
    <div className="min-h-screen">
      {/* Navigation */}
      <nav className="bg-blue-900 text-white shadow-lg">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center">
              <div className="flex-shrink-0 font-bold text-xl">IBU Operations team schedule</div>
              {/* Desktop Navigation */}
              <div className="hidden md:flex ml-10 space-x-4">
                {/* Employees see their schedule and availability */}
                {!isManager && (
                  <>
                    <Link to="/my-schedule" className="flex items-center px-3 py-2 rounded hover:bg-blue-800">
                      <LayoutGrid className="w-4 h-4 mr-2" />
                      Schedule
                    </Link>
                    <Link to="/my-availability" className="flex items-center px-3 py-2 rounded hover:bg-blue-800">
                      <Calendar className="w-4 h-4 mr-2" />
                      My Availability
                    </Link>
                  </>
                )}
                {/* Managers see full menu */}
                {isManager && (
                  <>
                    <Link to="/manager" className="flex items-center px-3 py-2 rounded hover:bg-blue-800">
                      <LayoutGrid className="w-4 h-4 mr-2" />
                      Schedule Manager
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
              </div>
            </div>

            {/* Mobile Menu Button */}
            <div className="md:hidden flex items-center gap-4">
              <NotificationBell />
              <button
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                className="p-2 rounded hover:bg-blue-800"
              >
                {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
              </button>
            </div>

            {/* Desktop User Info & Logout */}
            <div className="hidden md:flex items-center gap-4">
              <NotificationBell />
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
                onClick={handleLogoutClick}
                className="flex items-center px-3 py-2 rounded hover:bg-blue-800 text-sm"
              >
                <LogOut className="w-4 h-4 mr-1" />
                Logout
              </button>
            </div>
          </div>

          {/* Mobile Menu */}
          {mobileMenuOpen && (
            <div className="md:hidden border-t border-blue-800">
              <div className="px-2 pt-2 pb-3 space-y-1">
                {/* Employees see their schedule and availability */}
                {!isManager && (
                  <>
                    <button
                      onClick={() => handleMobileNavClick('/my-schedule')}
                      className="flex items-center w-full px-3 py-2 rounded hover:bg-blue-800 text-left"
                    >
                      <LayoutGrid className="w-4 h-4 mr-2" />
                      Schedule
                    </button>
                    <button
                      onClick={() => handleMobileNavClick('/my-availability')}
                      className="flex items-center w-full px-3 py-2 rounded hover:bg-blue-800 text-left"
                    >
                      <Calendar className="w-4 h-4 mr-2" />
                      My Availability
                    </button>
                  </>
                )}
                {/* Managers see full menu */}
                {isManager && (
                  <>
                    <button
                      onClick={() => handleMobileNavClick('/manager')}
                      className="flex items-center w-full px-3 py-2 rounded hover:bg-blue-800 text-left"
                    >
                      <LayoutGrid className="w-4 h-4 mr-2" />
                      Schedule Manager
                    </button>
                    <button
                      onClick={() => handleMobileNavClick('/employees')}
                      className="flex items-center w-full px-3 py-2 rounded hover:bg-blue-800 text-left"
                    >
                      <Users className="w-4 h-4 mr-2" />
                      Employees
                    </button>
                    <button
                      onClick={() => handleMobileNavClick('/database')}
                      className="flex items-center w-full px-3 py-2 rounded hover:bg-blue-800 text-left"
                    >
                      <FileSpreadsheet className="w-4 h-4 mr-2" />
                      Database
                    </button>
                  </>
                )}
                {/* Mobile User Info & Logout */}
                <div className="border-t border-blue-800 pt-2 mt-2">
                  <div className="flex items-center gap-2 text-sm px-3 py-2">
                    {isManager ? (
                      <Shield className="w-4 h-4 text-yellow-400" />
                    ) : (
                      <User className="w-4 h-4" />
                    )}
                    <span>{user?.employee_name}</span>
                    <span className="text-blue-300">({user?.role})</span>
                  </div>
                  <button
                    onClick={handleLogoutClick}
                    className="flex items-center w-full px-3 py-2 rounded hover:bg-blue-800 text-left"
                  >
                    <LogOut className="w-4 h-4 mr-2" />
                    Logout
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 py-6">
        <Routes>
          <Route path="/" element={
            <ProtectedRoute>
              {!isManager ? <Navigate to="/my-schedule" replace /> : <Navigate to="/manager" replace />}
            </ProtectedRoute>
          } />
          <Route path="/my-schedule" element={
            <ProtectedRoute>
              <EmployeeScheduleView />
            </ProtectedRoute>
          } />
          <Route path="/my-availability" element={
            <ProtectedRoute>
              <MyAvailability />
            </ProtectedRoute>
          } />
          <Route path="/manager" element={
            <ProtectedRoute requireManager>
              <ScheduleManager />
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
  
  const handleLogout = () => {
    setIsLoggedIn(false)
  }
  
  return (
    <Router>
      <ErrorBoundary>
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
              isLoggedIn ? <AppLayout onLogout={handleLogout} /> : <Navigate to="/login" replace />
            } 
          />
        </Routes>
      </ErrorBoundary>
    </Router>
  )
}

export default App
