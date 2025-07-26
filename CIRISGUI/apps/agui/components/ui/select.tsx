import * as React from "react"

interface SelectContextValue {
  value?: string
  onValueChange?: (value: string) => void
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

const SelectContext = React.createContext<SelectContextValue>({})

export const Select = ({ children, value, onValueChange, disabled }: {
  children: React.ReactNode
  value?: string
  onValueChange?: (value: string) => void
  disabled?: boolean
}) => {
  const [open, setOpen] = React.useState(false)
  
  return (
    <SelectContext.Provider value={{ value, onValueChange, open, onOpenChange: setOpen }}>
      <div className="relative">
        {children}
      </div>
    </SelectContext.Provider>
  )
}

export const SelectTrigger = ({ children, className = "" }: {
  children: React.ReactNode
  className?: string
}) => {
  const { open, onOpenChange } = React.useContext(SelectContext)
  
  return (
    <button
      type="button"
      onClick={() => onOpenChange?.(!open)}
      className={`flex h-10 w-full items-center justify-between rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${className}`}
    >
      {children}
      <svg className="h-4 w-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
      </svg>
    </button>
  )
}

export const SelectValue = ({ placeholder }: { placeholder?: string }) => {
  const { value } = React.useContext(SelectContext)
  return <span>{value || placeholder || "Select..."}</span>
}

export const SelectContent = ({ children }: { children: React.ReactNode }) => {
  const { open } = React.useContext(SelectContext)
  
  if (!open) return null
  
  return (
    <div className="absolute z-50 mt-1 w-full rounded-md border border-gray-300 bg-white shadow-lg">
      <div className="py-1">{children}</div>
    </div>
  )
}

export const SelectItem = ({ value, children }: {
  value: string
  children: React.ReactNode
}) => {
  const { onValueChange, onOpenChange } = React.useContext(SelectContext)
  
  return (
    <div
      className="cursor-pointer px-3 py-2 text-sm hover:bg-gray-100"
      onClick={() => {
        onValueChange?.(value)
        onOpenChange?.(false)
      }}
    >
      {children}
    </div>
  )
}