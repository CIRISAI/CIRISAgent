import { CreateAgentRequest, AgentInfo, ManagerStatus, TemplateInfo, PortInfo, DeleteAgentResponse, HealthResponse, ManagerClientConfig } from './types';
export declare class CIRISManagerClient {
    private client;
    constructor(config: ManagerClientConfig);
    private handleError;
    /**
     * Check health of the manager service
     */
    health(): Promise<HealthResponse>;
    /**
     * Get manager status
     */
    status(): Promise<ManagerStatus>;
    /**
     * List all managed agents
     */
    listAgents(): Promise<AgentInfo[]>;
    /**
     * Get specific agent by name
     */
    getAgent(name: string): Promise<AgentInfo>;
    /**
     * Create a new agent
     */
    createAgent(request: CreateAgentRequest): Promise<AgentInfo>;
    /**
     * Delete an agent
     */
    deleteAgent(agentId: string): Promise<DeleteAgentResponse>;
    /**
     * List available templates
     */
    listTemplates(): Promise<TemplateInfo>;
    /**
     * Get allocated ports information
     */
    getAllocatedPorts(): Promise<PortInfo>;
}
//# sourceMappingURL=client.d.ts.map