'use client';

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import toast from 'react-hot-toast';
import { cirisClient, User } from '../lib/ciris-sdk';

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hasPermission: (permission: string) => boolean;
  hasRole: (role: string) => boolean;
  setUser: (user: User | null) => void;
  setToken: (token: string) => void;
  managerToken: string | null;
  setManagerToken: (token: string | null) => void;
  isManagerAuthenticated: () => boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [managerToken, setManagerToken] = useState<string | null>(null);
  const router = useRouter();

  // Check auth status on mount
  useEffect(() => {
    // Skip auth check on login page and manager pages
    const pathname = window.location.pathname;
    if (pathname === '/login' || pathname.startsWith('/manager')) {
      setLoading(false);
    } else {
      checkAuth();
    }
    // Also check for manager token
    const savedManagerToken = localStorage.getItem('manager_token');
    if (savedManagerToken) {
      setManagerToken(savedManagerToken);
    }
  }, []);

  const checkAuth = async () => {
    try {
      if (cirisClient.isAuthenticated()) {
        const currentUser = await cirisClient.auth.getMe();
        setUser(currentUser);
      }
    } catch (error) {
      console.error('Auth check failed:', error);
    } finally {
      setLoading(false);
    }
  };

  const login = useCallback(async (username: string, password: string) => {
    try {
      const user = await cirisClient.login(username, password);
      setUser(user);
      toast.success(`Welcome, ${user.username || user.user_id}!`);
      router.push('/');
    } catch (error: any) {
      toast.error(error.message || 'Login failed');
      throw error;
    }
  }, [router]);

  const logout = useCallback(async () => {
    try {
      await cirisClient.logout();
      setUser(null);
      toast.success('Logged out successfully');
      router.push('/login');
    } catch (error) {
      console.error('Logout failed:', error);
      toast.error('Logout failed');
    }
  }, [router]);

  const hasPermission = useCallback((permission: string) => {
    if (!user) return false;
    return user.permissions.includes(permission) || user.role === 'SYSTEM_ADMIN';
  }, [user]);

  const hasRole = useCallback((role: string) => {
    if (!user) return false;
    const roleHierarchy = ['OBSERVER', 'ADMIN', 'AUTHORITY', 'SYSTEM_ADMIN'];
    const userRoleIndex = roleHierarchy.indexOf(user.role);
    const requiredRoleIndex = roleHierarchy.indexOf(role);
    return userRoleIndex >= requiredRoleIndex;
  }, [user]);

  const setToken = useCallback((token: string) => {
    cirisClient.setConfig({ authToken: token });
  }, []);

  const isManagerAuthenticated = useCallback(() => {
    return !!managerToken;
  }, [managerToken]);

  return (
    <AuthContext.Provider value={{ 
      user, 
      loading, 
      login, 
      logout, 
      hasPermission, 
      hasRole, 
      setUser, 
      setToken,
      managerToken,
      setManagerToken,
      isManagerAuthenticated
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}