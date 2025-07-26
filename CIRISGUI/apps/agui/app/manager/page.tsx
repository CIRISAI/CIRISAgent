'use client';

import { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, Plus, Server, Trash2, RefreshCw } from 'lucide-react';
import { CIRISManagerClient, AgentInfo, ManagerStatus } from '../../lib/ciris-manager-client';
import { CreateAgentDialog } from './create-agent-dialog';
import { ManagerProtectedRoute } from '../../components/ManagerProtectedRoute';

export default function ManagerPage() {
  return (
    <ManagerProtectedRoute>
      <ManagerPageContent />
    </ManagerProtectedRoute>
  );
}

function ManagerPageContent() {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [status, setStatus] = useState<ManagerStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const managerClient = new CIRISManagerClient({
    baseURL: '/manager/v1'  // Use relative URLs through nginx
  });

  const fetchData = async () => {
    try {
      setError(null);
      const [agentsList, managerStatus] = await Promise.all([
        managerClient.listAgents(),
        managerClient.status()
      ]);
      setAgents(agentsList);
      setStatus(managerStatus);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  const handleDeleteAgent = async (agentId: string) => {
    if (!confirm(`Are you sure you want to delete agent ${agentId}?`)) {
      return;
    }

    try {
      await managerClient.deleteAgent(agentId);
      await fetchData(); // Refresh the list
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete agent');
    }
  };

  const handleAgentCreated = () => {
    setCreateDialogOpen(false);
    fetchData(); // Refresh the list
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6">
      <div className="mb-6 flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold">CIRIS Manager</h1>
          <p className="text-muted-foreground mt-1">
            Manage your CIRIS agents and infrastructure
          </p>
        </div>
        <div className="flex gap-2">
          <Button 
            variant="outline" 
            size="sm"
            onClick={handleRefresh}
            disabled={refreshing}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <Button onClick={() => setCreateDialogOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Create Agent
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-6">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Tabs defaultValue="agents" className="space-y-4">
        <TabsList>
          <TabsTrigger value="agents">Agents</TabsTrigger>
          <TabsTrigger value="status">Manager Status</TabsTrigger>
        </TabsList>

        <TabsContent value="agents" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Active Agents</CardTitle>
              <CardDescription>
                {agents.length} agent{agents.length !== 1 ? 's' : ''} currently running
              </CardDescription>
            </CardHeader>
            <CardContent>
              {agents.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  No agents running. Create one to get started.
                </div>
              ) : (
                <div className="space-y-4">
                  {agents.map((agent) => (
                    <div
                      key={agent.agent_id}
                      className="border rounded-lg p-4 hover:bg-accent/50 transition-colors"
                    >
                      <div className="flex items-start justify-between">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <Server className="h-4 w-4" />
                            <h3 className="font-semibold">{agent.name}</h3>
                            <Badge variant="secondary">{agent.template}</Badge>
                          </div>
                          <p className="text-sm text-muted-foreground">
                            ID: {agent.agent_id}
                          </p>
                          <p className="text-sm text-muted-foreground">
                            Port: {agent.port} • API: {agent.api_endpoint}
                          </p>
                          {agent.created_at && (
                            <p className="text-xs text-muted-foreground">
                              Created: {new Date(agent.created_at).toLocaleString()}
                            </p>
                          )}
                        </div>
                        <div className="flex gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => window.open(agent.api_endpoint, '_blank')}
                          >
                            Open API
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDeleteAgent(agent.agent_id)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="status" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Manager Status</CardTitle>
              <CardDescription>
                Current status of the CIRIS Manager service
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {status && (
                <>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">Status:</span>
                    <Badge variant={status.status === 'running' ? 'default' : 'secondary'}>
                      {status.status}
                    </Badge>
                  </div>
                  <div>
                    <span className="font-semibold">Version:</span> {status.version}
                  </div>
                  <div>
                    <h4 className="font-semibold mb-2">Components:</h4>
                    <div className="grid grid-cols-2 gap-2">
                      {Object.entries(status.components).map(([component, state]) => (
                        <div key={component} className="flex items-center justify-between bg-accent/30 rounded p-2">
                          <span className="text-sm">{component}</span>
                          <Badge variant="outline" className="text-xs">
                            {state}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <CreateAgentDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        onAgentCreated={handleAgentCreated}
        managerClient={managerClient}
      />
    </div>
  );
}