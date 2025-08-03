"use client";

import { useState, useEffect } from "react";
import { useAuth } from "../../contexts/AuthContext";
import { cirisClient } from "../../lib/ciris-sdk";
import type { OAuthProvider, AgentInfo } from "../../lib/ciris-sdk";
import { detectDeploymentMode, getApiBaseUrl, getApiUrl } from "../../lib/api-utils";
import LogoIcon from "../../components/ui/floating/LogoIcon";
import CButton from "components/ui/Buttons";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [selectedAgent, setSelectedAgent] = useState("datum");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [loadingAgents, setLoadingAgents] = useState(true);
  const { login } = useAuth();
  
  // Always show Google and Discord OAuth options
  const oauthProviders = [
    { provider: "google", name: "Google" },
    { provider: "discord", name: "Discord" }
  ];

  // Load agents by detecting deployment mode dynamically
  useEffect(() => {
    const loadAgents = async () => {
      // Try CIRISManager first to detect managed mode
      try {
        console.log('Checking for CIRISManager...');
        const response = await fetch('/manager/v1/agents');
        if (response.ok) {
          // CIRISManager is available - we're in managed mode
          console.log('CIRISManager detected - using managed mode');
          const data = await response.json();
          console.log('Loaded agents:', data.agents);
          
          // Convert manager API response to AgentInfo format
          const agentsList: AgentInfo[] = data.agents.map((agent: any) => ({
            agent_id: agent.agent_id,
            agent_name: agent.agent_name,
            status: agent.status,
            health: agent.health,
            api_url: agent.api_endpoint || `http://localhost:${agent.api_port}`,
            api_port: parseInt(agent.api_port) || 8080,
            api_endpoint: agent.api_endpoint || `http://localhost:${agent.api_port}`,
            container_name: agent.container_name,
            created_at: agent.created_at,
            update_available: false,
          }));
          
          setAgents(agentsList);
          if (agentsList.length > 0) {
            // Select the first healthy agent by default
            const healthyAgent = agentsList.find(a => a.health === 'healthy') || agentsList[0];
            setSelectedAgent(healthyAgent.agent_id);
          }
          setLoadingAgents(false); // Important: set loading to false!
          return; // Exit early for managed mode
        }
      } catch (error) {
        console.log('CIRISManager not available, trying standalone mode');
      }
      
      // CIRISManager not available - try standalone mode
        // In standalone mode, fetch real agent identity from API
        try {
          // Configure SDK for standalone mode
          cirisClient.setConfig({ baseURL: window.location.origin });
          
          // Fetch real identity from the API
          const identity = await cirisClient.agent.getIdentity();
          
          // Create agent info from real identity
          const realAgent: AgentInfo = {
            agent_id: identity.agent_id,
            agent_name: identity.name,  // Real name from API!
            container_name: 'standalone',
            status: 'running',
            api_endpoint: window.location.origin,
            created_at: new Date().toISOString(),
            update_available: false
          };
          
          setAgents([realAgent]);
          setSelectedAgent(realAgent.agent_id);
        } catch (error) {
          console.error('Failed to fetch agent identity:', error);
          setError(error instanceof Error ? error : new Error('Failed to fetch agent identity'));
          // Fail fast - don't create fake data
          setAgents([]);
        } finally {
          setLoadingAgents(false);
        }
      
      // Try standalone API
      try {
        console.log('Trying standalone mode...');
        // Configure SDK for standalone mode
        cirisClient.setConfig({ baseURL: window.location.origin });
        
        // Fetch real identity from the API
        const identity = await cirisClient.agent.getIdentity();
        
        // Create agent info from real identity
        const realAgent: AgentInfo = {
          agent_id: identity.agent_id,
          agent_name: identity.name,  // Real name from API!
          container_name: 'standalone',
          status: 'running',
          api_endpoint: window.location.origin,
          created_at: new Date().toISOString(),
          update_available: false
        };
        
        setAgents([realAgent]);
        setSelectedAgent(realAgent.agent_id);
        console.log('Standalone mode successful');
      } catch (error) {
        console.error('Neither CIRISManager nor standalone API available:', error);
        setError(error instanceof Error ? error : new Error('No CIRIS infrastructure available'));
        setAgents([]);
      } finally {
        setLoadingAgents(false);
      }
    };
    loadAgents();
  }, []);

  // Update client baseURL when agent selection changes
  useEffect(() => {
    const agent = agents.find(a => a.agent_id === selectedAgent);
    if (agent) {
      // Determine base URL based on available infrastructure
      let baseURL;
      
      // Check if we have multiple agents (managed mode) or single agent (standalone)
      if (agents.length > 1 || agent.container_name !== 'standalone') {
        // Managed mode: use agent-specific API path
        baseURL = `${window.location.origin}/api/${agent.agent_id}`;
      } else {
        // Standalone mode: direct API access
        baseURL = window.location.origin;
      }
      
      cirisClient.setConfig({ baseURL });
      
      // Store selected agent for use after login
      localStorage.setItem('selectedAgentId', agent.agent_id);
      localStorage.setItem('selectedAgentName', agent.agent_name);
    }
  }, [selectedAgent, agents]);

  const handleOAuthLogin = async (provider: string) => {
    try {
      const agent = agents.find(a => a.agent_id === selectedAgent);
      if (!agent) return;
      
      let oauthUrl;
      let redirectUri;
      
      // Determine OAuth URLs based on deployment mode
      if (agents.length > 1 || agent.container_name !== 'standalone') {
        // Managed mode: use agent-specific paths
        redirectUri = encodeURIComponent(`${window.location.origin}/oauth/${selectedAgent}/callback`);
        oauthUrl = `${window.location.origin}/api/${agent.agent_id}/auth/oauth/${provider}/login`;
      } else {
        // Standalone mode: direct OAuth
        redirectUri = encodeURIComponent(`${window.location.origin}/oauth/callback`);
        oauthUrl = `${window.location.origin}/v1/auth/oauth/${provider}/login`;
      }
      
      window.location.href = `${oauthUrl}?redirect_uri=${redirectUri}`;
    } catch (error) {
      console.error("OAuth login error:", error);
    }
  };

  const getProviderIcon = (provider: string) => {
    switch (provider.toLowerCase()) {
      case "google":
        return (
          <svg className="w-5 h-5" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
        );
      case "discord":
        return (
          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="#5865F2">
            <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515a.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0a12.64 12.64 0 0 0-.617-1.25a.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057a19.9 19.9 0 0 0 5.993 3.03a.078.078 0 0 0 .084-.028a14.09 14.09 0 0 0 1.226-1.994a.076.076 0 0 0-.041-.106a13.107 13.107 0 0 1-1.872-.892a.077.077 0 0 1-.008-.128a10.2 10.2 0 0 0 .372-.292a.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127a12.299 12.299 0 0 1-1.873.892a.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028a19.839 19.839 0 0 0 6.002-3.03a.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419c0-1.333.956-2.419 2.157-2.419c1.21 0 2.176 1.096 2.157 2.42c0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419c0-1.333.955-2.419 2.157-2.419c1.21 0 2.176 1.096 2.157 2.42c0 1.333-.946 2.418-2.157 2.418z"/>
          </svg>
        );
      default:
        return "🔑";
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(username, password);
    } catch (error) {
      // Error is handled in AuthContext
    } finally {
      setLoading(false);
    }
  };

  const handleManagerGoogleLogin = async () => {
    try {
      // Redirect to Manager OAuth endpoint through nginx proxy
      const redirectUri = encodeURIComponent(`${window.location.origin}/manager/callback`);
      // Always use the nginx proxy path
      const managerUrl = `${window.location.origin}/manager/v1/oauth/login`;
      window.location.href = `${managerUrl}?redirect_uri=${redirectUri}`;
    } catch (error) {
      console.error("Manager OAuth login error:", error);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-md w-full space-y-8">
        <div>
          <LogoIcon className="mx-auto h-12 w-auto text-brand-primary fill-brand-primary" />
          <h2 className="mt-6 text-center text-3xl text-brand-primary font-extrabold">
            Sign in to CIRIS
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            Select an agent and enter your credentials
          </p>
          {error && (
            <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-md">
              <p className="text-sm text-red-600">{error.message}</p>
            </div>
          )}
        </div>
        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          <input type="hidden" name="remember" value="true" />
          
          {/* Agent Selector */}
          <div>
            <label htmlFor="agent" className="block text-sm font-medium text-gray-700">
              Select Agent
            </label>
            <select
              id="agent"
              name="agent"
              className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md"
              value={selectedAgent}
              onChange={(e) => setSelectedAgent(e.target.value)}
              disabled={loading || loadingAgents}
            >
              {loadingAgents ? (
                <option>Loading agents...</option>
              ) : agents.length === 0 ? (
                <option>No agents available</option>
              ) : (
                agents.map((agent) => (
                  <option key={agent.agent_id} value={agent.agent_id}>
                    {agent.agent_name} ({agent.status})
                  </option>
                ))
              )}
            </select>
            <p className="mt-1 text-xs text-gray-500">
              Each agent has separate authentication. You'll need to login individually to each agent.
            </p>
          </div>

          <div className="rounded-md shadow-sm -space-y-px">
            <div>
              <label htmlFor="username" className="sr-only">
                Username
              </label>
              <input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                required
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-t-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 focus:z-10 sm:text-sm"
                placeholder="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={loading}
              />
            </div>
            <div>
              <label htmlFor="password" className="sr-only">
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-b-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 focus:z-10 sm:text-sm"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading}
              />
            </div>
          </div>

          <div className="flex items-center justify-center mt-6">
            <button
              type="submit"
              disabled={loading || agents.length === 0}
              className="focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed bg-brand-primary transition-all hover:bg-black cursor-pointer text-white border px-12 py-4 rounded-sm"
            >
              {loading ? "Signing in..." : agents.length === 0 ? "No agents available" : "Sign in"}
            </button>
          </div>

          {/* OAuth Login Options */}
          <div className="mt-6">
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-300" />
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-2 bg-gray-50 text-gray-500">
                  Or continue with
                </span>
              </div>
            </div>

            <div className="mt-6 grid grid-cols-2 gap-3">
              {oauthProviders.map((provider) => (
                <button
                  key={provider.provider}
                  type="button"
                  onClick={() => handleOAuthLogin(provider.provider)}
                  disabled={agents.length === 0}
                  className="w-full inline-flex justify-center items-center py-2.5 px-4 border border-gray-300 rounded-md shadow-sm bg-white text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
                  <span className="mr-2">
                    {getProviderIcon(provider.provider)}
                  </span>
                  {provider.name}
                </button>
              ))}
            </div>
          </div>

          {/* Manager Access Section - Contextually aware */}
          <div className="mt-8 pt-8 border-t border-gray-200">
            <div className="text-center">
              <p className="text-sm text-gray-600 mb-4">
                System administrators with @ciris.ai accounts
              </p>
              <button
                type="button"
                onClick={handleManagerGoogleLogin}
                className="inline-flex items-center px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-all duration-200 group"
              >
                <svg className="w-4 h-4 mr-2 opacity-70 group-hover:opacity-100 transition-opacity" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                </svg>
                Manager Access
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}