import { BaseResource } from './base';

// Response interfaces
export interface AgentInfo {
  agent_id: string;
  agent_name: string;
  container_name: string;
  status: string;
  health?: string;
  api_endpoint?: string;
  created_at: string;
  started_at?: string;
  exit_code?: number;
  update_available: boolean;
}

export interface AgentCreationRequest {
  agent_name: string;
  agent_type?: string;
  adapters?: string[];
  environment?: Record<string, string>;
  wa_signature?: string;
}

export interface UpdateNotification {
  agent_id: string;
  new_version: string;
  changelog?: string;
  urgency?: 'low' | 'normal' | 'high' | 'critical';
}

export interface DeploymentStatus {
  agent_id: string;
  status: string;
  message: string;
  staged_container?: string;
  consent_status?: string;
}

export interface ManagerHealth {
  status: 'healthy' | 'unhealthy';
  service: string;
  docker?: {
    connected: boolean;
    version: string;
    containers: number;
    running: number;
  };
  error?: string;
}

export class ManagerResource extends BaseResource {
  /**
   * List all CIRIS agents managed by CIRISManager
   */
  async listAgents(): Promise<AgentInfo[]> {
    // Manager API always goes through the nginx proxy, not the agent endpoint
    // We need to use the origin URL to ensure it goes through the right path
    const managerUrl = typeof window !== 'undefined' 
      ? `${window.location.origin}/manager/v1/agents`
      : '/manager/v1/agents';
    
    const response = await this.transport.request<{ agents: AgentInfo[] }>('GET', managerUrl);
    // Extract agents array from response
    return response.agents || [];
  }

  /**
   * Get detailed information about a specific agent
   */
  async getAgent(agentId: string): Promise<AgentInfo> {
    const managerUrl = typeof window !== 'undefined' 
      ? `${window.location.origin}/manager/v1/agents/${agentId}`
      : `/manager/v1/agents/${agentId}`;
    return this.transport.request<AgentInfo>('GET', managerUrl);
  }

  /**
   * Create a new CIRIS agent with WA authorization
   * Requires: Local authentication and valid WA signature
   */
  async createAgent(data: AgentCreationRequest): Promise<AgentInfo> {
    const managerUrl = typeof window !== 'undefined' 
      ? `${window.location.origin}/manager/v1/agents`
      : '/manager/v1/agents';
    return this.transport.request<AgentInfo>('POST', managerUrl, { body: data });
  }

  /**
   * Notify an agent that an update is available
   * Requires: Local authentication
   */
  async notifyUpdate(agentId: string, notification: UpdateNotification): Promise<{ status: string; message: string }> {
    const managerUrl = typeof window !== 'undefined' 
      ? `${window.location.origin}/manager/v1/agents/${agentId}/notify-update`
      : `/manager/v1/agents/${agentId}/notify-update`;
    return this.transport.request<{ status: string; message: string }>('POST', managerUrl, { body: notification });
  }

  /**
   * Get the deployment status for an agent
   */
  async getDeploymentStatus(agentId: string): Promise<DeploymentStatus> {
    const managerUrl = typeof window !== 'undefined' 
      ? `${window.location.origin}/manager/v1/deployments/${agentId}/status`
      : `/manager/v1/deployments/${agentId}/status`;
    return this.transport.request<DeploymentStatus>('GET', managerUrl);
  }

  /**
   * Health check endpoint for CIRISManager
   */
  async health(): Promise<ManagerHealth> {
    const managerUrl = typeof window !== 'undefined' 
      ? `${window.location.origin}/manager/v1/health`
      : '/manager/v1/health';
    return this.transport.request<ManagerHealth>('GET', managerUrl);
  }
}