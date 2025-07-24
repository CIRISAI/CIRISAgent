#!/usr/bin/env python3
"""
Test script for nginx configuration generation.

Tests the template-based nginx config generation with multiple agents.
"""
import sys
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ciris_manager.nginx_manager import NginxManager


def test_nginx_generation():
    """Test nginx config generation with sample agents."""
    
    # Initialize nginx manager with test directory
    test_dir = Path("/tmp/test_nginx")
    test_dir.mkdir(exist_ok=True)
    
    nginx_manager = NginxManager(
        config_dir=str(test_dir),
        container_name="test-nginx"
    )
    
    # Sample agents data (simulating what docker_discovery would return)
    test_agents = [
        {
            "agent_id": "datum",
            "agent_name": "Datum",
            "api_port": 8080,
            "status": "running",
            "container": "ciris-agent-datum"
        },
        {
            "agent_id": "sage",
            "agent_name": "Sage",
            "api_port": 8081,
            "status": "running",
            "container": "ciris-agent-sage"
        },
        {
            "agent_id": "scout",
            "agent_name": "Scout",
            "api_port": 8082,
            "status": "stopped",
            "container": "ciris-agent-scout"
        }
    ]
    
    print("Testing nginx config generation with 3 agents...")
    print(f"Agents: {[a['agent_name'] for a in test_agents]}")
    print()
    
    # Generate config
    config = nginx_manager.generate_config(test_agents)
    
    print("Generated nginx.conf:")
    print("=" * 80)
    print(config)
    print("=" * 80)
    
    # Write to test file
    test_config_path = test_dir / "nginx.conf.test"
    test_config_path.write_text(config)
    print(f"\nConfig written to: {test_config_path}")
    
    # Verify key sections exist
    print("\nVerification:")
    print(f"- Contains 'upstream gui': {'upstream gui' in config}")
    print(f"- Contains 'upstream manager': {'upstream manager' in config}")
    print(f"- Contains 'upstream agent_datum': {'upstream agent_datum' in config}")
    print(f"- Contains 'upstream agent_sage': {'upstream agent_sage' in config}")
    print(f"- Contains 'upstream agent_scout': {'upstream agent_scout' in config}")
    print(f"- Contains default route to datum: {'/v1/' in config and 'agent_datum' in config}")
    print(f"- Contains OAuth routes: {'/v1/auth/oauth/' in config}")
    print(f"- Contains API routes: {'/api/' in config}")
    
    # Test with empty agent list
    print("\n\nTesting with no agents...")
    empty_config = nginx_manager.generate_config([])
    print("Empty agent list config (first 500 chars):")
    print(empty_config[:500])
    print("...")
    print(f"- Contains GUI route: {'location /' in empty_config}")
    print(f"- Contains manager route: {'/manager/v1/' in empty_config}")
    print(f"- No default API route: {'/v1/' not in empty_config or 'agent_' not in empty_config}")


if __name__ == "__main__":
    test_nginx_generation()