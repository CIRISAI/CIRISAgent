import * as React from "react"

export interface AlertProps {
  children?: React.ReactNode
  variant?: 'default' | 'destructive'
  className?: string
}

export const Alert = ({ children, variant = 'default', className = '' }: AlertProps) => {
  const variants = {
    default: 'bg-blue-50 text-blue-900 border-blue-200',
    destructive: 'bg-red-50 text-red-900 border-red-200'
  }
  
  return (
    <div className={`relative w-full rounded-lg border p-4 ${variants[variant]} ${className}`}>
      {children}
    </div>
  )
}

export const AlertDescription = ({ children }: { children: React.ReactNode }) => (
  <div className="text-sm">{children}</div>
)