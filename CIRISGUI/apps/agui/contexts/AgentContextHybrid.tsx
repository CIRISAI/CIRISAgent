'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useAuth } from './AuthContext';
import { cirisClient } from '../lib/ciris-sdk';
import { AgentInfo } from '../lib/ciris-sdk/resources/manager';
import type { APIRole, WARole } from '../lib/ciris-sdk';
import { usePathname } from 'next/navigation';
import { sdkConfigManager } from '../lib/sdk-config-manager';
import { AuthStore } from '../lib/ciris-sdk/auth-store';

interface AgentRole {
  agentId: string;
  apiRole: APIRole;
  waRole?: WARole;
  isAuthority: boolean;
  lastChecked: Date;
}

interface AgentContextType {
  agents: AgentInfo[];
  currentAgent: AgentInfo | null;
  currentAgentRole: AgentRole | null;
  agentRoles: Map<string, AgentRole>;
  selectAgent: (agentId: string) => Promise<void>;
  refreshAgents: () => Promise<void>;
  refreshAgentRoles: () => Promise<void>;
  isLoadingAgents: boolean;
  isLoadingRoles: boolean;
  error: Error | null;
  isManagerAvailable: boolean;
}

const AgentContext = createContext<AgentContextType | null>(null);

// Default local dev agent when manager is not available
const DEFAULT_LOCAL_AGENT: AgentInfo = {
  agent_id: 'datum',
  agent_name: 'Datum (Local Dev)',
  status: 'running',
  health: 'healthy',
  api_url: process.env.NEXT_PUBLIC_CIRIS_API_URL || 'http://localhost',
  api_port: 8080,
  api_endpoint: process.env.NEXT_PUBLIC_CIRIS_API_URL || 'http://localhost:8080',
  container_name: 'ciris-agent-datum',
  created_at: new Date().toISOString(),
  started_at: new Date().toISOString(),
  update_available: false,
};

