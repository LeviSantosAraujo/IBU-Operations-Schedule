import { useState } from 'react'
import { FileSpreadsheet, Upload, Plus, Download, AlertCircle, Check } from 'lucide-react'
import { auth } from '../auth'

export default function DatabaseManagement() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)

  const handleDownload = async () => {
    try {
      const response = await fetch('/api/excel/download', {
        headers: auth.getAuthHeaders()
      })
      
      if (!response.ok) {
        throw new Error('Failed to download Excel file')
      }
      
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'IBU_Schedule.xlsx'
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (err) {
      setError('Failed to download Excel file')
    }
  }

  const handleCreateNew = async () => {
    setLoading(true)
    setError('')
    
    try {
      const response = await fetch('/api/excel/create-new', {
        method: 'POST',
        headers: auth.getAuthHeaders()
      })
      
      if (!response.ok) {
        throw new Error('Failed to create Excel file')
      }
      
      alert('New Excel database created successfully!')
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
      const response = await fetch('/api/excel/upload', {
        method: 'POST',
        headers: auth.getAuthHeaders(),
        body: formData
      })

      if (!response.ok) {
        throw new Error('Failed to upload Excel file')
      }

      alert('Excel file uploaded successfully!')
      setSelectedFile(null)
    } catch (err) {
      setError('Failed to upload Excel file')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center gap-3 mb-6">
        <FileSpreadsheet className="w-8 h-8 text-blue-600" />
        <h2 className="text-2xl font-bold text-gray-900">Database Management</h2>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-100 text-red-700 rounded flex items-center gap-2">
          <AlertCircle className="w-5 h-5" />
          {error}
        </div>
      )}

      <div className="space-y-6">
        {/* Download Current Database */}
        <div className="border rounded-lg p-4">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center">
              <Download className="w-5 h-5 text-blue-600" />
            </div>
            <div className="flex-1">
              <h3 className="font-medium">Download Current Database</h3>
              <p className="text-sm text-gray-500">Download the current Excel file to view or edit offline</p>
            </div>
          </div>
          <button
            onClick={handleDownload}
            className="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 flex items-center justify-center gap-2"
          >
            <Download className="w-4 h-4" />
            Download Excel File
          </button>
        </div>

        {/* Upload New Database */}
        <div className="border rounded-lg p-4">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center">
              <Upload className="w-5 h-5 text-green-600" />
            </div>
            <div className="flex-1">
              <h3 className="font-medium">Upload New Database</h3>
              <p className="text-sm text-gray-500">Replace the current database with a new Excel file</p>
            </div>
          </div>
          
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

        {/* Create New Database */}
        <div className="border rounded-lg p-4">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 bg-purple-100 rounded-full flex items-center justify-center">
              <Plus className="w-5 h-5 text-purple-600" />
            </div>
            <div className="flex-1">
              <h3 className="font-medium">Create New Database</h3>
              <p className="text-sm text-gray-500">Start with a fresh Excel database</p>
            </div>
          </div>
          <button
            onClick={handleCreateNew}
            disabled={loading}
            className="w-full bg-purple-600 text-white py-2 rounded hover:bg-purple-700 disabled:opacity-50 flex items-center justify-center gap-2"
          >
            <Plus className="w-4 h-4" />
            {loading ? 'Creating...' : 'Create New Database'}
          </button>
        </div>
      </div>

      <div className="mt-6 text-sm text-gray-500 bg-gray-50 p-3 rounded">
        <p className="font-medium mb-1">Important Notes:</p>
        <ul className="list-disc list-inside space-y-1">
          <li>Uploading a new database will replace the current one</li>
          <li>Make sure to download the current database before replacing it</li>
          <li>Changes made in the Excel file will be reflected in the system</li>
        </ul>
      </div>
    </div>
  )
}
