import { useState, useEffect } from 'react'
import { getEmployees, createEmployee, updateEmployee, deleteEmployee, updateManagerPassword } from '../api'
import { Plus, Edit, Trash2, Check, X } from 'lucide-react'

const employeeTypes = [
  { value: 'employee', label: 'Employee', maxHours: 24 },
  { value: 'intern', label: 'Intern', maxHours: 15 },
  { value: 'manager', label: 'Manager', maxHours: 80 }
]

export default function EmployeeManagement() {
  const [employees, setEmployees] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState<string | null>(null) // 'add', 'update', or employee_id for delete
  const [editing, setEditing] = useState<string | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    employee_type: 'employee',
    max_hours_per_week: 24,
    active: true,
    password: ''
  })

  useEffect(() => {
    loadEmployees()
  }, [])

  const loadEmployees = async () => {
    setLoading(true)
    try {
      const data = await getEmployees()
      setEmployees(data)
    } catch (err) {
      alert('Error loading employees')
    } finally {
      setLoading(false)
    }
  }

  const handleAdd = async () => {
    setSaving('add')
    try {
      await createEmployee({
        id: `emp_${Date.now()}`,
        ...formData
      })
      setShowAdd(false)
      setFormData({
        name: '',
        email: '',
        employee_type: 'employee',
        max_hours_per_week: 24,
        active: true,
        password: ''
      })
      loadEmployees()
    } catch (err) {
      alert('Error creating employee')
    } finally {
      setSaving(null)
    }
  }

  const handleUpdate = async (id: string) => {
    setSaving('update')
    try {
      // Only send fields that should be updated - let backend preserve preferences, created_at, etc.
      const updateData = {
        name: formData.name,
        email: formData.email,
        employee_type: formData.employee_type,
        max_hours_per_week: formData.max_hours_per_week,
        active: formData.active
      }
      await updateEmployee(id, updateData)

      // If manager and password provided, update password
      if (formData.employee_type === 'manager' && formData.password) {
        try {
          await updateManagerPassword(id, formData.password)
        } catch (pwdErr) {
          console.error('Password update error:', pwdErr)
          alert('Employee updated but password update failed. You may need to update the password separately.')
        }
      }

      setEditing(null)
      loadEmployees()
    } catch (err) {
      console.error('Update error:', err)
      alert('Error updating employee')
    } finally {
      setSaving(null)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this employee?')) return
    setSaving(id)
    try {
      await deleteEmployee(id)
      loadEmployees()
    } catch (err) {
      alert('Error deleting employee')
    } finally {
      setSaving(null)
    }
  }

  const startEdit = (emp: any) => {
    setEditing(emp.id)
    setFormData({
      name: emp.name,
      email: emp.email || '',
      employee_type: emp.employee_type,
      max_hours_per_week: emp.max_hours_per_week,
      active: emp.active,
      password: ''
    })
  }

  const handleTypeChange = (type: string) => {
    const typeInfo = employeeTypes.find(t => t.value === type)
    setFormData({
      ...formData,
      employee_type: type,
      max_hours_per_week: typeInfo?.maxHours || 24
    })
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Employee Management</h1>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
        >
          <Plus className="w-4 h-4" />
          Add Employee
        </button>
      </div>

      {/* Add Employee Form */}
      {showAdd && (
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h3 className="text-lg font-bold mb-4">Add New Employee</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Name</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full border rounded px-3 py-2"
                placeholder="Full Name"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Email</label>
              <input
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                className="w-full border rounded px-3 py-2"
                placeholder="email@example.com"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Type</label>
              <select
                value={formData.employee_type}
                onChange={(e) => handleTypeChange(e.target.value)}
                className="w-full border rounded px-3 py-2"
              >
                {employeeTypes.map(type => (
                  <option key={type.value} value={type.value}>{type.label}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="mt-4">
            <label className="block text-sm font-medium mb-1">
              Max Hours/Week: {formData.max_hours_per_week}h
            </label>
            <input
              type="range"
              min="5"
              max="80"
              step="1"
              value={formData.max_hours_per_week}
              onChange={(e) => setFormData({ ...formData, max_hours_per_week: parseInt(e.target.value) })}
              className="w-full"
            />
          </div>
          <div className="flex gap-2 mt-4">
            <button
              onClick={handleAdd}
              disabled={!formData.name || saving === 'add'}
              className="flex items-center gap-2 bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 disabled:opacity-50"
            >
              <Check className="w-4 h-4" />
              {saving === 'add' ? 'Saving...' : 'Save'}
            </button>
            <button
              onClick={() => setShowAdd(false)}
              className="flex items-center gap-2 bg-gray-300 px-4 py-2 rounded hover:bg-gray-400"
            >
              <X className="w-4 h-4" />
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Employees Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-100">
            <tr>
              <th className="p-3 text-left text-sm font-medium">Name</th>
              <th className="p-3 text-left text-sm font-medium">Type</th>
              <th className="p-3 text-left text-sm font-medium">Email</th>
              <th className="p-3 text-left text-sm font-medium">Max Hours</th>
              <th className="p-3 text-left text-sm font-medium">Password</th>
              <th className="p-3 text-left text-sm font-medium">Status</th>
              <th className="p-3 text-left text-sm font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {employees.map(emp => (
              <tr key={emp.id} className="border-t">
                {editing === emp.id ? (
                  <>
                    <td className="p-3">
                      <input
                        type="text"
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                        className="w-full border rounded px-2 py-1"
                      />
                    </td>
                    <td className="p-3">
                      <select
                        value={formData.employee_type}
                        onChange={(e) => handleTypeChange(e.target.value)}
                        className="w-full border rounded px-2 py-1"
                      >
                        {employeeTypes.map(type => (
                          <option key={type.value} value={type.value}>{type.label}</option>
                        ))}
                      </select>
                    </td>
                    <td className="p-3">
                      <input
                        type="email"
                        value={formData.email}
                        onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                        className="w-full border rounded px-2 py-1"
                      />
                    </td>
                    <td className="p-3">
                      <input
                        type="number"
                        value={formData.max_hours_per_week}
                        onChange={(e) => setFormData({ ...formData, max_hours_per_week: parseInt(e.target.value) })}
                        className="w-20 border rounded px-2 py-1"
                      />
                    </td>
                    <td className="p-3">
                      {formData.employee_type === 'manager' && (
                        <input
                          type="password"
                          placeholder="New password (optional)"
                          value={formData.password}
                          onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                          className="w-full border rounded px-2 py-1 text-sm"
                        />
                      )}
                    </td>
                    <td className="p-3">
                      <select
                        value={formData.active.toString()}
                        onChange={(e) => setFormData({ ...formData, active: e.target.value === 'true' })}
                        className="border rounded px-2 py-1"
                      >
                        <option value="true">Active</option>
                        <option value="false">Inactive</option>
                      </select>
                    </td>
                    <td className="p-3">
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleUpdate(emp.id)}
                          disabled={saving === 'update'}
                          className="text-green-600 hover:text-green-800 disabled:opacity-50"
                        >
                          {saving === 'update' ? 'Saving...' : <Check className="w-4 h-4" />}
                        </button>
                        <button
                          onClick={() => setEditing(null)}
                          disabled={saving === 'update'}
                          className="text-red-600 hover:text-red-800 disabled:opacity-50"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </>
                ) : (
                  <>
                    <td className="p-3 font-medium">{emp.name}</td>
                    <td className="p-3">
                      <span className="capitalize">
                        {emp.employee_type.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="p-3 text-gray-600">{emp.email || '-'}</td>
                    <td className="p-3">{emp.max_hours_per_week}h</td>
                    <td className="p-3">
                      <span className={`px-2 py-1 rounded text-xs ${emp.active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                        {emp.active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="p-3">
                      <div className="flex gap-2">
                        <button
                          onClick={() => startEdit(emp)}
                          disabled={saving === emp.id}
                          className="text-blue-600 hover:text-blue-800 disabled:opacity-50"
                        >
                          <Edit className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(emp.id)}
                          disabled={saving === emp.id}
                          className="text-red-600 hover:text-red-800 disabled:opacity-50"
                        >
                          {saving === emp.id ? 'Deleting...' : <Trash2 className="w-4 h-4" />}
                        </button>
                      </div>
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        
        {employees.length === 0 && (
          <div className="p-8 text-center text-gray-500">
            No employees found. Add your first employee above.
          </div>
        )}
      </div>
    </div>
  )
}
