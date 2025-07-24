"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.CIRISManagerClient = void 0;
const axios_1 = __importDefault(require("axios"));
class CIRISManagerClient {
    constructor(config) {
        this.client = axios_1.default.create({
            baseURL: config.baseURL,
            timeout: config.timeout || 30000,
            headers: {
                'Content-Type': 'application/json',
                ...config.headers
            }
        });
        // Add response interceptor for error handling
        this.client.interceptors.response.use(response => response, this.handleError);
    }
    handleError(error) {
        if (error.response) {
            // Server responded with error status
            const message = error.response.data?.detail || error.message;
            throw new Error(`Manager API Error ${error.response.status}: ${message}`);
        }
        else if (error.request) {
            // Request made but no response
            throw new Error('No response from Manager API');
        }
        else {
            // Request setup error
            throw new Error(`Request error: ${error.message}`);
        }
    }
    /**
     * Check health of the manager service
     */
    async health() {
        const response = await this.client.get('/manager/v1/health');
        return response.data;
    }
    /**
     * Get manager status
     */
    async status() {
        const response = await this.client.get('/manager/v1/status');
        return response.data;
    }
    /**
     * List all managed agents
     */
    async listAgents() {
        const response = await this.client.get('/manager/v1/agents');
        return response.data.agents;
    }
    /**
     * Get specific agent by name
     */
    async getAgent(name) {
        const response = await this.client.get(`/manager/v1/agents/${name}`);
        return response.data;
    }
    /**
     * Create a new agent
     */
    async createAgent(request) {
        const response = await this.client.post('/manager/v1/agents', request);
        return response.data;
    }
    /**
     * Delete an agent
     */
    async deleteAgent(agentId) {
        const response = await this.client.delete(`/manager/v1/agents/${agentId}`);
        return response.data;
    }
    /**
     * List available templates
     */
    async listTemplates() {
        const response = await this.client.get('/manager/v1/templates');
        return response.data;
    }
    /**
     * Get allocated ports information
     */
    async getAllocatedPorts() {
        const response = await this.client.get('/manager/v1/ports/allocated');
        return response.data;
    }
}
exports.CIRISManagerClient = CIRISManagerClient;
//# sourceMappingURL=client.js.map