export function AgentProvider({ children }: { children: ReactNode }) {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [currentAgent, setCurrentAgent] = useState<AgentInfo | null>(null);
  const [agentRoles, setAgentRoles] = useState<Map<string, AgentRole>>(new Map());
  const [isLoadingAgents, setIsLoadingAgents] = useState(false);
  const [isLoadingRoles, setIsLoadingRoles] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [isManagerAvailable, setIsManagerAvailable] = useState(false);
  const { user } = useAuth();
  const pathname = usePathname();

  // Discover agents from CIRISManager or fallback to local
  const refreshAgents = async () => {
    setIsLoadingAgents(true);
    setError(null);
    
    try {
      // Try to fetch from manager first
      const discovered = await cirisClient.manager.listAgents();
      setAgents(discovered);
      setIsManagerAvailable(true);
      
      // If no current agent selected, select first running agent
      if (!currentAgent && discovered.length > 0) {
        const runningAgent = discovered.find(a => a.status === 'running') || discovered[0];
        await selectAgent(runningAgent.agent_id);
      }
    } catch (err) {
      // Manager not available, use default local agent
      console.log('CIRIS Manager not available, using local dev agent');
      setAgents([DEFAULT_LOCAL_AGENT]);
      setIsManagerAvailable(false);
      
      // Auto-select the default agent
      if (!currentAgent) {
        await selectAgent(DEFAULT_LOCAL_AGENT.agent_id);
      }
      
      // Only set error if it's not a connection error (which is expected)
      if (err instanceof Error && !err.message.includes('fetch') && !err.message.includes('Failed to fetch')) {
        setError(err);
      }
    } finally {
      setIsLoadingAgents(false);
    }
  };

  // Fetch roles for all agents
  const refreshAgentRoles = async () => {
    if (!user) return;
    
    setIsLoadingRoles(true);
    const newRoles = new Map<string, AgentRole>();
    
    // Get the auth token once, to use for all agents
    const authToken = AuthStore.getAccessToken() || undefined;
    
    for (const agent of agents) {
      try {
        // Use SDK config manager for each agent
        sdkConfigManager.configure(agent.agent_id, authToken);
        
        // Get current user info for this agent
        const userInfo = await cirisClient.auth.getCurrentUser();
        
        if (userInfo) {
          newRoles.set(agent.agent_id, {
            agentId: agent.agent_id,
            apiRole: userInfo.api_role,
            waRole: userInfo.wa_role,
            isAuthority: userInfo.wa_role === 'AUTHORITY' || userInfo.api_role === 'SYSTEM_ADMIN',
            lastChecked: new Date()
          });
        } else {
          throw new Error('No user info returned');
        }
      } catch (error) {
        console.error(`Failed to fetch role for agent ${agent.agent_id}:`, error);
        // Set a default role on error
        newRoles.set(agent.agent_id, {
          agentId: agent.agent_id,
          apiRole: 'OBSERVER' as APIRole,
          isAuthority: false,
          lastChecked: new Date()
        });
      }
    }
    
    // Restore SDK config to current agent
    if (currentAgent && authToken) {
      sdkConfigManager.configure(currentAgent.agent_id, authToken);
    }
    
    setAgentRoles(newRoles);
    setIsLoadingRoles(false);
  };

  // Select an agent
  const selectAgent = async (agentId: string) => {
    const agent = agents.find(a => a.agent_id === agentId);
    if (!agent) return;
    
    console.log('[AgentContext] Selecting agent:', agentId);
    setCurrentAgent(agent);
    
    // Use SDK config manager to properly configure the SDK
    // This handles OAuth tokens and proper URL configuration
    const authToken = AuthStore.getAccessToken() || undefined;
    sdkConfigManager.configure(agentId, authToken);
    
    // Store selection
    localStorage.setItem('selectedAgentId', agentId);
    localStorage.setItem('selectedAgentName', agent.agent_name);
    
    // Store API endpoint for this agent if in standalone mode
    if (!isManagerAvailable) {
      localStorage.setItem(`agent_${agentId}_api_url`, `${agent.api_url}:${agent.api_port}`);
    }
  };

  // Get current agent role
  const currentAgentRole = currentAgent ? agentRoles.get(currentAgent.agent_id) || null : null;

  // Initial load - restore SDK configuration first
  useEffect(() => {
    // Check if we have a stored auth token and restore SDK config
    const authToken = AuthStore.getAccessToken();
    const savedAgentId = localStorage.getItem('selectedAgentId');
    
    if (authToken && savedAgentId) {
      console.log('[AgentContext] Restoring SDK config for agent:', savedAgentId);
      sdkConfigManager.configure(savedAgentId, authToken);
    }
    
    refreshAgents();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Refresh roles when agents or user changes
  useEffect(() => {
    if (agents.length > 0 && user) {
      refreshAgentRoles();
    }
  }, [agents, user]); // eslint-disable-line react-hooks/exhaustive-deps

  // Detect agent from URL path or restore previous selection
  useEffect(() => {
    if (agents.length === 0 || currentAgent) return;
    
    // Check if we're on an agent-specific path like /agent/{agent_id}/...
    const pathMatch = pathname.match(/^\/agent\/([^\/]+)/);
    if (pathMatch && pathMatch[1]) {
      const agentIdFromUrl = pathMatch[1];
      const agentFromUrl = agents.find(a => a.agent_id === agentIdFromUrl);
      if (agentFromUrl) {
        selectAgent(agentIdFromUrl);
        return;
      }
    }
    
    // Fall back to saved selection
    const savedAgentId = localStorage.getItem('selectedAgentId');
    if (savedAgentId) {
      selectAgent(savedAgentId);
    }
  }, [agents, pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  const value: AgentContextType = {
    agents,
    currentAgent,
    currentAgentRole,
    agentRoles,
    selectAgent,
    refreshAgents,
    refreshAgentRoles,
    isLoadingAgents,
    isLoadingRoles,
    error,
    isManagerAvailable,
  };

  return <AgentContext.Provider value={value}>{children}</AgentContext.Provider>;
}

export function useAgent() {
  const context = useContext(AgentContext);
  if (!context) {
    throw new Error('useAgent must be used within an AgentProvider');
  }
  return context;
}