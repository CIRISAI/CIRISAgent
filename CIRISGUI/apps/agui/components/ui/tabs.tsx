import * as React from "react"

interface TabsContextValue {
  value: string
  onValueChange: (value: string) => void
}

const TabsContext = React.createContext<TabsContextValue | undefined>(undefined)

export const Tabs = ({ children, defaultValue, className = "" }: {
  children: React.ReactNode
  defaultValue: string
  className?: string
}) => {
  const [value, setValue] = React.useState(defaultValue)
  
  return (
    <TabsContext.Provider value={{ value, onValueChange: setValue }}>
      <div className={className}>
        {children}
      </div>
    </TabsContext.Provider>
  )
}

export const TabsList = ({ children, className = "" }: {
  children: React.ReactNode
  className?: string
}) => (
  <div className={`inline-flex h-10 items-center justify-center rounded-md bg-gray-100 p-1 text-gray-600 ${className}`}>
    {children}
  </div>
)

export const TabsTrigger = ({ value, children, className = "" }: {
  value: string
  children: React.ReactNode
  className?: string
}) => {
  const context = React.useContext(TabsContext)
  if (!context) throw new Error("TabsTrigger must be used within Tabs")
  
  const isActive = context.value === value
  
  return (
    <button
      className={`inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium transition-all ${
        isActive ? 'bg-white text-gray-900 shadow-sm' : 'hover:bg-gray-200'
      } ${className}`}
      onClick={() => context.onValueChange(value)}
    >
      {children}
    </button>
  )
}

export const TabsContent = ({ value, children, className = "" }: {
  value: string
  children: React.ReactNode
  className?: string
}) => {
  const context = React.useContext(TabsContext)
  if (!context) throw new Error("TabsContent must be used within Tabs")
  
  if (context.value !== value) return null
  
  return (
    <div className={`mt-2 ${className}`}>
      {children}
    </div>
  )
}