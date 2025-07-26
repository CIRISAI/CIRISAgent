"""
Additional tests for CIRISManager to improve coverage.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path
from ciris_manager.manager import CIRISManager, main
from ciris_manager.config.settings import CIRISManagerConfig


class TestManagerCoverage:
    """Additional test cases for manager coverage."""
    
    @pytest.mark.asyncio
    async def test_main_entry_point(self):
        """Test main entry point."""
        with patch('ciris_manager.manager.logging.basicConfig'):
            with patch('ciris_manager.manager.CIRISManagerConfig.from_file') as mock_from_file:
                mock_config = Mock()
                mock_from_file.return_value = mock_config
                
                with patch('ciris_manager.manager.CIRISManager') as mock_manager_class:
                    mock_manager = AsyncMock()
                    mock_manager.run = AsyncMock()
                    mock_manager_class.return_value = mock_manager
                    
                    with patch('ciris_manager.manager.asyncio.run') as mock_run:
                        # Call main through asyncio
                        await main()
                        
                        # Verify manager was created and run
                        mock_manager_class.assert_called_once_with(mock_config)
                        mock_manager.run.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_add_nginx_route(self, tmp_path):
        """Test nginx route addition."""
        nginx_dir = tmp_path / "nginx"
        nginx_dir.mkdir()
        
        config = CIRISManagerConfig(
            manager={
                "agents_directory": str(tmp_path / "agents")
            },
            nginx={
                "config_dir": str(nginx_dir)
            }
        )
        
        with patch('ciris_manager.nginx_manager.NginxManager') as mock_nginx_class:
            # Configure nginx manager mock
            mock_nginx = Mock()
            mock_nginx.update_config = Mock(return_value=True)
            mock_nginx_class.return_value = mock_nginx
            
            manager = CIRISManager(config)
            manager.nginx_manager = mock_nginx
            
            # Test nginx route addition
            await manager._add_nginx_route("scout", 8081)
            
            # Should call update_config with agent list
            mock_nginx.update_config.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_nginx_config_error_handling(self, tmp_path):
        """Test nginx config update error handling."""
        nginx_dir = tmp_path / "nginx"
        nginx_dir.mkdir()
        
        config = CIRISManagerConfig(
            manager={
                "agents_directory": str(tmp_path / "agents")
            },
            nginx={
                "config_dir": str(nginx_dir)
            }
        )
        
        with patch('ciris_manager.nginx_manager.NginxManager') as mock_nginx_class:
            # Configure nginx manager mock to raise error
            mock_nginx = Mock()
            mock_nginx.update_config = Mock(side_effect=Exception("Config error"))
            mock_nginx_class.return_value = mock_nginx
            
            manager = CIRISManager(config)
            manager.nginx_manager = mock_nginx
            
            # Should catch exception and return False
            result = await manager.update_nginx_config()
            assert result is False
    
    @pytest.mark.asyncio
    async def test_add_nginx_route_failure(self, tmp_path):
        """Test nginx route addition failure."""
        nginx_dir = tmp_path / "nginx"
        nginx_dir.mkdir()
        
        config = CIRISManagerConfig(
            manager={
                "agents_directory": str(tmp_path / "agents")
            },
            nginx={
                "config_dir": str(nginx_dir)
            }
        )
        
        with patch('ciris_manager.nginx_manager.NginxManager') as mock_nginx_class:
            # Configure nginx manager mock to return False
            mock_nginx = Mock()
            mock_nginx.update_config = Mock(return_value=False)
            mock_nginx_class.return_value = mock_nginx
            
            manager = CIRISManager(config)
            manager.nginx_manager = mock_nginx
            
            # Should raise RuntimeError when update fails
            with pytest.raises(RuntimeError, match="Failed to update nginx configuration"):
                await manager._add_nginx_route("scout", 8081)
    
    @pytest.mark.asyncio
    async def test_pull_agent_images(self, tmp_path):
        """Test pulling agent images."""
        nginx_dir = tmp_path / "nginx"
        nginx_dir.mkdir()
        
        config = CIRISManagerConfig(
            manager={
                "agents_directory": str(tmp_path / "agents")
            },
            nginx={
                "config_dir": str(nginx_dir)
            }
        )
        
        manager = CIRISManager(config)
        
        compose_path = tmp_path / "docker-compose.yml"
        compose_path.write_text("version: '3.8'\n")
        
        # Mock subprocess
        with patch('asyncio.create_subprocess_exec') as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_subprocess.return_value = mock_process
            
            await manager._pull_agent_images(compose_path)
            
            # Verify docker-compose pull was called
            mock_subprocess.assert_called_once()
            call_args = mock_subprocess.call_args[0]
            assert call_args[0] == "docker-compose"
            assert call_args[1] == "-f"
            assert str(compose_path) in call_args[2]
            assert call_args[3] == "pull"
    
    def test_scan_existing_agents_no_directory(self, tmp_path):
        """Test scanning when agents directory doesn't exist."""
        nginx_dir = tmp_path / "nginx"
        nginx_dir.mkdir()
        
        config = CIRISManagerConfig(
            manager={
                "agents_directory": str(tmp_path / "nonexistent")
            },
            nginx={
                "config_dir": str(nginx_dir)
            }
        )
        
        # Should not raise error
        manager = CIRISManager(config)
        manager._scan_existing_agents()
        
        # No agents should be found
        assert len(manager.agent_registry.agents) == 0
    
    @pytest.mark.asyncio
    async def test_container_management_loop_error_handling(self, tmp_path):
        """Test container management loop error handling."""
        nginx_dir = tmp_path / "nginx"
        nginx_dir.mkdir()
        
        config = CIRISManagerConfig(
            manager={
                "agents_directory": str(tmp_path / "agents")
            },
            nginx={
                "config_dir": str(nginx_dir)
            },
            container_management={
                "interval": 1  # Fast for testing (minimum 1 second)
            }
        )
        
        manager = CIRISManager(config)
        manager._running = True
        
        # Register an agent with invalid compose file
        manager.agent_registry.register_agent(
            agent_id="agent-test",
            name="Test",
            port=8080,
            template="test",
            compose_file="/invalid/path/compose.yml"
        )
        
        # Run loop briefly
        loop_task = asyncio.create_task(manager.container_management_loop())
        await asyncio.sleep(0.05)
        
        # Stop
        manager._running = False
        
        # Cancel and wait
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass
        
        # Should have handled error and continued
    
    @pytest.mark.asyncio
    async def test_create_agent_allocate_existing_port(self, tmp_path):
        """Test agent creation when port is already allocated."""
        nginx_dir = tmp_path / "nginx"
        nginx_dir.mkdir()
        
        config = CIRISManagerConfig(
            manager={
                "agents_directory": str(tmp_path / "agents"),
                "templates_directory": str(tmp_path / "templates")
            },
            nginx={
                "config_dir": str(nginx_dir)
            }
        )
        
        # Create template
        templates_dir = Path(config.manager.templates_directory)
        templates_dir.mkdir(parents=True)
        template_path = templates_dir / "test.yaml"
        template_path.write_text("name: test\n")
        
        with patch('ciris_manager.nginx_manager.NginxManager') as mock_nginx_class:
            # Configure nginx manager mock
            mock_nginx = Mock()
            mock_nginx.ensure_managed_sections = Mock(return_value=True)
            mock_nginx.add_agent_route = Mock(return_value=True)
            mock_nginx_class.return_value = mock_nginx
            
            manager = CIRISManager(config)
            manager.nginx_manager = mock_nginx
        
            # Pre-allocate port
            manager.port_manager.allocate_port("agent-existing")
        
            # Mock verifier and subprocess
            manager.template_verifier.is_pre_approved = Mock(return_value=True)
            
            with patch('asyncio.create_subprocess_exec') as mock_subprocess:
                mock_process = AsyncMock()
                mock_process.returncode = 0
                mock_process.communicate = AsyncMock(return_value=(b"", b""))
                mock_subprocess.return_value = mock_process
                
                # Create agent - should get next available port
                result = await manager.create_agent("test", "Test")
                
                assert result["port"] == 8081  # Next available
    
    @pytest.mark.asyncio 
    async def test_start_api_server_disabled(self, tmp_path):
        """Test that API server doesn't start when port is not configured."""
        nginx_dir = tmp_path / "nginx"
        nginx_dir.mkdir()
        
        config = CIRISManagerConfig(
            manager={
                "agents_directory": str(tmp_path / "agents"),
                "port": 0  # Disable API (0 means don't bind)
            },
            nginx={
                "config_dir": str(nginx_dir)
            }
        )
        
        manager = CIRISManager(config)
        
        with patch.object(manager, '_start_api_server') as mock_start_api:
            await manager.start()
            
            # API server should not be started
            mock_start_api.assert_not_called()
            
            await manager.stop()
    
    @pytest.mark.asyncio
    async def test_run_with_signal_handlers(self, tmp_path):
        """Test run method with signal handling."""
        nginx_dir = tmp_path / "nginx"
        nginx_dir.mkdir()
        
        config = CIRISManagerConfig(
            manager={
                "agents_directory": str(tmp_path / "agents")
            },
            nginx={
                "config_dir": str(nginx_dir)
            }
        )
        
        manager = CIRISManager(config)
        
        # Mock signal handler setup
        with patch('asyncio.get_event_loop') as mock_get_loop:
            mock_loop = Mock()
            mock_get_loop.return_value = mock_loop
            
            # Start run task
            run_task = asyncio.create_task(manager.run())
            
            # Let it start
            await asyncio.sleep(0.01)
            
            # Trigger shutdown
            manager._shutdown_event.set()
            
            # Wait for completion
            await run_task
            
            # Verify signal handlers were added
            assert mock_loop.add_signal_handler.called