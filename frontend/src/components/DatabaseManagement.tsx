import { useState } from 'react'
import { FileSpreadsheet, Download, AlertCircle, Info } from 'lucide-react'
import { auth } from '../auth'
import { API_BASE_URL } from '../api'

export default function DatabaseManagement() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleDownload = async () => {
    setLoading(true)
    setError('')

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
      </div>

      <div className="mt-6 text-sm text-gray-500 bg-gray-50 p-3 rounded">
        <p className="font-medium mb-1 flex items-center gap-2">
          <Info className="w-4 h-4" />
          Important Notes:
        </p>
        <ul className="list-disc list-inside space-y-1">
          <li>This exports current data to Excel for viewing and analysis only</li>
          <li>Changes made in the Excel file will NOT be reflected in the system</li>
          <li>Use the regular UI (Employees, Schedule, etc.) to make changes</li>
          <li>Data is automatically backed up daily to Excel format</li>
        </ul>
      </div>
    </div>
  )
}
