#!/usr/bin/env python3
"""
CIRISManager CLI v2 - Full agent management from the command line.

Examples:
    # List all agents
    ciris-manager agent list
    
    # Create a service agent
    ciris-manager agent create --name my-api --template scout --mode service
    
    # Create a Discord bot
    ciris-manager agent create --name my-bot --template sage --mode discord \
        --env DISCORD_BOT_TOKEN=xxx --env DISCORD_HOME_CHANNEL_ID=yyy
    
    # Create a multi-mode agent
    ciris-manager agent create --name multi --template default --mode service,discord
    
    # Delete an agent
    ciris-manager agent delete my-api
    
    # Check agent status
    ciris-manager agent status my-api
"""

import click
import requests
import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional
try:
    from tabulate import tabulate
except ImportError:
    # Simple fallback if tabulate not installed
    def tabulate(data, headers, tablefmt=None):
        lines = []
        lines.append(' | '.join(headers))
        lines.append('-' * (len(' | '.join(headers))))
        for row in data:
            lines.append(' | '.join(str(x) for x in row))
        return '\n'.join(lines)
import sys
import os

# Default manager URL
DEFAULT_MANAGER_URL = "http://localhost:8888"


class ManagerClient:
    """Client for interacting with CIRISManager API."""
    
    def __init__(self, base_url: str, token: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        if token:
            self.session.headers['Authorization'] = f'Bearer {token}'
    
    def list_agents(self) -> List[Dict]:
        """List all agents."""
        resp = self.session.get(f"{self.base_url}/manager/v1/agents")
        resp.raise_for_status()
        return resp.json()['agents']
    
    def create_agent(self, template: str, name: str, environment: Dict[str, str], 
                     wa_signature: Optional[str] = None) -> Dict:
        """Create a new agent."""
        data = {
            "template": template,
            "name": name
        }
        if environment:
            data["environment"] = environment
        if wa_signature:
            data["wa_signature"] = wa_signature
        
        resp = self.session.post(f"{self.base_url}/manager/v1/agents", json=data)
        resp.raise_for_status()
        return resp.json()
    
    def delete_agent(self, agent_id: str) -> Dict:
        """Delete an agent."""
        resp = self.session.delete(f"{self.base_url}/manager/v1/agents/{agent_id}")
        resp.raise_for_status()
        return resp.json()
    
    def get_agent(self, agent_id: str) -> Dict:
        """Get agent details."""
        resp = self.session.get(f"{self.base_url}/manager/v1/agents/{agent_id}")
        resp.raise_for_status()
        return resp.json()
    
    def list_templates(self) -> Dict:
        """List available templates."""
        resp = self.session.get(f"{self.base_url}/manager/v1/templates")
        resp.raise_for_status()
        return resp.json()


@click.group()
@click.option('--manager-url', default=DEFAULT_MANAGER_URL, 
              envvar='CIRIS_MANAGER_URL', help='CIRISManager API URL')
@click.option('--token', envvar='CIRIS_MANAGER_TOKEN', help='Authentication token')
@click.pass_context
def cli(ctx, manager_url, token):
    """CIRISManager CLI - Manage CIRIS agents from the command line."""
    ctx.ensure_object(dict)
    ctx.obj['client'] = ManagerClient(manager_url, token)


@cli.group()
def agent():
    """Manage CIRIS agents."""
    pass


@agent.command('list')
@click.pass_context
def list_agents(ctx):
    """List all agents."""
    try:
        agents = ctx.obj['client'].list_agents()
        
        if not agents:
            click.echo("No agents found.")
            return
        
        # Format for table display
        table_data = []
        for agent in agents:
            # Extract mode from environment
            env = agent.get('environment', {})
            mode = env.get('CIRIS_MODE', env.get('CIRIS_ADAPTER', 'unknown'))
            
            table_data.append([
                agent.get('agent_id', 'N/A'),
                agent.get('agent_name', 'N/A'),
                agent.get('status', 'unknown'),
                mode,
                agent.get('api_port', 'N/A'),
                agent.get('container_name', 'N/A')
            ])
        
        headers = ['Agent ID', 'Name', 'Status', 'Mode', 'Port', 'Container']
        click.echo(tabulate(table_data, headers=headers, tablefmt='grid'))
        
    except requests.exceptions.RequestException as e:
        click.echo(f"Error: Failed to connect to manager: {e}", err=True)
        sys.exit(1)


@agent.command('create')
@click.option('--name', '-n', required=True, help='Agent name')
@click.option('--template', '-t', default='default', help='Template to use')
@click.option('--mode', '-m', default='service', 
              help='Agent mode: service, discord, tool, or comma-separated')
@click.option('--env', '-e', multiple=True, help='Environment variables (KEY=VALUE)')
@click.option('--env-file', type=click.Path(exists=True), 
              help='Load environment from .env file')
@click.option('--wa-signature', help='Wise Authority signature (for non-pre-approved templates)')
@click.pass_context
def create_agent(ctx, name, template, mode, env, env_file, wa_signature):
    """Create a new agent.
    
    Examples:
        # Create a service agent
        ciris-manager agent create --name api-bot --mode service
        
        # Create a Discord bot
        ciris-manager agent create --name discord-bot --mode discord \\
            --env DISCORD_BOT_TOKEN=xxx --env DISCORD_HOME_CHANNEL_ID=yyy
        
        # Create multi-mode agent
        ciris-manager agent create --name multi --mode service,discord
    """
    try:
        # Build environment dict
        environment = {}
        
        # Always set CIRIS_MODE
        environment['CIRIS_MODE'] = mode
        
        # For backward compatibility, also set CIRIS_ADAPTER
        adapter_mapping = {
            'service': 'api',
            'tool': 'cli',
            'discord': 'discord'
        }
        adapters = []
        for m in mode.split(','):
            m = m.strip()
            adapters.append(adapter_mapping.get(m, m))
        environment['CIRIS_ADAPTER'] = ','.join(adapters)
        
        # Load from env file if provided
        if env_file:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        environment[key.strip()] = value.strip()
        
        # Add individual env vars
        for e in env:
            if '=' in e:
                key, value = e.split('=', 1)
                environment[key] = value
        
        # Create the agent
        click.echo(f"Creating agent '{name}' with template '{template}' in mode '{mode}'...")
        result = ctx.obj['client'].create_agent(template, name, environment, wa_signature)
        
        click.echo(f"✓ Agent created successfully!")
        click.echo(f"  Agent ID: {result['agent_id']}")
        click.echo(f"  Container: {result['container']}")
        click.echo(f"  Port: {result['port']}")
        click.echo(f"  API Endpoint: {result['api_endpoint']}")
        click.echo(f"  Mode: {mode}")
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            click.echo(f"Error: Permission denied. This template requires WA signature.", err=True)
        else:
            click.echo(f"Error: {e.response.json().get('detail', str(e))}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@agent.command('delete')
@click.argument('agent_id')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation')
@click.pass_context
def delete_agent(ctx, agent_id, yes):
    """Delete an agent."""
    try:
        if not yes:
            click.confirm(f"Are you sure you want to delete agent '{agent_id}'?", abort=True)
        
        click.echo(f"Deleting agent '{agent_id}'...")
        result = ctx.obj['client'].delete_agent(agent_id)
        
        click.echo(f"✓ Agent deleted successfully!")
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            click.echo(f"Error: Agent '{agent_id}' not found.", err=True)
        else:
            click.echo(f"Error: {e.response.json().get('detail', str(e))}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@agent.command('status')
@click.argument('agent_id')
@click.pass_context
def agent_status(ctx, agent_id):
    """Show detailed agent status."""
    try:
        agent = ctx.obj['client'].get_agent(agent_id)
        
        click.echo(f"\nAgent: {agent['name']} ({agent['agent_id']})")
        click.echo(f"Template: {agent['template']}")
        click.echo(f"Port: {agent['port']}")
        click.echo(f"Created: {agent.get('created_at', 'Unknown')}")
        
        # Try to get from live discovery
        agents = ctx.obj['client'].list_agents()
        live_agent = next((a for a in agents if a['agent_id'] == agent_id), None)
        
        if live_agent:
            click.echo(f"\nLive Status:")
            click.echo(f"  Container: {live_agent.get('container_name', 'N/A')}")
            click.echo(f"  Status: {live_agent.get('status', 'unknown')}")
            click.echo(f"  Health: {live_agent.get('health', 'unknown')}")
            
            env = live_agent.get('environment', {})
            mode = env.get('CIRIS_MODE', env.get('CIRIS_ADAPTER', 'unknown'))
            click.echo(f"  Mode: {mode}")
            
            if live_agent.get('api_endpoint'):
                click.echo(f"  API: {live_agent['api_endpoint']}")
        else:
            click.echo(f"\nStatus: Not running")
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            click.echo(f"Error: Agent '{agent_id}' not found.", err=True)
        else:
            click.echo(f"Error: {e.response.json().get('detail', str(e))}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.group()
def template():
    """Manage agent templates."""
    pass


@template.command('list')
@click.pass_context
def list_templates(ctx):
    """List available templates."""
    try:
        result = ctx.obj['client'].list_templates()
        
        click.echo("\nAvailable Templates:")
        click.echo("=" * 60)
        
        for name, desc in result['templates'].items():
            pre_approved = " ✓" if name in result['pre_approved'] else " (requires WA signature)"
            click.echo(f"{name:<20} {desc}{pre_approved}")
        
        click.echo("\n✓ = Pre-approved (no signature required)")
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command('test-mode')
@click.option('--mode', '-m', default='service,discord', 
              help='Mode to test (default: service,discord)')
@click.pass_context
def test_mode(ctx, mode):
    """Quick test of the new CIRIS_MODE feature.
    
    Creates a test agent with the specified mode to verify it works correctly.
    """
    import random
    import string
    
    # Generate random agent name
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    name = f"test-mode-{suffix}"
    
    click.echo(f"Testing CIRIS_MODE='{mode}'...")
    click.echo(f"Creating test agent: {name}")
    
    try:
        # Create agent with specified mode
        environment = {
            'CIRIS_MODE': mode,
            'CIRIS_MOCK_LLM': 'true'  # Use mock LLM for testing
        }
        
        # Add backward compatibility
        adapter_mapping = {
            'service': 'api',
            'tool': 'cli',
            'discord': 'discord'
        }
        adapters = []
        for m in mode.split(','):
            m = m.strip()
            adapters.append(adapter_mapping.get(m, m))
        environment['CIRIS_ADAPTER'] = ','.join(adapters)
        
        result = ctx.obj['client'].create_agent('default', name, environment)
        
        click.echo(f"✓ Agent created with mode '{mode}'")
        click.echo(f"  Agent ID: {result['agent_id']}")
        click.echo(f"  Port: {result['port']}")
        
        # Check if it's running
        import time
        time.sleep(3)  # Give it time to start
        
        agents = ctx.obj['client'].list_agents()
        test_agent = next((a for a in agents if a['agent_id'] == result['agent_id']), None)
        
        if test_agent:
            click.echo(f"\n✓ Agent is running!")
            click.echo(f"  Status: {test_agent.get('status', 'unknown')}")
            click.echo(f"  Mode in env: {test_agent.get('environment', {}).get('CIRIS_MODE', 'not set')}")
            
            # Cleanup
            if click.confirm("\nDelete test agent?", default=True):
                ctx.obj['client'].delete_agent(result['agent_id'])
                click.echo("✓ Test agent deleted")
        else:
            click.echo(f"\n⚠ Agent not found in running containers")
            click.echo("This might be expected if mode='tool' (exits after startup)")
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli()