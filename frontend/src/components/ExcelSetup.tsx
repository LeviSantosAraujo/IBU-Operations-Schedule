import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { FileSpreadsheet, Upload, Plus, Check, AlertCircle, Home, Shield } from 'lucide-react'
import { auth } from '../auth'
import { API_BASE_URL } from '../api'

interface ExcelSetupProps {
  onSetupComplete: () => void
}

export default function ExcelSetup({ onSetupComplete }: ExcelSetupProps) {
  const navigate = useNavigate()
  const [status, setStatus] = useState<{ configured: boolean; file_path?: string; file_exists?: boolean } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [isManager, setIsManager] = useState(false)

  useEffect(() => {
    checkStatus()
    setIsManager(auth.isManager())
  }, [])

  const checkStatus = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/excel/status`)
      const data = await response.json()
      setStatus(data)
      if (data.configured && data.file_exists) {
        // Already configured, stay on this page but show configured state
        // Don't auto-redirect so managers can change the database if needed
      }
    } catch (err) {
      // Don't show error on initial status check - it's expected when not configured
      console.error('Status check failed:', err)
      setStatus({ configured: false, file_path: undefined, file_exists: false })
    }
  }

  const handleCreateNew = async () => {
    setLoading(true)
    setError('')
    
    try {
      const response = await fetch(`${API_BASE_URL}/excel/create-new`, {
        method: 'POST',
        headers: auth.getAuthHeaders()
      })
      
      if (!response.ok) {
        throw new Error('Failed to create Excel file')
      }
      
      const data = await response.json()
      setStatus({ configured: true, file_path: data.file_path, file_exists: true })
    } catch (err) {
      setError('Failed to create new Excel database')
    } finally {
      setLoading(false)
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0])
    }
  }

  const handleUpload = async () => {
    if (!selectedFile) {
      setError('Please select a file first')
      return
    }

    setLoading(true)
    setError('')

    const formData = new FormData()
    formData.append('file', selectedFile)

    try {
      const response = await fetch(`${API_BASE_URL}/excel/upload`, {
        method: 'POST',
        headers: auth.getAuthHeaders(),
        body: formData
      })

      if (!response.ok) {
        throw new Error('Failed to upload Excel file')
      }

      const data = await response.json()
      setStatus({ configured: true, file_path: data.file_path, file_exists: true })
    } catch (err) {
      setError('Failed to upload Excel file')
    } finally {
      setLoading(false)
    }
  }

  const handleGoToLogin = () => {
    onSetupComplete()
    navigate('/login')
  }

  // Show configured state if Excel is already set up
  if (status?.configured && status?.file_exists) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <div className="bg-white p-8 rounded-lg shadow-lg w-full max-w-lg">
          <div className="flex items-center justify-between mb-4">
            <button
              onClick={handleGoToLogin}
              className="text-gray-500 hover:text-gray-700 flex items-center gap-1 text-sm"
            >
              <Home className="w-4 h-4" />
              Home
            </button>
          </div>
          
          <div className="text-center mb-6">
            <Check className="w-16 h-16 text-green-600 mx-auto mb-4" />
            <h1 className="text-2xl font-bold text-gray-900">Excel Database Configured</h1>
            <p className="text-gray-600 mt-2">
              The system is using an Excel file as its database.
            </p>
          </div>

          {isManager ? (
            <div className="space-y-4">
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Shield className="w-5 h-5 text-blue-600" />
                  <h3 className="font-medium text-blue-900">Manager Options</h3>
                </div>
                <p className="text-sm text-blue-700 mb-4">
                  As a manager, you can change the Excel database if needed.
                </p>
                
                <div className="space-y-3">
                  <button
                    onClick={handleCreateNew}
                    disabled={loading}
                    className="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    <Plus className="w-4 h-4" />
                    {loading ? 'Creating...' : 'Create New Database'}
                  </button>
                  
                  <div className="border rounded-lg p-3">
                    <input
                      type="file"
                      accept=".xlsx,.xls"
                      onChange={handleFileSelect}
                      className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 mb-2"
                    />
                    {selectedFile && (
                      <button
                        onClick={handleUpload}
                        disabled={loading}
                        className="w-full bg-green-600 text-white py-2 rounded hover:bg-green-700 disabled:opacity-50 flex items-center justify-center gap-2"
                      >
                        <Upload className="w-4 h-4" />
                        {loading ? 'Uploading...' : `Upload ${selectedFile.name}`}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
              <p className="text-sm text-gray-600">
                The Excel database is configured and managed by your managers. 
                Contact them if you need to make changes to the database.
              </p>
            </div>
          )}

          {error && (
            <div className="mt-4 p-3 bg-red-100 text-red-700 rounded flex items-center gap-2">
              <AlertCircle className="w-5 h-5" />
              {error}
            </div>
          )}

          <div className="mt-6">
            <button
              onClick={handleGoToLogin}
              className="w-full bg-gray-600 text-white py-2 rounded hover:bg-gray-700 flex items-center justify-center gap-2"
            >
              <Home className="w-4 h-4" />
              Go to Login
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100">
      <div className="bg-white p-8 rounded-lg shadow-lg w-full max-w-lg">
        <div className="flex items-center justify-between mb-4">
          <button
            onClick={handleGoToLogin}
            className="text-gray-500 hover:text-gray-700 flex items-center gap-1 text-sm"
          >
            <Home className="w-4 h-4" />
            Home
          </button>
        </div>
        
        <div className="text-center mb-6">
          <FileSpreadsheet className="w-16 h-16 text-green-600 mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-gray-900">Excel Database Setup</h1>
          <p className="text-gray-600 mt-2">
            The scheduling system uses an Excel file as its database.
            Choose how you want to set it up.
          </p>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-100 text-red-700 rounded flex items-center gap-2">
            <AlertCircle className="w-5 h-5" />
            {error}
          </div>
        )}

        <div className="space-y-4">
          {/* Create New Database */}
          <div className="border rounded-lg p-4 hover:border-blue-500 transition-colors">
            <button
              onClick={handleCreateNew}
              disabled={loading}
              className="w-full flex items-center gap-3 text-left"
            >
              <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center">
                <Plus className="w-5 h-5 text-blue-600" />
              </div>
              <div className="flex-1">
                <h3 className="font-medium">Create New Database</h3>
                <p className="text-sm text-gray-500">Start with a fresh Excel file</p>
              </div>
            </button>
          </div>

          {/* Upload Existing */}
          <div className="border rounded-lg p-4 hover:border-green-500 transition-colors">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center">
                <Upload className="w-5 h-5 text-green-600" />
              </div>
              <div className="flex-1">
                <h3 className="font-medium">Upload Existing Excel</h3>
                <p className="text-sm text-gray-500">Use your existing schedule spreadsheet</p>
              </div>
            </div>
            
            <div className="ml-13 pl-13">
              <input
                type="file"
                accept=".xlsx,.xls"
                onChange={handleFileSelect}
                className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-green-50 file:text-green-700 hover:file:bg-green-100 mb-2"
              />
              {selectedFile && (
                <button
                  onClick={handleUpload}
                  disabled={loading}
                  className="w-full bg-green-600 text-white py-2 rounded hover:bg-green-700 disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  <Check className="w-4 h-4" />
                  {loading ? 'Uploading...' : `Upload ${selectedFile.name}`}
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="mt-6 text-sm text-gray-500 bg-gray-50 p-3 rounded">
          <p className="font-medium mb-1">What happens:</p>
          <ul className="list-disc list-inside space-y-1">
            <li>Employees, passwords, and availability stored in Excel tabs</li>
            <li>Each week's schedule gets its own tab (e.g., "Schedule_2024_01_15")</li>
            <li>You can download the Excel anytime to view or edit offline</li>
            <li>Changes made in Excel will be reflected in the system</li>
          </ul>
        </div>
      </div>
    </div>
  )
}
