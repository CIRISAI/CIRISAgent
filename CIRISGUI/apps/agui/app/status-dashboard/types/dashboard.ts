// Dashboard type definitions

export interface DashboardData {
  health: SystemHealth;
  cost: CostMetrics;
  resources: ResourceUsage;
  adapters: AdapterInfo[];
  channels: ChannelInfo[];
  services: ServiceHealth[];
  incidents: Incident[];
  metrics: MetricsData;
}

export interface SystemHealth {
  status: 'healthy' | 'degraded' | 'critical' | 'initializing';
  version: string;
  uptime: number;
  cognitiveState?: string;
  initializationComplete: boolean;
}

export interface CostMetrics {
  lastHourCents: number;
  last24HoursCents: number;
  budgetCents?: number;
  projectedDailyCents?: number;
}

export interface ResourceUsage {
  cpu: {
    current: number;
    limit: number;
    trend: 'up' | 'down' | 'stable';
  };
  memory: {
    current: number;
    limit: number;
    used: number;
    available: number;
  };
  disk: {
    used: number;
    total: number;
    percentage: number;
  };
  healthStatus: 'healthy' | 'warning' | 'critical';
  warnings: string[];
}

export interface AdapterInfo {
  adapterId: string;
  adapterType: string;
  isRunning: boolean;
  messagesProcessed: number;
  errorsCount: number;
  uptimeSeconds: number;
  lastError?: string;
  tools?: string[];
}

export interface ChannelInfo {
  channelId: string;
  channelType: 'discord' | 'api' | 'cli' | 'system';
  name: string;
  isActive: boolean;
  lastActivity?: string;
  userCount?: number;
}

export interface ServiceHealth {
  name: string;
  status: 'healthy' | 'degraded' | 'unavailable';
  circuitBreakerState: 'closed' | 'open' | 'half-open';
  available: number;
  healthy: number;
  lastError?: string;
  lastErrorTime?: string;
}

export interface Incident {
  id: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  status: 'active' | 'resolved' | 'investigating';
  description: string;
  timestamp: string;
  affectedServices?: string[];
}

export interface MetricsData {
  messagesPerMinute: TimeSeriesData[];
  responseTime: TimeSeriesData[];
  errorRate: TimeSeriesData[];
  activeUsers: number;
  totalRequests24h: number;
}

export interface TimeSeriesData {
  timestamp: number;
  value: number;
}

export interface WebSocketMessage {
  type: 'telemetry' | 'status' | 'incident' | 'metrics';
  data: any;
  timestamp: string;
}
