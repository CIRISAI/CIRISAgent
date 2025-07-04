// CIRIS TypeScript SDK - Memory Resource

import { BaseResource } from './base';
import { GraphNode, MemoryOpResult } from '../types';

export interface MemoryStats {
  total_nodes: number;
  nodes_by_type: Record<string, number>;
  nodes_by_scope: Record<string, number>;
  oldest_memory?: string;
  newest_memory?: string;
}

export interface MemoryQueryOptions {
  type?: string;
  scope?: string;
  limit?: number;
  offset?: number;
  order_by?: 'created_at' | 'updated_at' | 'relevance';
  order?: 'asc' | 'desc';
}

export class MemoryResource extends BaseResource {
  /**
   * Query memory nodes
   */
  async query(
    query: string,
    options: MemoryQueryOptions = {}
  ): Promise<GraphNode[]> {
    // If query looks like a node ID, search by ID
    const isNodeId = query && (
      query.startsWith('metric_') || 
      query.startsWith('audit_') || 
      query.startsWith('log_') ||
      query.startsWith('dream_schedule_') ||
      query.includes('_') && /\d{10}/.test(query)
    );
    
    const body: any = {
      ...(isNodeId ? { node_id: query } : { query }),
      ...options
    };
    
    return this.transport.post<GraphNode[]>('/v1/memory/query', body);
  }

  /**
   * Get a specific memory node
   */
  async getNode(nodeId: string): Promise<GraphNode> {
    return this.transport.get<GraphNode>(`/v1/memory/${nodeId}`);
  }

  /**
   * Recall specific memory by ID (alternative to getNode)
   */
  async recall(nodeId: string): Promise<GraphNode> {
    return this.transport.get<GraphNode>(`/v1/memory/recall/${nodeId}`);
  }

  /**
   * Create a new memory node
   */
  async createNode(node: Omit<GraphNode, 'id' | 'version' | 'updated_at'>): Promise<MemoryOpResult> {
    return this.transport.post<MemoryOpResult>('/v1/memory/store', node);
  }

  /**
   * Update a memory node
   */
  async updateNode(
    nodeId: string,
    updates: Partial<GraphNode>
  ): Promise<MemoryOpResult> {
    return this.transport.patch<MemoryOpResult>(`/v1/memory/${nodeId}`, updates);
  }

  /**
   * Delete a memory node
   */
  async deleteNode(nodeId: string): Promise<MemoryOpResult> {
    return this.transport.delete<MemoryOpResult>(`/v1/memory/${nodeId}`);
  }

  /**
   * Get memory statistics
   */
  async getStats(): Promise<MemoryStats> {
    // Memory stats are part of the query response
    const result = await this.transport.post<{
      results: GraphNode[];
      stats: MemoryStats;
    }>('/v1/memory/query', {
      query: '',
      include_stats: true
    });
    return result.stats || {
      total_nodes: 0,
      nodes_by_type: {},
      nodes_by_scope: {},
      oldest_memory: undefined,
      newest_memory: undefined
    };
  }

  /**
   * Search memories by semantic similarity
   */
  async search(
    query: string,
    options: {
      limit?: number;
      threshold?: number;
      scope?: string;
    } = {}
  ): Promise<GraphNode[]> {
    const result = await this.transport.post<{
      results: GraphNode[];
      stats?: MemoryStats;
    }>('/v1/memory/query', {
      query,
      ...options
    });
    return result.results || [];
  }

  /**
   * Get memory timeline
   */
  async getTimeline(options: {
    start_time?: string;
    end_time?: string;
    bucket_size?: '1h' | '1d' | '1w' | '1m';
    scope?: string;
  } = {}): Promise<{
    memories: GraphNode[];
    buckets: Record<string, number>;
    total: number;
  }> {
    return this.transport.get('/v1/memory/timeline', { params: options });
  }

  /**
   * Get related memories
   */
  async getRelated(
    nodeId: string,
    options: {
      limit?: number;
      relationship_type?: string;
    } = {}
  ): Promise<GraphNode[]> {
    return this.transport.get<GraphNode[]>(`/v1/memory/${nodeId}/related`, {
      params: options
    });
  }

  /**
   * Get memory graph visualization as SVG
   */
  async getVisualization(options: {
    node_type?: string;
    scope?: 'local' | 'identity' | 'environment' | 'community';
    hours?: number;
    layout?: 'force' | 'timeline' | 'hierarchical';
    width?: number;
    height?: number;
    limit?: number;
  } = {}): Promise<string> {
    // This returns SVG as text
    const response = await this.transport.get('/v1/memory/visualize/graph', {
      params: options,
      responseType: 'text'
    });
    return response as unknown as string;
  }
}