'use client';

import { useQuery } from '@tanstack/react-query';
import { cirisClient } from '../../lib/ciris-sdk';
import { ProtectedRoute } from '../../components/ProtectedRoute';
import { StatusDot, SpinnerIcon, InfoIcon, ClockIcon, MemoryIcon } from '../../components/Icons';

export default function DashboardPage() {
  // Fetch all necessary data
  const { data: health } = useQuery({
    queryKey: ['dashboard-health'],
    queryFn: () => cirisClient.system.getHealth(),
    refetchInterval: 5000,
  });

  const { data: resources } = useQuery({
    queryKey: ['dashboard-resources'],
    queryFn: () => cirisClient.system.getResources(),
    refetchInterval: 5000,
  });
  
  // Cast resources to the actual API response structure
  const resourceData = resources as any;

  const { data: services } = useQuery({
    queryKey: ['dashboard-services'],
    queryFn: () => cirisClient.system.getServices(),
    refetchInterval: 10000,
  });

  const { data: agentStatus } = useQuery({
    queryKey: ['dashboard-agent'],
    queryFn: () => cirisClient.agent.getStatus(),
    refetchInterval: 5000,
  });

  const { data: memoryStats } = useQuery({
    queryKey: ['dashboard-memory'],
    queryFn: () => cirisClient.memory.getStats(),
    refetchInterval: 30000,
  });

  const { data: telemetryOverview } = useQuery({
    queryKey: ['dashboard-telemetry'],
    queryFn: () => cirisClient.telemetry.getOverview(),
    refetchInterval: 30000,
  });

  const { data: recentLogs } = useQuery({
    queryKey: ['dashboard-logs'],
    queryFn: () => cirisClient.telemetry.getLogs('ERROR', undefined, 5),
    refetchInterval: 10000,
  });

  const { data: runtimeStatus } = useQuery({
    queryKey: ['dashboard-runtime'],
    queryFn: () => cirisClient.system.getRuntimeStatus(),
    refetchInterval: 5000,
  });

  const { data: queueStatus } = useQuery({
    queryKey: ['dashboard-queue'],
    queryFn: () => cirisClient.system.getProcessingQueueStatus(),
    refetchInterval: 5000,
  });

  // Helper functions
  const formatUptime = (seconds: number) => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${days}d ${hours}h ${minutes}m`;
  };

  const getHealthColor = (status: string) => {
    switch (status) {
      case 'healthy': return 'green';
      case 'degraded': return 'yellow';
      case 'unhealthy': return 'red';
      default: return 'gray';
    }
  };

  // The SDK already unwraps the data, so services IS the data object
  const serviceStats = {
    healthy: services?.services?.filter((s: any) => s.healthy === true).length || 0,
    degraded: services?.services?.filter((s: any) => s.healthy === false && s.available === true).length || 0,
    unhealthy: services?.services?.filter((s: any) => s.available === false).length || 0,
    total: services?.total_services || 0,
  };

  return (
    <ProtectedRoute>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">CIRIS System Dashboard</h1>
          <p className="mt-2 text-lg text-gray-600">
            Real-time monitoring of all system components
          </p>
        </div>

        {/* Key Metrics */}
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4 mb-8">
          {/* System Health */}
          <div className="bg-white overflow-hidden shadow rounded-lg">
            <div className="p-5">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <StatusDot 
                    status={getHealthColor(health?.status || 'gray')} 
                    className="h-8 w-8" 
                  />
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">
                      System Health
                    </dt>
                    <dd className="text-lg font-semibold text-gray-900">
                      {health?.status?.toUpperCase() || 'UNKNOWN'}
                    </dd>
                  </dl>
                </div>
              </div>
            </div>
          </div>

          {/* Agent State */}
          <div className="bg-white overflow-hidden shadow rounded-lg">
            <div className="p-5">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <div className="p-3 bg-indigo-100 rounded-lg">
                    <InfoIcon className="text-indigo-600" size="lg" />
                  </div>
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">
                      Agent State
                    </dt>
                    <dd className="text-lg font-semibold text-gray-900">
                      {agentStatus?.cognitive_state || 'UNKNOWN'}
                    </dd>
                  </dl>
                </div>
              </div>
            </div>
          </div>

          {/* Uptime */}
          <div className="bg-white overflow-hidden shadow rounded-lg">
            <div className="p-5">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <div className="p-3 bg-green-100 rounded-lg">
                    <ClockIcon className="text-green-600" size="lg" />
                  </div>
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">
                      Uptime
                    </dt>
                    <dd className="text-lg font-semibold text-gray-900">
                      {health?.uptime_seconds ? formatUptime(health.uptime_seconds) : 'N/A'}
                    </dd>
                  </dl>
                </div>
              </div>
            </div>
          </div>

          {/* Memory Nodes */}
          <div className="bg-white overflow-hidden shadow rounded-lg">
            <div className="p-5">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <div className="p-3 bg-purple-100 rounded-lg">
                    <MemoryIcon className="text-purple-600" size="lg" />
                  </div>
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">
                      Memory Nodes
                    </dt>
                    <dd className="text-lg font-semibold text-gray-900">
                      {memoryStats?.total_nodes?.toLocaleString() || '0'}
                    </dd>
                  </dl>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Resource Usage */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 mb-8">
          <div className="bg-white shadow rounded-lg">
            <div className="px-4 py-5 sm:p-6">
              <h3 className="text-lg font-medium text-gray-900 mb-4">
                Current Resource Usage
              </h3>
              <div className="space-y-4">
                {/* CPU Usage */}
                <div>
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-sm font-medium text-gray-700">CPU Usage</span>
                    <span className={`text-sm font-bold ${
                      (resourceData?.current_usage?.cpu_percent || 0) > 80 ? 'text-red-600' : 
                      (resourceData?.current_usage?.cpu_percent || 0) > 60 ? 'text-yellow-600' : 'text-green-600'
                    }`}>
                      {resourceData?.current_usage?.cpu_percent?.toFixed(1) || 0}%
                    </span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className={`h-2 rounded-full transition-all duration-300 ${
                        (resourceData?.current_usage?.cpu_percent || 0) > 80 ? 'bg-red-500' : 
                        (resourceData?.current_usage?.cpu_percent || 0) > 60 ? 'bg-yellow-500' : 'bg-green-500'
                      }`}
                      style={{ width: `${resourceData?.current_usage?.cpu_percent || 0}%` }}
                    />
                  </div>
                </div>

                {/* Memory Usage */}
                <div>
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-sm font-medium text-gray-700">Memory Usage</span>
                    <span className={`text-sm font-bold ${
                      (resourceData?.current_usage?.memory_percent || 0) > 80 ? 'text-red-600' : 
                      (resourceData?.current_usage?.memory_percent || 0) > 60 ? 'text-yellow-600' : 'text-green-600'
                    }`}>
                      {resourceData?.current_usage?.memory_mb || 0} MB ({resourceData?.current_usage?.memory_percent?.toFixed(1) || 0}%)
                    </span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className={`h-2 rounded-full transition-all duration-300 ${
                        (resourceData?.current_usage?.memory_percent || 0) > 80 ? 'bg-red-500' : 
                        (resourceData?.current_usage?.memory_percent || 0) > 60 ? 'bg-yellow-500' : 'bg-green-500'
                      }`}
                      style={{ width: `${resourceData?.current_usage?.memory_percent || 0}%` }}
                    />
                  </div>
                </div>

                {/* Disk Usage */}
                <div className="flex justify-between items-center">
                  <span className="text-sm font-medium text-gray-700">Disk Usage</span>
                  <span className="text-sm font-bold text-gray-900">
                    {resourceData?.current_usage?.disk_used_mb ? `${(resourceData.current_usage.disk_used_mb / 1024).toFixed(1)} GB` : 'N/A'}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Environmental Impact */}
          <div className="bg-white shadow rounded-lg">
            <div className="px-4 py-5 sm:p-6">
              <h3 className="text-lg font-medium text-gray-900 mb-4">Environmental Impact</h3>
              <div className="grid grid-cols-3 gap-4">
                <div className="text-center">
                  <div className="text-2xl font-bold text-green-700">
                    {telemetryOverview?.carbon_per_hour_grams ? (telemetryOverview.carbon_per_hour_grams * 24 / 1000).toFixed(3) : '0.000'}
                  </div>
                  <div className="text-xs text-gray-600 mt-1">kg CO₂ (24h)</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-blue-700">
                    {telemetryOverview?.tokens_per_hour ? telemetryOverview.tokens_per_hour.toLocaleString() : '0'}
                  </div>
                  <div className="text-xs text-gray-600 mt-1">Tokens/hour</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-purple-700">
                    ${telemetryOverview?.cost_per_hour_cents ? (telemetryOverview.cost_per_hour_cents * 24 / 100).toFixed(2) : '0.00'}
                  </div>
                  <div className="text-xs text-gray-600 mt-1">Cost (24h)</div>
                </div>
              </div>
              <div className="mt-4 pt-4 border-t grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-gray-600">Hourly Rate:</span>
                  <span className="ml-2 font-medium">${telemetryOverview?.cost_per_hour_cents ? (telemetryOverview.cost_per_hour_cents / 100).toFixed(4) : '0.00'}/hr</span>
                </div>
                <div>
                  <span className="text-gray-600">Carbon Rate:</span>
                  <span className="ml-2 font-medium">{telemetryOverview?.carbon_per_hour_grams?.toFixed(1) || '0.0'}g/hr</span>
                </div>
              </div>
            </div>
          </div>

          {/* Service Health Summary */}
          <div className="bg-white shadow rounded-lg">
            <div className="px-4 py-5 sm:p-6">
              <h3 className="text-lg font-medium text-gray-900 mb-4">
                Service Health Distribution
              </h3>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <StatusDot status="green" className="h-5 w-5" />
                    <span className="ml-2 text-sm font-medium text-gray-700">Healthy Services</span>
                  </div>
                  <span className="text-lg font-semibold text-green-600">{serviceStats.healthy}</span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <StatusDot status="yellow" className="h-5 w-5" />
                    <span className="ml-2 text-sm font-medium text-gray-700">Degraded Services</span>
                  </div>
                  <span className="text-lg font-semibold text-yellow-600">{serviceStats.degraded}</span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <StatusDot status="red" className="h-5 w-5" />
                    <span className="ml-2 text-sm font-medium text-gray-700">Unhealthy Services</span>
                  </div>
                  <span className="text-lg font-semibold text-red-600">{serviceStats.unhealthy}</span>
                </div>
                <div className="pt-2 mt-2 border-t border-gray-200">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-gray-700">Total Services</span>
                    <span className="text-lg font-semibold text-gray-900">{serviceStats.total}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Runtime & Queue Status */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3 mb-8">
          <div className="bg-white shadow rounded-lg">
            <div className="px-4 py-5 sm:p-6">
              <h3 className="text-lg font-medium text-gray-900 mb-4">Runtime Status</h3>
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">Runtime State</span>
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    runtimeStatus?.is_paused 
                      ? 'bg-yellow-100 text-yellow-800' 
                      : 'bg-green-100 text-green-800'
                  }`}>
                    {runtimeStatus?.is_paused ? 'PAUSED' : 'RUNNING'}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white shadow rounded-lg">
            <div className="px-4 py-5 sm:p-6">
              <h3 className="text-lg font-medium text-gray-900 mb-4">Processing Queue</h3>
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">Queue Size</span>
                  <span className="text-lg font-semibold">
                    {queueStatus?.queue_size || 0}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">Max Size</span>
                  <span className="text-sm font-medium">
                    {queueStatus?.max_size || 'N/A'}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white shadow rounded-lg">
            <div className="px-4 py-5 sm:p-6">
              <h3 className="text-lg font-medium text-gray-900 mb-4">Telemetry</h3>
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">Total Metrics</span>
                  <span className="text-lg font-semibold">
                    {telemetryOverview?.total_metrics?.toLocaleString() || '0'}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">Active Services</span>
                  <span className="text-sm font-medium">
                    {telemetryOverview?.active_services || 0}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Recent Error Logs */}
        {recentLogs && recentLogs.length > 0 && (
          <div className="bg-white shadow rounded-lg">
            <div className="px-4 py-5 sm:p-6">
              <h3 className="text-lg font-medium text-gray-900 mb-4">Recent Errors</h3>
              <div className="space-y-2">
                {recentLogs.map((log: any, index: number) => (
                  <div key={index} className="flex items-start space-x-3 p-3 bg-red-50 rounded-lg">
                    <div className="flex-shrink-0">
                      <StatusDot status="red" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-red-900">
                        {log.service} - {log.level}
                      </p>
                      <p className="text-sm text-red-700 truncate">
                        {log.message}
                      </p>
                      <p className="text-xs text-red-600 mt-1">
                        {new Date(log.timestamp).toLocaleString()}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Quick Actions */}
        <div className="mt-8 bg-blue-50 rounded-lg p-6">
          <h3 className="text-lg font-medium text-blue-900 mb-4">Quick Links</h3>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <a href="/api-demo" className="text-center p-4 bg-white rounded-lg shadow hover:shadow-md transition-shadow">
              <div className="text-2xl mb-2">🚀</div>
              <div className="text-sm font-medium text-gray-900">API Explorer</div>
            </a>
            <a href="/system" className="text-center p-4 bg-white rounded-lg shadow hover:shadow-md transition-shadow">
              <div className="text-2xl mb-2">⚙️</div>
              <div className="text-sm font-medium text-gray-900">System Status</div>
            </a>
            <a href="/memory" className="text-center p-4 bg-white rounded-lg shadow hover:shadow-md transition-shadow">
              <div className="text-2xl mb-2">🧠</div>
              <div className="text-sm font-medium text-gray-900">Memory Graph</div>
            </a>
            <a href="/config" className="text-center p-4 bg-white rounded-lg shadow hover:shadow-md transition-shadow">
              <div className="text-2xl mb-2">🔧</div>
              <div className="text-sm font-medium text-gray-900">Configuration</div>
            </a>
          </div>
        </div>
      </div>
    </ProtectedRoute>
  );
}