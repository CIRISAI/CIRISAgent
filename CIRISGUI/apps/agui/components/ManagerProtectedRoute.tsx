'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '../contexts/AuthContext';

interface ManagerProtectedRouteProps {
  children: React.ReactNode;
}

export function ManagerProtectedRoute({ children }: ManagerProtectedRouteProps) {
  const { isManagerAuthenticated, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !isManagerAuthenticated()) {
      router.push('/login');
    }
  }, [loading, isManagerAuthenticated, router]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-lg">Loading...</div>
      </div>
    );
  }

  if (!isManagerAuthenticated()) {
    return null;
  }

  return <>{children}</>;
}