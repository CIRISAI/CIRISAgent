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
    // Use relative URL to go through nginx proxy
    const response = await fetch('/manager/v1/agents');
    if (!response.ok) {
      throw new Error(`Failed to fetch agents: ${response.status}`);
    }
    const data = await response.json();
    // Extract agents array from response
    return data.agents || data;
  }

  /**
   * Get detailed information about a specific agent
   */
  async getAgent(agentId: string): Promise<AgentInfo> {
    return this.transport.get<AgentInfo>(`/manager/v1/agents/${agentId}`);
  }

  /**
   * Create a new CIRIS agent with WA authorization
   * Requires: Local authentication and valid WA signature
   */
  async createAgent(data: AgentCreationRequest): Promise<AgentInfo> {
    return this.transport.post<AgentInfo>('/manager/v1/agents', data);
  }

  /**
   * Notify an agent that an update is available
   * Requires: Local authentication
   */
  async notifyUpdate(agentId: string, notification: UpdateNotification): Promise<{ status: string; message: string }> {
    return this.transport.post<{ status: string; message: string }>(
      `/manager/v1/agents/${agentId}/notify-update`,
      notification
    );
  }

  /**
   * Get the deployment status for an agent
   */
  async getDeploymentStatus(agentId: string): Promise<DeploymentStatus> {
    return this.transport.get<DeploymentStatus>(`/manager/v1/deployments/${agentId}/status`);
  }

  /**
   * Health check endpoint for CIRISManager
   */
  async health(): Promise<ManagerHealth> {
    return this.transport.get<ManagerHealth>('/manager/v1/health');
  }
}