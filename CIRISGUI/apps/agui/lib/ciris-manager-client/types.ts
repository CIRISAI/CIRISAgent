/**
 * Type definitions for CIRIS Manager API
 */

export interface CreateAgentRequest {
  template: string;
  name: string;
  environment?: Record<string, string>;
  wa_signature?: string;
}

export interface AgentInfo {
  agent_id: string;
  name: string;
  container: string;
  port: number;
  api_endpoint: string;
  template: string;
  status: string;
  created_at?: string;
  compose_file?: string;
}

export interface AgentListResponse {
  agents: AgentInfo[];
}

export interface ManagerStatus {
  status: string;
  version: string;
  components: Record<string, string>;
}

export interface TemplateInfo {
  templates: Record<string, string>;
  pre_approved: string[];
}

export interface PortInfo {
  allocated: Record<string, number>;
  reserved: number[];
  range: {
    start: number;
    end: number;
  };
}

export interface DeleteAgentResponse {
  status: string;
  agent_id: string;
  message: string;
}

export interface HealthResponse {
  status: string;
  service: string;
}

export interface ManagerClientConfig {
  baseURL: string;
  timeout?: number;
  headers?: Record<string, string>;
}