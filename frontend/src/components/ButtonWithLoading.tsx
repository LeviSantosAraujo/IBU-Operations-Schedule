import React from 'react'
import { Loader2 } from 'lucide-react'

interface ButtonWithLoadingProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  isLoading: boolean
  children: React.ReactNode
}

export const ButtonWithLoading: React.FC<ButtonWithLoadingProps> = ({ 
  isLoading, 
  children, 
  disabled, 
  ...props 
}) => {
  return (
    <button
      {...props}
      disabled={disabled || isLoading}
      className={`${props.className || ''} flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed`}
    >
      {isLoading && <Loader2 className="w-4 h-4 animate-spin" />}
      {children}
    </button>
  )
}
