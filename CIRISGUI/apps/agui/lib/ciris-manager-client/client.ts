import axios, { AxiosInstance, AxiosError } from 'axios';
import {
  CreateAgentRequest,
  AgentInfo,
  AgentListResponse,
  ManagerStatus,
  TemplateInfo,
  PortInfo,
  DeleteAgentResponse,
  HealthResponse,
  ManagerClientConfig
} from './types';

export class CIRISManagerClient {
  private client: AxiosInstance;

  constructor(config: ManagerClientConfig) {
    this.client = axios.create({
      baseURL: config.baseURL,
      timeout: config.timeout || 30000,
      headers: {
        'Content-Type': 'application/json',
        ...config.headers
      }
    });

    // Add response interceptor for error handling
    this.client.interceptors.response.use(
      response => response,
      this.handleError
    );
  }

  private handleError(error: AxiosError): Promise<never> {
    if (error.response) {
      // Server responded with error status
      const message = (error.response.data as any)?.detail || error.message;
      throw new Error(`Manager API Error ${error.response.status}: ${message}`);
    } else if (error.request) {
      // Request made but no response
      throw new Error('No response from Manager API');
    } else {
      // Request setup error
      throw new Error(`Request error: ${error.message}`);
    }
  }

  /**
   * Check health of the manager service
   */
  async health(): Promise<HealthResponse> {
    const response = await this.client.get<HealthResponse>('/health');
    return response.data;
  }

  /**
   * Get manager status
   */
  async status(): Promise<ManagerStatus> {
    const response = await this.client.get<ManagerStatus>('/status');
    return response.data;
  }

  /**
   * List all managed agents
   */
  async listAgents(): Promise<AgentInfo[]> {
    const response = await this.client.get<AgentListResponse>('/agents');
    return response.data.agents;
  }

  /**
   * Get specific agent by name
   */
  async getAgent(name: string): Promise<AgentInfo> {
    const response = await this.client.get<AgentInfo>(`/agents/${name}`);
    return response.data;
  }

  /**
   * Create a new agent
   */
  async createAgent(request: CreateAgentRequest): Promise<AgentInfo> {
    const response = await this.client.post<AgentInfo>('/agents', request);
    return response.data;
  }

  /**
   * Delete an agent
   */
  async deleteAgent(agentId: string): Promise<DeleteAgentResponse> {
    const response = await this.client.delete<DeleteAgentResponse>(`/agents/${agentId}`);
    return response.data;
  }

  /**
   * List available templates
   */
  async listTemplates(): Promise<TemplateInfo> {
    const response = await this.client.get<TemplateInfo>('/templates');
    return response.data;
  }

  /**
   * Get allocated ports information
   */
  async getAllocatedPorts(): Promise<PortInfo> {
    const response = await this.client.get<PortInfo>('/ports/allocated');
    return response.data;
  }
}