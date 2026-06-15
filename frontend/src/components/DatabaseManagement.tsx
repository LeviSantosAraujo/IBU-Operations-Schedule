import { useState } from 'react'
import { FileSpreadsheet, Download, Upload, AlertCircle, Info } from 'lucide-react'
import { auth } from '../auth'
import { API_BASE_URL } from '../api'

export default function DatabaseManagement() {
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const handleDownload = async () => {
    setLoading(true)
    setError('')
    setSuccess('')

    try {
      const response = await fetch(`${API_BASE_URL}/excel/download`, {
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
    } finally {
      setLoading(false)
    }
  }

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    setUploading(true)
    setError('')
    setSuccess('')

    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch(`${API_BASE_URL}/database/upload-excel`, {
        method: 'POST',
        headers: auth.getAuthHeaders(),
        body: formData
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to upload Excel file')
      }

      const result = await response.json()
      setSuccess(result.message || 'Excel file merged successfully')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload Excel file')
    } finally {
      setUploading(false)
      // Reset file input
      e.target.value = ''
    }
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center gap-3 mb-6">
        <FileSpreadsheet className="w-8 h-8 text-blue-600" />
        <h2 className="text-2xl font-bold text-gray-900">Database Export</h2>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-100 text-red-700 rounded flex items-center gap-2">
          <AlertCircle className="w-5 h-5" />
          {error}
        </div>
      )}

      {success && (
        <div className="mb-4 p-3 bg-green-100 text-green-700 rounded flex items-center gap-2">
          <Info className="w-5 h-5" />
          {success}
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
              <h3 className="font-medium">Export Database to Excel</h3>
              <p className="text-sm text-gray-500">Download current data as Excel file for offline viewing</p>
            </div>
          </div>
          <button
            onClick={handleDownload}
            disabled={loading}
            className="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2"
          >
            <Download className="w-4 h-4" />
            {loading ? 'Exporting...' : 'Export to Excel'}
          </button>
        </div>

        {/* Upload Excel File */}
        <div className="border rounded-lg p-4">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center">
              <Upload className="w-5 h-5 text-green-600" />
            </div>
            <div className="flex-1">
              <h3 className="font-medium">Import Database from Excel</h3>
              <p className="text-sm text-gray-500">Upload Excel file to replace all data (managers only)</p>
            </div>
          </div>
          <input
            type="file"
            accept=".xlsx"
            onChange={handleUpload}
            disabled={uploading}
            className="w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-green-50 file:text-green-700 hover:file:bg-green-100 disabled:opacity-50"
          />
          {uploading && (
            <div className="mt-3">
              <div className="flex items-center gap-2 text-sm text-gray-600 mb-2">
                <div className="animate-spin w-4 h-4 border-2 border-green-600 border-t-transparent rounded-full"></div>
                <span>Merging Excel file with existing data...</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div className="bg-green-600 h-2 rounded-full animate-pulse" style={{ width: '60%' }}></div>
              </div>
              <p className="mt-2 text-xs text-gray-500">This may take a few seconds. Employees will be preserved.</p>
            </div>
          )}
        </div>
      </div>

      <div className="mt-6 text-sm text-gray-500 bg-gray-50 p-3 rounded">
        <p className="font-medium mb-1 flex items-center gap-2">
          <Info className="w-4 h-4" />
          Important Notes:
        </p>
        <ul className="list-disc list-inside space-y-1">
          <li>Export downloads current data to Excel for viewing and analysis</li>
          <li>Import replaces ALL data with the uploaded Excel file</li>
          <li>Import is for managers only and writes to GitHub for persistence</li>
          <li>Data is automatically saved to GitHub on every change</li>
        </ul>
      </div>
    </div>
  )
}
