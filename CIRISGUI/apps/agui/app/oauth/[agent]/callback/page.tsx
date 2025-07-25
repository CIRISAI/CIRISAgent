'use client';

import { useEffect, useState, Suspense } from 'react';
import { useSearchParams, useRouter, useParams } from 'next/navigation';
import { useAuth } from '../../../../contexts/AuthContext';
import { cirisClient } from '../../../../lib/ciris-sdk';
import { AGENTS } from '../../../../config/agents';

function OAuthCallbackContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const params = useParams();
  const { setUser, setToken } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [processing, setProcessing] = useState(true);

  useEffect(() => {
    handleOAuthCallback();
  }, [searchParams, params]);

  const handleOAuthCallback = async () => {
    const code = searchParams.get('code');
    const state = searchParams.get('state');
    const error = searchParams.get('error');
    const errorDescription = searchParams.get('error_description');
    const agentId = params.agent as string;
    
    // Check if we have direct token parameters (from API redirect)
    const accessToken = searchParams.get('access_token');
    const tokenType = searchParams.get('token_type');
    const role = searchParams.get('role');
    const userId = searchParams.get('user_id');

    if (error) {
      setError(`OAuth error: ${error} - ${errorDescription || 'Unknown error'}`);
      setProcessing(false);
      return;
    }

    // Handle direct token response from API
    if (accessToken && tokenType && role && userId) {
      try {
        // Set the authentication state directly
        const user = {
          user_id: userId,
          username: userId,
          role: role as any, // Role comes as string from query params
          api_role: role as any, // For the required api_role field
          wa_role: undefined, // OAuth users don't have WA role initially
          permissions: [],
          created_at: new Date().toISOString(),
          last_login: new Date().toISOString()
        };
        
        setToken(accessToken);
        setUser(user);
        
        // Store the selected agent for future use
        const agent = AGENTS.find(a => a.id === agentId);
        if (agent) {
          localStorage.setItem('selectedAgentId', agent.id);
          localStorage.setItem('selectedAgentName', agent.name);
        }
        
        // Redirect to dashboard
        router.push('/dashboard');
        return;
      } catch (err) {
        setError(err instanceof Error ? err.message : 'OAuth authentication failed');
        setProcessing(false);
        return;
      }
    }

    // Original OAuth code flow (if needed in future)
    if (!code || !state) {
      setError('Missing OAuth callback parameters');
      setProcessing(false);
      return;
    }

    // Find the agent configuration
    const agent = AGENTS.find(a => a.id === agentId);
    if (!agent) {
      setError(`Invalid agent: ${agentId}`);
      setProcessing(false);
      return;
    }

    try {
      // Update the SDK to use the correct agent URL
      const baseURL = process.env.NODE_ENV === 'development' 
        ? process.env.NEXT_PUBLIC_CIRIS_API_URL || 'http://localhost:8080'
        : agent.apiUrl;
      
      cirisClient.setConfig({ baseURL });

      // Extract provider from state (we'll encode it in the state parameter)
      const provider = state.split(':')[0];
      
      const user = await cirisClient.auth.handleOAuthCallback(provider, code, state);
      
      // Set the authentication state
      setUser(user);
      
      // Store the selected agent for future use
      localStorage.setItem('selectedAgentId', agent.id);
      localStorage.setItem('selectedAgentName', agent.name);
      
      // Redirect to dashboard
      router.push('/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'OAuth authentication failed');
      setProcessing(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center">
          <h2 className="mt-6 text-3xl font-extrabold text-gray-900">
            OAuth Authentication
          </h2>
          
          {processing ? (
            <div className="mt-8">
              <div className="inline-flex items-center">
                <svg className="animate-spin h-8 w-8 mr-3 text-indigo-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span className="text-lg text-gray-600">Processing authentication...</span>
              </div>
            </div>
          ) : error ? (
            <div className="mt-8">
              <div className="bg-red-50 border border-red-200 rounded-md p-4">
                <p className="text-sm text-red-600">{error}</p>
              </div>
              <button
                onClick={() => router.push('/login')}
                className="mt-4 inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700"
              >
                Back to Login
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export default function OAuthCallbackPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <h2 className="text-3xl font-extrabold text-gray-900">Loading...</h2>
        </div>
      </div>
    }>
      <OAuthCallbackContent />
    </Suspense>
  );
}