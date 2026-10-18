import { createContext, useContext, type ReactNode } from 'react'

export interface AuthUser {
  id: string
  email: string
  role: 'admin' | 'recruiter' | 'viewer'
  status: 'active' | 'invited'
  created_at: string
  updated_at: string
}

export function isAdminRole(role?: string): boolean {
  return role === 'admin'
}

export function isPrivilegedRole(role?: string): boolean {
  return role === 'admin' || role === 'recruiter'
}

export function isViewerRole(role?: string): boolean {
  return role === 'viewer'
}

export interface AuthContextType {
  user: AuthUser | null
  loading: boolean
  isAdmin: boolean
  isPrivileged: boolean
  isViewer: boolean
  setUser: (user: AuthUser | null) => void
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  isAdmin: false,
  isPrivileged: false,
  isViewer: false,
  setUser: () => {},
  logout: async () => {},
})

export function useAuth(): AuthContextType {
  return useContext(AuthContext)
}

interface AuthProviderProps {
  value: AuthContextType
  children: ReactNode
}

export function AuthProvider({ value, children }: AuthProviderProps) {
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
