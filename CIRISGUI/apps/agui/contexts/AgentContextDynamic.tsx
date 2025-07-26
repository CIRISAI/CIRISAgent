'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useAuth } from './AuthContext';
import { cirisClient } from '../lib/ciris-sdk';
import { AgentInfo } from '../lib/ciris-sdk/resources/manager';
import type { APIRole, WARole } from '../lib/ciris-sdk';

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
}

const AgentContext = createContext<AgentContextType | null>(null);

export function AgentProvider({ children }: { children: ReactNode }) {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [currentAgent, setCurrentAgent] = useState<AgentInfo | null>(null);
  const [agentRoles, setAgentRoles] = useState<Map<string, AgentRole>>(new Map());
  const [isLoadingAgents, setIsLoadingAgents] = useState(false);
  const [isLoadingRoles, setIsLoadingRoles] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const { user } = useAuth();

  // Discover agents from CIRISManager
  const refreshAgents = async () => {
    setIsLoadingAgents(true);
    setError(null);
    
    try {
      const discovered = await cirisClient.manager.listAgents();
      setAgents(discovered);
      
      // If no current agent selected, select first running agent
      if (!currentAgent && discovered.length > 0) {
        const runningAgent = discovered.find(a => a.status === 'running');
        if (runningAgent) {
          setCurrentAgent(runningAgent);
        }
      }
    } catch (err) {
      console.error('Failed to discover agents:', err);
      setError(err instanceof Error ? err : new Error('Failed to discover agents'));
      // Don't create fallback agents - let the UI handle the "no agents" case
    } finally {
      setIsLoadingAgents(false);
    }
  };

  // Load agent roles when user logs in
  const refreshAgentRoles = async () => {
    if (!user) return;
    
    setIsLoadingRoles(true);
    const newRoles = new Map<string, AgentRole>();
    
    for (const agent of agents) {
      if (agent.api_endpoint && agent.status === 'running') {
        try {
          // Create client for specific agent
          const agentClient = cirisClient.withConfig({
            baseURL: agent.api_endpoint
          });
          
          const currentUser = await agentClient.auth.getCurrentUser();
          
          if (currentUser) {
            newRoles.set(agent.agent_id, {
              agentId: agent.agent_id,
              apiRole: currentUser.api_role || currentUser.role,
              waRole: currentUser.wa_role,
              isAuthority: currentUser.wa_role === 'AUTHORITY',
              lastChecked: new Date()
            });
          }
        } catch (error) {
          console.error(`Failed to get role for agent ${agent.agent_id}:`, error);
        }
      }
    }
    
    setAgentRoles(newRoles);
    setIsLoadingRoles(false);
  };

  const selectAgent = async (agentId: string) => {
    const agent = agents.find(a => a.agent_id === agentId);
    if (!agent) {
      throw new Error(`Agent ${agentId} not found`);
    }
    
    setCurrentAgent(agent);
    
    // Update SDK to use multi-agent routing pattern
    // For production, use /api/{agent}/v1 pattern
    // For local development, use the agent's direct endpoint
    const isProduction = window.location.hostname === 'agents.ciris.ai';
    const baseURL = isProduction 
      ? `${window.location.origin}/api/${agentId}`
      : agent.api_endpoint;
    
    cirisClient.setConfig({ baseURL });
  };

  // Initial discovery
  useEffect(() => {
    refreshAgents();
  }, []);

  // Refresh roles when agents change or user logs in
  useEffect(() => {
    if (user && agents.length > 0) {
      refreshAgentRoles();
    }
  }, [user, agents]);

  // Auto-refresh agents every 30 seconds
  useEffect(() => {
    const interval = setInterval(refreshAgents, 30000);
    return () => clearInterval(interval);
  }, []);

  const currentAgentRole = currentAgent 
    ? agentRoles.get(currentAgent.agent_id) || null
    : null;

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
    error
  };

  return (
    <AgentContext.Provider value={value}>
      {children}
    </AgentContext.Provider>
  );
}

export function useAgent() {
  const context = useContext(AgentContext);
  if (!context) {
    throw new Error('useAgent must be used within AgentProvider');
  }
  return context;
}