import { useState, useEffect } from 'react'
import { Bell, X, Check, XCircle, User } from 'lucide-react'
import { getNotifications, markNotificationAsRead, markAllNotificationsAsRead, getAvailabilityRequests, approveAvailabilityRequest, rejectAvailabilityRequest } from '../api'
import { auth } from '../auth'

export default function NotificationBell() {
  const [notifications, setNotifications] = useState<any[]>([])
  const [availabilityRequests, setAvailabilityRequests] = useState<any[]>([])
  const [isOpen, setIsOpen] = useState(false)
  const [unreadCount, setUnreadCount] = useState(0)
  const [isManager] = useState(auth.isManager())
  const [hasAuthError, setHasAuthError] = useState(false)
  const [optimisticallyReadNotifications, setOptimisticallyReadNotifications] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (hasAuthError) return // Stop polling if auth error occurred

    loadNotifications()
    if (isManager) {
      loadAvailabilityRequests()
    }
    // Poll for new notifications every 30 seconds
    const interval = setInterval(() => {
      if (!hasAuthError) {
        loadNotifications()
        if (isManager) {
          loadAvailabilityRequests()
        }
      }
    }, 30000)
    return () => clearInterval(interval)
  }, [isManager, hasAuthError])

  const loadNotifications = async () => {
    try {
      const data = await getNotifications()
      // Merge server data with optimistic updates - keep notifications marked as read
      const mergedData = (data || []).map((n: any) => 
        optimisticallyReadNotifications.has(n.id) ? { ...n, read: true } : n
      )
      setNotifications(mergedData)
      setUnreadCount(mergedData.filter((n: any) => !n.read).length)
      setHasAuthError(false)
    } catch (err: any) {
      if (err.response?.status === 401 || err.response?.status === 403) {
        setHasAuthError(true)
      }
      console.error('Error loading notifications:', err)
    }
  }

  const loadAvailabilityRequests = async () => {
    try {
      const data = await getAvailabilityRequests()
      console.log('[FRONTEND] Loading availability requests:', data)
      const pendingRequests = data.filter((r: any) =>
        r.status === 'pending' || r.status === 'AvailabilityRequestStatus.PENDING'
      )
      console.log('[FRONTEND] Pending requests:', pendingRequests)
      console.log('[FRONTEND] All request statuses:', data.map((r: any) => ({ id: r.id, status: r.status, days: r.days_of_week })))
      setAvailabilityRequests(pendingRequests)
      setHasAuthError(false)
    } catch (err: any) {
      if (err.response?.status === 401 || err.response?.status === 403) {
        setHasAuthError(true)
      }
      console.error('Error loading availability requests:', err)
    }
  }

  const handleMarkAsRead = async (notificationId: string) => {
    // Optimistically mark notification as read
    setOptimisticallyReadNotifications(prev => new Set(prev).add(notificationId))
    setNotifications(prev => prev.map(n => 
      n.id === notificationId ? { ...n, read: true } : n
    ))
    setUnreadCount(prev => Math.max(0, prev - 1))

    // Run API call in background
    markNotificationAsRead(notificationId)
      .then(() => {
        // Remove from optimistic set once confirmed by server
        setOptimisticallyReadNotifications(prev => {
          const newSet = new Set(prev)
          newSet.delete(notificationId)
          return newSet
        })
        loadNotifications()
      })
      .catch((err) => {
        console.error('Error marking notification as read:', err)
        // Revert optimistic update if it failed
        setOptimisticallyReadNotifications(prev => {
          const newSet = new Set(prev)
          newSet.delete(notificationId)
          return newSet
        })
        loadNotifications()
      })
  }

  const handleMarkAllAsRead = async () => {
    // Optimistically mark all notifications as read
    const notificationIds = regularNotifications.filter(n => !n.read).map(n => n.id)
    setOptimisticallyReadNotifications(prev => new Set([...prev, ...notificationIds]))
    setNotifications(prev => prev.map(n => ({ ...n, read: true })))
    setUnreadCount(0)

    // Run API call in background
    markAllNotificationsAsRead()
      .then(() => {
        // Keep them in optimistic set to prevent reappearing on poll
        console.log('All notifications marked as read')
      })
      .catch((err) => {
        console.error('Error marking all notifications as read:', err)
        // Revert optimistic update if it failed
        setOptimisticallyReadNotifications(prev => {
          const newSet = new Set(prev)
          notificationIds.forEach(id => newSet.delete(id))
          return newSet
        })
        loadNotifications()
      })
  }

  const handleApprove = async (requestId: string, comment: string = '') => {
    // Immediately dismiss the request from UI
    const requestToProcess = availabilityRequests.find(r => r.id === requestId)
    setAvailabilityRequests(prev => prev.filter(r => r.id !== requestId))

    // Run approval in background
    approveAvailabilityRequest(requestId, comment)
      .then(() => {
        loadNotifications()
        // Immediately refresh schedule to show approved locked shifts
        window.dispatchEvent(new CustomEvent('scheduleUpdate'))
      })
      .catch((err) => {
        console.error('Error approving request:', err)
        alert('Error approving request. Please try again.')
        // Re-add the request if it failed
        if (requestToProcess) {
          setAvailabilityRequests(prev => [...prev, requestToProcess])
        }
      })
  }

  const handleReject = async (requestId: string, comment: string = '') => {
    // Immediately dismiss the request from UI
    const requestToProcess = availabilityRequests.find(r => r.id === requestId)
    setAvailabilityRequests(prev => prev.filter(r => r.id !== requestId))

    // Run rejection in background
    rejectAvailabilityRequest(requestId, comment)
      .then(() => {
        loadNotifications()
      })
      .catch((err) => {
        console.error('Error rejecting request:', err)
        alert('Error rejecting request. Please try again.')
        // Re-add the request if it failed
        if (requestToProcess) {
          setAvailabilityRequests(prev => [...prev, requestToProcess])
        }
      })
  }

  const getNotificationIcon = (type: string) => {
    switch (type) {
      case 'availability_approved':
        return <Check className="w-4 h-4 text-green-600" />
      case 'availability_rejected':
        return <XCircle className="w-4 h-4 text-red-600" />
      default:
        return <Bell className="w-4 h-4 text-blue-600" />
    }
  }

  const regularNotifications = notifications.filter(n => n.type !== 'availability_request')
  const totalCount = regularNotifications.filter(n => !n.read).length + availabilityRequests.length

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 rounded hover:bg-blue-800 transition-colors"
      >
        <Bell className="w-5 h-5" />
        {totalCount > 0 && (
          <span className="absolute top-0 right-0 bg-red-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">
            {totalCount}
          </span>
        )}
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setIsOpen(false)}
          />
          <div className="fixed top-16 right-2 left-2 sm:absolute sm:left-auto sm:right-0 sm:top-12 sm:w-96 bg-white rounded-lg shadow-xl border z-50 max-h-[80vh] overflow-y-auto">
            <div className="p-4 border-b flex justify-between items-center">
              <h3 className="font-semibold">Notifications</h3>
              <div className="flex gap-2">
                {!isManager && unreadCount > 0 && (
                  <button
                    onClick={handleMarkAllAsRead}
                    className="text-xs text-blue-600 hover:text-blue-800"
                  >
                    Mark all read
                  </button>
                )}
                <button
                  onClick={() => setIsOpen(false)}
                  className="text-gray-500 hover:text-gray-700"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>
            
            {/* Availability Requests Section - Managers Only */}
            {isManager && availabilityRequests.length > 0 && (
              <div className="border-b">
                <div className="p-3 bg-orange-50">
                  <h4 className="font-semibold text-sm text-orange-800">Pending Availability Requests</h4>
                </div>
                <div className="divide-y">
                  {availabilityRequests.map((request) => (
                    <div key={request.id} className="p-3">
                      <div className="flex items-start gap-2 mb-2">
                        <User className="w-4 h-4 text-gray-500 mt-0.5" />
                        <div className="flex-1">
                          <p className="text-sm font-medium text-gray-900">{request.employee_name || 'Employee'}</p>
                          <p className="text-xs text-gray-600">
                            {request.request_type === 'availability' ? 'Availability Request' : 'Time Off Request'}
                          </p>
                          <div className="text-xs text-gray-600 mt-1 space-y-1">
                            {request.start_date && request.end_date && (
                              <p><strong>Date:</strong> {request.start_date} to {request.end_date}</p>
                            )}
                            {request.days_of_week && request.days_of_week.length > 0 && (
                              <p><strong>Days:</strong> {Array.isArray(request.days_of_week) ? request.days_of_week.join(', ') : request.days_of_week}</p>
                            )}
                            {request.start_time && request.end_time && (
                              <p><strong>Time:</strong> {request.start_time} - {request.end_time}</p>
                            )}
                            {request.employee_comment && (
                              <p><strong>Comment:</strong> "{request.employee_comment}"</p>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleApprove(request.id)}
                          className="flex-1 bg-green-600 text-white text-xs py-2 px-3 rounded hover:bg-green-700 min-h-[44px]"
                        >
                          Approve
                        </button>
                        <button
                          onClick={() => handleReject(request.id)}
                          className="flex-1 bg-red-600 text-white text-xs py-2 px-3 rounded hover:bg-red-700 min-h-[44px]"
                        >
                          Reject
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Regular Notifications */}
            {regularNotifications.length === 0 && availabilityRequests.length === 0 ? (
              <div className="p-4 text-gray-500 text-sm">No notifications</div>
            ) : (
              <div className="divide-y">
                {regularNotifications.map((notification) => (
                  <div
                    key={notification.id}
                    className={`p-4 hover:bg-gray-50 cursor-pointer ${!notification.read ? 'bg-blue-50' : ''}`}
                    onClick={() => !notification.read && handleMarkAsRead(notification.id)}
                  >
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5">
                        {getNotificationIcon(notification.type)}
                      </div>
                      <div className="flex-1">
                        <p className="text-sm text-gray-800">{notification.message}</p>
                        {notification.details && (
                          <div className="text-xs text-gray-600 mt-1 space-y-1">
                            {notification.details.request_type && (
                              <p><strong>Type:</strong> {notification.details.request_type}</p>
                            )}
                            {notification.details.start_date && notification.details.end_date && (
                              <p><strong>Date:</strong> {notification.details.start_date} to {notification.details.end_date}</p>
                            )}
                            {notification.details.days_of_week && notification.details.days_of_week !== 'All days' && (
                              <p><strong>Days:</strong> {notification.details.days_of_week}</p>
                            )}
                            {notification.details.time_range && notification.details.time_range !== 'All day' && (
                              <p><strong>Time:</strong> {notification.details.time_range}</p>
                            )}
                            {notification.details.employee_comment && (
                              <p><strong>Comment:</strong> "{notification.details.employee_comment}"</p>
                            )}
                          </div>
                        )}
                        <p className="text-xs text-gray-500 mt-1">
                          {new Date(notification.created_at).toLocaleString()}
                        </p>
                      </div>
                      {!notification.read && (
                        <div className="w-2 h-2 bg-blue-600 rounded-full mt-2" />
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
