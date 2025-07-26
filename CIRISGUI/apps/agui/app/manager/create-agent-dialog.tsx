'use client';

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Loader2, Info, Eye, EyeOff } from 'lucide-react';
import { CIRISManagerClient, TemplateInfo, CreateAgentRequest } from '../../lib/ciris-manager-client';

interface CreateAgentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAgentCreated: () => void;
  managerClient: CIRISManagerClient;
}

export function CreateAgentDialog({
  open,
  onOpenChange,
  onAgentCreated,
  managerClient
}: CreateAgentDialogProps) {
  const [templates, setTemplates] = useState<TemplateInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const [formData, setFormData] = useState<CreateAgentRequest>({
    template: '',
    name: '',
    environment: {},
    wa_signature: ''
  });

  const [envVars, setEnvVars] = useState<Array<{ key: string; value: string }>>([
    { key: '', value: '' }
  ]);
  
  const [envFileContent, setEnvFileContent] = useState<string>('');
  const [showRedacted, setShowRedacted] = useState(false);

  // Redact sensitive values in environment variables
  const redactValue = (key: string, value: string): string => {
    const sensitiveKeys = [
      'TOKEN', 'KEY', 'SECRET', 'PASSWORD', 'PASS', 'PWD',
      'AUTH', 'CREDENTIAL', 'API_KEY', 'ACCESS_KEY', 'PRIVATE'
    ];
    
    const shouldRedact = sensitiveKeys.some(sensitive => 
      key.toUpperCase().includes(sensitive)
    );
    
    if (shouldRedact && value && value.length > 0) {
      // Show first 4 and last 4 characters for verification
      if (value.length > 8) {
        return `${value.slice(0, 4)}...${value.slice(-4)}`;
      } else {
        return '****';
      }
    }
    return value;
  };

  // Parse .env file content into key-value pairs
  const parseEnvFile = (content: string): Array<{ key: string; value: string }> => {
    const lines = content.split('\n');
    const vars: Array<{ key: string; value: string }> = [];
    
    lines.forEach(line => {
      const trimmed = line.trim();
      if (trimmed && !trimmed.startsWith('#')) {
        const [key, ...valueParts] = trimmed.split('=');
        if (key) {
          vars.push({
            key: key.trim(),
            value: valueParts.join('=').trim()
          });
        }
      }
    });
    
    return vars;
  };

  // Load default .env values
  const loadDefaultEnv = async () => {
    try {
      const response = await fetch('/manager/v1/env/default');
      if (response.ok) {
        const data = await response.json();
        if (data.content) {
          setEnvFileContent(data.content);
          const parsed = parseEnvFile(data.content);
          setEnvVars(parsed.length > 0 ? parsed : [{ key: '', value: '' }]);
        }
      }
    } catch (error) {
      console.error('Failed to load default .env:', error);
    }
  };

  useEffect(() => {
    if (open) {
      fetchTemplates();
      loadDefaultEnv();
    }
  }, [open]);

  const fetchTemplates = async () => {
    setLoading(true);
    try {
      const templateData = await managerClient.listTemplates();
      setTemplates(templateData);
      // Select first pre-approved template by default
      if (templateData.pre_approved.length > 0) {
        setFormData(prev => ({ ...prev, template: templateData.pre_approved[0] }));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch templates');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setCreating(true);

    try {
      // Convert env vars array to object
      const environment: Record<string, string> = {};
      envVars.forEach(({ key, value }) => {
        if (key.trim()) {
          environment[key] = value;
        }
      });

      const request: CreateAgentRequest = {
        ...formData,
        environment: Object.keys(environment).length > 0 ? environment : undefined
      };

      await managerClient.createAgent(request);
      onAgentCreated();
      
      // Reset form
      setFormData({
        template: templates?.pre_approved[0] || '',
        name: '',
        environment: {},
        wa_signature: ''
      });
      setEnvVars([{ key: '', value: '' }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create agent');
    } finally {
      setCreating(false);
    }
  };

  const addEnvVar = () => {
    setEnvVars([...envVars, { key: '', value: '' }]);
  };

  const removeEnvVar = (index: number) => {
    setEnvVars(envVars.filter((_, i) => i !== index));
  };

  const updateEnvVar = (index: number, field: 'key' | 'value', value: string) => {
    const updated = [...envVars];
    updated[index][field] = value;
    setEnvVars(updated);
  };

  const isPreApproved = templates?.pre_approved.includes(formData.template) ?? false;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Create New Agent</DialogTitle>
          <DialogDescription>
            Deploy a new CIRIS agent instance with the selected template
          </DialogDescription>
        </DialogHeader>

        <form id="create-agent-form" onSubmit={handleSubmit} className="flex flex-col flex-1 overflow-hidden">
          <div className="space-y-4 py-4 overflow-y-auto flex-1 px-1">
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <div className="space-y-2">
              <Label htmlFor="template">Template</Label>
              <Select
                value={formData.template}
                onValueChange={(value) => setFormData({ ...formData, template: value })}
                disabled={loading || !templates}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select a template" />
                </SelectTrigger>
                <SelectContent>
                  {templates && Object.entries(templates.templates).map(([key, description]) => (
                    <SelectItem key={key} value={key}>
                      <div className="flex items-center gap-2">
                        <span>{key}</span>
                        {templates.pre_approved.includes(key) && (
                          <Badge variant="secondary" className="text-xs">Pre-approved</Badge>
                        )}
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {!isPreApproved && formData.template && (
                <Alert>
                  <Info className="h-4 w-4" />
                  <AlertDescription>
                    This template requires Wise Authority approval. Please provide a signature below.
                  </AlertDescription>
                </Alert>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="name">Agent Name</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="my-agent"
                required
              />
            </div>

            {!isPreApproved && formData.template && (
              <div className="space-y-2">
                <Label htmlFor="wa_signature">Wise Authority Signature</Label>
                <Textarea
                  id="wa_signature"
                  value={formData.wa_signature}
                  onChange={(e) => setFormData({ ...formData, wa_signature: e.target.value })}
                  placeholder="Ed25519 signature from Wise Authority"
                  rows={3}
                  required
                />
              </div>
            )}

            <div className="space-y-2">
              <Label>Environment Variables (Optional)</Label>
              <Tabs defaultValue="keyvalue">
                <TabsList className="grid w-full grid-cols-2">
                  <TabsTrigger value="keyvalue">Key-Value</TabsTrigger>
                  <TabsTrigger value="envfile">.env File</TabsTrigger>
                </TabsList>
                
                <TabsContent value="keyvalue" className="space-y-2">
                  <div className="flex justify-between items-center mb-2">
                    <div className="flex items-center gap-2">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => setShowRedacted(!showRedacted)}
                      >
                        {showRedacted ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                        {showRedacted ? 'Hide Values' : 'Show Values'}
                      </Button>
                    </div>
                    <Button type="button" variant="outline" size="sm" onClick={addEnvVar}>
                      Add Variable
                    </Button>
                  </div>
                  <div className="space-y-2">
                    {envVars.map((envVar, index) => (
                      <div key={index} className="flex gap-2">
                        <Input
                          placeholder="Key"
                          value={envVar.key}
                          onChange={(e) => updateEnvVar(index, 'key', e.target.value)}
                        />
                        <Input
                          placeholder="Value"
                          type={showRedacted ? "text" : "password"}
                          value={showRedacted ? envVar.value : redactValue(envVar.key, envVar.value)}
                          onChange={(e) => updateEnvVar(index, 'value', e.target.value)}
                          disabled={!showRedacted && redactValue(envVar.key, envVar.value) !== envVar.value}
                        />
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => removeEnvVar(index)}
                          disabled={envVars.length === 1}
                        >
                          Remove
                        </Button>
                      </div>
                    ))}
                  </div>
                </TabsContent>
                
                <TabsContent value="envfile" className="space-y-2">
                  <div className="flex items-center gap-2 mb-2">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowRedacted(!showRedacted)}
                    >
                      {showRedacted ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      {showRedacted ? 'Hide Sensitive Values' : 'Show All Values'}
                    </Button>
                    <span className="text-sm text-muted-foreground">
                      Sensitive values are redacted for security
                    </span>
                  </div>
                  <Textarea
                    placeholder="Paste your .env file content here..."
                    value={showRedacted ? envFileContent : envFileContent.split('\n').map(line => {
                      const trimmed = line.trim();
                      if (trimmed && !trimmed.startsWith('#')) {
                        const [key, ...valueParts] = trimmed.split('=');
                        if (key) {
                          const value = valueParts.join('=').trim();
                          const redacted = redactValue(key.trim(), value);
                          if (redacted !== value) {
                            return `${key}=${redacted}`;
                          }
                        }
                      }
                      return line;
                    }).join('\n')}
                    onChange={(e) => {
                      setEnvFileContent(e.target.value);
                      const parsed = parseEnvFile(e.target.value);
                      setEnvVars(parsed.length > 0 ? parsed : [{ key: '', value: '' }]);
                    }}
                    rows={8}
                    className="font-mono text-sm"
                  />
                  {envFileContent && (
                    <p className="text-sm text-muted-foreground">
                      {parseEnvFile(envFileContent).length} variables detected
                    </p>
                  )}
                </TabsContent>
              </Tabs>
            </div>
          </div>
        </form>
        
        <div className="border-t pt-4 mt-4">
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={creating}
            >
              Cancel
            </Button>
            <Button 
              type="submit" 
              form="create-agent-form"
              disabled={creating || !formData.template || !formData.name}>
              {creating ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Creating...
                </>
              ) : (
                'Create Agent'
              )}
          </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}