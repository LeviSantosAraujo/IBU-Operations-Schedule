import React, { Component, ErrorInfo, ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
  errorInfo: ErrorInfo | null
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null, errorInfo: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ error, errorInfo })
    
    // Log to console
    console.error('[React Error Boundary]', error, errorInfo)
    
    // Log to backend
    this.logErrorToBackend(error, errorInfo)
  }

  async logErrorToBackend(error: Error, errorInfo: ErrorInfo) {
    try {
      const API_URL = import.meta.env.VITE_API_URL || ''
      const errorData = {
        type: 'react_error',
        message: error.message,
        stack: error.stack,
        componentStack: errorInfo.componentStack,
        timestamp: new Date().toISOString(),
        userAgent: navigator.userAgent
      }
      
      await fetch(`${API_URL}/api/log-error`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(errorData)
      })
    } catch (e) {
      console.error('Failed to log React error to backend:', e)
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-gray-100 flex items-center justify-center p-4">
          <div className="bg-white rounded-lg shadow-lg p-8 max-w-lg w-full">
            <h1 className="text-2xl font-bold text-red-600 mb-4">Something went wrong</h1>
            <p className="text-gray-600 mb-4">
              An unexpected error occurred. The error has been logged and will be reviewed.
            </p>
            <details className="mb-4">
              <summary className="cursor-pointer text-sm font-medium text-gray-700 mb-2">
                Error details
              </summary>
              <pre className="bg-gray-100 p-4 rounded text-xs overflow-auto max-h-40">
                {this.state.error?.toString()}
                {this.state.errorInfo?.componentStack}
              </pre>
            </details>
            <button
              onClick={() => window.location.reload()}
              className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
            >
              Reload Page
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
