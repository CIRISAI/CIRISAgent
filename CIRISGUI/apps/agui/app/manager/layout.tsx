'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import LogoIcon from '../../components/ui/floating/LogoIcon';
import { Button } from '@/components/ui/button';
import { LogOut } from 'lucide-react';

interface ManagerLayoutProps {
  children: React.ReactNode;
}

export default function ManagerLayout({ children }: ManagerLayoutProps) {
  const router = useRouter();

  const handleLogout = () => {
    // Clear manager token
    localStorage.removeItem('managerToken');
    router.push('/login');
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Manager Navigation Bar */}
      <nav className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center">
              <Link href="/manager" className="flex items-center">
                <LogoIcon className="h-8 w-8 text-brand-primary fill-brand-primary" />
                <span className="ml-2 text-xl font-semibold">CIRIS Manager</span>
              </Link>
            </div>
            
            <div className="flex items-center space-x-4">
              <Link 
                href="/manager" 
                className="text-gray-700 hover:text-gray-900 px-3 py-2 rounded-md text-sm font-medium"
              >
                Manager Dashboard
              </Link>
              <Link 
                href="/" 
                className="text-gray-700 hover:text-gray-900 px-3 py-2 rounded-md text-sm font-medium"
              >
                Agent Interface
              </Link>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleLogout}
                className="ml-4"
              >
                <LogOut className="h-4 w-4 mr-2" />
                Logout
              </Button>
            </div>
          </div>
        </div>
      </nav>

      {/* Page Content */}
      <main className="flex-1">
        {children}
      </main>
    </div>
  );
}