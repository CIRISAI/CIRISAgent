"""
Additional manager tests for coverage.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path
from ciris_manager.manager import CIRISManager
from ciris_manager.config.settings import CIRISManagerConfig
from .conftest import create_test_config


class TestManagerAdditional:
    """Additional manager tests."""
    
    @pytest.mark.asyncio
    async def test_start_api_server_import_error(self, tmp_path):
        """Test API server start with import error."""
        config = create_test_config(tmp_path)
        config.manager.port = 0  # Use port 0 to get a random available port
        
        manager = CIRISManager(config)
        
        # Mock uvicorn module at import time
        import sys
        mock_uvicorn = Mock()
        mock_server = AsyncMock()
        mock_uvicorn.Server.return_value = mock_server
        mock_uvicorn.Config.return_value = Mock()
        
        with patch.dict('sys.modules', {'uvicorn': mock_uvicorn}):
            # This will test the server creation path
            await manager._start_api_server()
            
            # Just verify the method completes without error
            assert mock_uvicorn.Config.called or mock_uvicorn.Server.called
    
    @pytest.mark.asyncio
    async def test_container_management_with_image_pull_disabled(self, tmp_path):
        """Test container management without pulling images."""
        config = create_test_config(tmp_path)
        config.container_management.pull_images = False
        config.container_management.interval = 0.01
        
        manager = CIRISManager(config)
        
        # Create agent with compose file
        agent_dir = tmp_path / "agents" / "test"
        agent_dir.mkdir(parents=True)
        compose_file = agent_dir / "docker-compose.yml"
        compose_file.write_text("version: '3.8'\n")
        
        manager.agent_registry.register_agent(
            agent_id="agent-test",
            name="Test",
            port=8080,
            template="test",
            compose_file=str(compose_file)
        )
        
        # Mock subprocess
        with patch('asyncio.create_subprocess_exec') as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_subprocess.return_value = mock_process
            
            # Run briefly
            manager._running = True
            task = asyncio.create_task(manager.container_management_loop())
            await asyncio.sleep(0.05)
            manager._running = False
            
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            
            # Should not have called pull
            for call in mock_subprocess.call_args_list:
                assert "pull" not in call[0]
    
    def test_scan_with_invalid_metadata(self, tmp_path):
        """Test scanning with invalid agent metadata."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir(exist_ok=True)
        config = create_test_config(tmp_path)
        
        # Create agent directory
        agent_dir = agents_dir / "test"
        agent_dir.mkdir()
        compose_file = agent_dir / "docker-compose.yml"
        compose_file.write_text("version: '3.8'\n")
        
        # Create invalid metadata
        metadata_file = agents_dir / "metadata.json"
        metadata_file.write_text("invalid json")
        
        # Should handle gracefully
        manager = CIRISManager(config)
        # No exception raised