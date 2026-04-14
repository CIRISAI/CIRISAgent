"""Tests for local LLM server discovery module."""

from __future__ import annotations

import asyncio
import socket
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ciris_engine.logic.adapters.api.routes.setup.llm_discovery import (
    LOCALHOST_PORTS,
    PROBE_HOSTNAMES,
    _build_server_entry,
    _build_server_label,
    _detect_server_type_from_response,
    _error_result,
    _find_llama_cpp_binary,
    _find_model_file,
    _generate_probe_targets,
    _probe_and_build_entry,
    _probe_llm_endpoint,
    _resolve_hostname,
    _start_llama_cpp_server,
    _start_ollama_server,
    _success_result,
    discover_local_llm_servers,
    start_local_llm_server,
)


class TestResolveHostname:
    """Tests for _resolve_hostname function."""

    def test_resolve_hostname_success(self) -> None:
        """Test successful hostname resolution."""
        with patch("socket.gethostbyname", return_value="192.168.1.100"):
            result = _resolve_hostname("jetson.local")
            assert result == "192.168.1.100"

    def test_resolve_hostname_failure_returns_hostname(self) -> None:
        """Test that failed resolution returns the original hostname."""
        with patch("socket.gethostbyname", side_effect=socket.gaierror):
            result = _resolve_hostname("nonexistent.local")
            assert result == "nonexistent.local"

    def test_resolve_localhost(self) -> None:
        """Test resolving localhost."""
        with patch("socket.gethostbyname", return_value="127.0.0.1"):
            result = _resolve_hostname("localhost")
            assert result == "127.0.0.1"


class TestBuildServerLabel:
    """Tests for _build_server_label function."""

    def test_label_no_models(self) -> None:
        """Test label with no models."""
        label = _build_server_label("jetson.local", 8080, [])
        assert label == "jetson.local:8080"

    def test_label_single_model(self) -> None:
        """Test label with single model."""
        label = _build_server_label("jetson.local", 8080, ["gemma-4-e2b"])
        assert label == "jetson.local:8080 (gemma-4-e2b)"

    def test_label_multiple_models(self) -> None:
        """Test label with multiple models."""
        label = _build_server_label("localhost", 11434, ["llama3", "mistral", "phi3"])
        assert label == "localhost:11434 (3 models)"

    def test_label_two_models(self) -> None:
        """Test label with exactly two models."""
        label = _build_server_label("ollama.local", 11434, ["model1", "model2"])
        assert label == "ollama.local:11434 (2 models)"


class TestBuildServerEntry:
    """Tests for _build_server_entry function."""

    def test_build_entry_hostname_probe(self) -> None:
        """Test building entry from hostname probe."""
        entry = _build_server_entry(
            hostname="jetson.local",
            port=8080,
            ip="192.168.1.100",
            server_type="llama_cpp",
            model_count=1,
            models=["gemma-4-e2b"],
        )
        assert entry["id"] == "192.168.1.100_8080"
        assert entry["url"] == "http://192.168.1.100:8080"
        assert entry["server_type"] == "llama_cpp"
        assert entry["model_count"] == 1
        assert entry["models"] == ["gemma-4-e2b"]
        assert entry["metadata"]["source"] == "hostname_probe"
        assert entry["metadata"]["hostname"] == "jetson.local"
        assert entry["metadata"]["ip"] == "192.168.1.100"
        assert entry["metadata"]["port"] == 8080

    def test_build_entry_localhost_scan(self) -> None:
        """Test building entry from localhost scan."""
        entry = _build_server_entry(
            hostname="localhost",
            port=11434,
            ip="127.0.0.1",
            server_type="ollama",
            model_count=3,
            models=["llama3", "mistral", "phi3"],
        )
        assert entry["id"] == "127.0.0.1_11434"
        assert entry["metadata"]["source"] == "localhost_scan"


class TestGenerateProbeTargets:
    """Tests for _generate_probe_targets function."""

    def test_with_localhost(self) -> None:
        """Test target generation including localhost."""
        targets = _generate_probe_targets(include_localhost=True)
        # Should include all hostname targets plus localhost ports
        hostname_count = sum(len(ports) for _, ports in PROBE_HOSTNAMES)
        localhost_count = len(LOCALHOST_PORTS)
        assert len(targets) == hostname_count + localhost_count
        # Check localhost is included
        assert ("localhost", 11434) in targets
        assert ("localhost", 8080) in targets

    def test_without_localhost(self) -> None:
        """Test target generation excluding localhost."""
        targets = _generate_probe_targets(include_localhost=False)
        hostname_count = sum(len(ports) for _, ports in PROBE_HOSTNAMES)
        assert len(targets) == hostname_count
        # Check localhost is not included
        assert not any(h == "localhost" for h, _ in targets)

    def test_includes_known_hostnames(self) -> None:
        """Test that known hostnames are included."""
        targets = _generate_probe_targets(include_localhost=True)
        hostnames = {h for h, _ in targets}
        assert "jetson.local" in hostnames
        assert "ollama.local" in hostnames


class TestDetectServerTypeFromResponse:
    """Tests for _detect_server_type_from_response function."""

    def test_detect_ollama_by_port(self) -> None:
        """Test detecting Ollama by port number."""
        result = _detect_server_type_from_response("http://localhost:11434", {})
        assert result == "ollama"

    def test_detect_lmstudio_by_port(self) -> None:
        """Test detecting LM Studio by port number."""
        result = _detect_server_type_from_response("http://localhost:1234", {})
        assert result == "lmstudio"

    def test_detect_vllm_by_port(self) -> None:
        """Test detecting vLLM by port number."""
        result = _detect_server_type_from_response("http://localhost:8000", {})
        assert result == "vllm"

    def test_detect_vllm_by_response(self) -> None:
        """Test detecting vLLM by response characteristics."""
        data = {"data": [{"id": "model", "max_model_len": 4096}]}
        result = _detect_server_type_from_response("http://localhost:9000", data)
        assert result == "vllm"

    def test_detect_lmstudio_by_response(self) -> None:
        """Test detecting LM Studio by response characteristics."""
        data = {"data": [{"id": "model", "publisher": "TheBloke"}]}
        result = _detect_server_type_from_response("http://localhost:9000", data)
        assert result == "lmstudio"

    def test_default_to_llama_cpp(self) -> None:
        """Test default to llama_cpp when no hints found."""
        data = {"data": [{"id": "model"}]}
        result = _detect_server_type_from_response("http://localhost:9000", data)
        assert result == "llama_cpp"

    def test_empty_models_list(self) -> None:
        """Test with empty models list."""
        result = _detect_server_type_from_response("http://localhost:9000", {"data": []})
        assert result == "llama_cpp"


class TestResultHelpers:
    """Tests for _error_result and _success_result functions."""

    def test_error_result(self) -> None:
        """Test error result creation."""
        result = _error_result("Something went wrong")
        assert result["success"] is False
        assert result["message"] == "Something went wrong"
        assert result["estimated_ready_seconds"] == 0
        assert "server_url" not in result
        assert "pid" not in result

    def test_success_result(self) -> None:
        """Test success result creation."""
        result = _success_result(8080, 12345, "Server started", 30)
        assert result["success"] is True
        assert result["server_url"] == "http://127.0.0.1:8080"
        assert result["pid"] == 12345
        assert result["message"] == "Server started"
        assert result["estimated_ready_seconds"] == 30


class TestProbeLlmEndpoint:
    """Tests for _probe_llm_endpoint function."""

    @pytest.mark.asyncio
    async def test_probe_ollama_server(self) -> None:
        """Test probing an Ollama server."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [{"name": "llama3"}, {"name": "mistral"}]
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await _probe_llm_endpoint("http://localhost:11434")

            assert result is not None
            server_type, model_count, models = result
            assert server_type == "ollama"
            assert model_count == 2
            assert models == ["llama3", "mistral"]

    @pytest.mark.asyncio
    async def test_probe_openai_compatible_v1_models(self) -> None:
        """Test probing an OpenAI-compatible /v1/models endpoint."""
        # First call (Ollama) returns 404, second call (/v1/models) returns models
        mock_404 = MagicMock()
        mock_404.status_code = 404

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {
            "data": [{"id": "gpt-3.5-turbo"}, {"id": "gpt-4"}]
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.side_effect = [mock_404, mock_200]
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await _probe_llm_endpoint("http://localhost:8080")

            assert result is not None
            server_type, model_count, models = result
            assert server_type == "llama_cpp"
            assert model_count == 2
            assert models == ["gpt-3.5-turbo", "gpt-4"]

    @pytest.mark.asyncio
    async def test_probe_models_endpoint_list_response(self) -> None:
        """Test probing /models endpoint with list response."""
        mock_404 = MagicMock()
        mock_404.status_code = 404

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = [{"id": "model1"}, {"id": "model2"}]

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            # Ollama fails, /v1/models fails, /models succeeds
            mock_client.get.side_effect = [mock_404, mock_404, mock_200]
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await _probe_llm_endpoint("http://localhost:9000")

            assert result is not None
            server_type, model_count, models = result
            assert server_type == "openai_compatible"
            assert model_count == 2

    @pytest.mark.asyncio
    async def test_probe_models_endpoint_dict_response(self) -> None:
        """Test probing /models endpoint with dict response containing data."""
        mock_404 = MagicMock()
        mock_404.status_code = 404

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {"data": [{"id": "model1"}]}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.side_effect = [mock_404, mock_404, mock_200]
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await _probe_llm_endpoint("http://localhost:9000")

            assert result is not None
            assert result[0] == "openai_compatible"

    @pytest.mark.asyncio
    async def test_probe_all_endpoints_fail(self) -> None:
        """Test when all probe endpoints fail."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("Connection refused")
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await _probe_llm_endpoint("http://localhost:9999")

            assert result is None


class TestProbeAndBuildEntry:
    """Tests for _probe_and_build_entry function."""

    @pytest.mark.asyncio
    async def test_skips_seen_urls(self) -> None:
        """Test that already-seen URLs are skipped."""
        seen_urls: set[str] = {"http://localhost:8080"}
        result = await _probe_and_build_entry("localhost", 8080, seen_urls)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_probe_failure(self) -> None:
        """Test that None is returned when probe fails."""
        seen_urls: set[str] = set()
        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.llm_discovery._probe_llm_endpoint",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await _probe_and_build_entry("localhost", 9999, seen_urls)
            assert result is None
            assert "http://localhost:9999" in seen_urls

    @pytest.mark.asyncio
    async def test_builds_entry_on_success(self) -> None:
        """Test building entry on successful probe."""
        seen_urls: set[str] = set()
        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.llm_discovery._probe_llm_endpoint",
            new_callable=AsyncMock,
            return_value=("ollama", 2, ["llama3", "mistral"]),
        ), patch(
            "ciris_engine.logic.adapters.api.routes.setup.llm_discovery._resolve_hostname",
            return_value="127.0.0.1",
        ):
            result = await _probe_and_build_entry("localhost", 11434, seen_urls)

            assert result is not None
            assert result["server_type"] == "ollama"
            assert result["model_count"] == 2
            assert "http://localhost:11434" in seen_urls


class TestDiscoverLocalLlmServers:
    """Tests for discover_local_llm_servers function."""

    @pytest.mark.asyncio
    async def test_discovery_with_no_servers(self) -> None:
        """Test discovery when no servers are found."""
        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.llm_discovery._probe_and_build_entry",
            new_callable=AsyncMock,
            return_value=None,
        ):
            servers, methods = await discover_local_llm_servers(timeout_seconds=1.0)

            assert servers == []
            assert "hostname_probe" in methods
            assert "localhost_scan" in methods

    @pytest.mark.asyncio
    async def test_discovery_without_localhost(self) -> None:
        """Test discovery excluding localhost."""
        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.llm_discovery._probe_and_build_entry",
            new_callable=AsyncMock,
            return_value=None,
        ):
            servers, methods = await discover_local_llm_servers(
                timeout_seconds=1.0, include_localhost=False
            )

            assert "hostname_probe" in methods
            assert "localhost_scan" not in methods

    @pytest.mark.asyncio
    async def test_discovery_returns_found_servers(self) -> None:
        """Test discovery returns found servers."""
        mock_entry = {
            "id": "127.0.0.1_11434",
            "label": "localhost:11434 (llama3)",
            "url": "http://127.0.0.1:11434",
            "server_type": "ollama",
            "model_count": 1,
            "models": ["llama3"],
            "metadata": {},
        }

        async def mock_probe(h: str, p: int, seen: set[str]) -> Dict[str, Any] | None:
            if h == "localhost" and p == 11434:
                return mock_entry
            return None

        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.llm_discovery._probe_and_build_entry",
            side_effect=mock_probe,
        ):
            servers, methods = await discover_local_llm_servers(timeout_seconds=1.0)

            assert len(servers) == 1
            assert servers[0]["server_type"] == "ollama"

    @pytest.mark.asyncio
    async def test_discovery_handles_timeout(self) -> None:
        """Test that discovery handles timeout gracefully."""

        async def slow_probe(h: str, p: int, seen: set[str]) -> None:
            await asyncio.sleep(10)  # Longer than timeout
            return None

        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.llm_discovery._probe_and_build_entry",
            side_effect=slow_probe,
        ):
            servers, methods = await discover_local_llm_servers(timeout_seconds=0.1)

            # Should return empty list due to timeout
            assert servers == []


class TestStartLocalLlmServer:
    """Tests for start_local_llm_server function."""

    @pytest.mark.asyncio
    async def test_unknown_server_type(self) -> None:
        """Test starting unknown server type."""
        result = await start_local_llm_server(server_type="unknown")

        assert result["success"] is False
        assert "Unknown server type" in result["message"]

    @pytest.mark.asyncio
    async def test_start_ollama_dispatches(self) -> None:
        """Test that ollama type dispatches to _start_ollama_server."""
        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.llm_discovery._start_ollama_server",
            new_callable=AsyncMock,
            return_value={"success": True},
        ) as mock_start:
            result = await start_local_llm_server(server_type="ollama", port=11434)

            mock_start.assert_called_once_with(11434, "gemma-4-e2b")
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_start_llama_cpp_dispatches(self) -> None:
        """Test that llama_cpp type dispatches to _start_llama_cpp_server."""
        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.llm_discovery._start_llama_cpp_server",
            new_callable=AsyncMock,
            return_value={"success": True},
        ) as mock_start:
            result = await start_local_llm_server(
                server_type="llama_cpp", model="gemma-4-e4b", port=8080
            )

            mock_start.assert_called_once_with(8080, "gemma-4-e4b")


class TestStartOllamaServer:
    """Tests for _start_ollama_server function."""

    @pytest.mark.asyncio
    async def test_ollama_not_found(self) -> None:
        """Test when ollama binary is not found."""
        with patch("shutil.which", return_value=None):
            result = await _start_ollama_server(11434, "llama3")

            assert result["success"] is False
            assert "Ollama not found" in result["message"]

    @pytest.mark.asyncio
    async def test_ollama_start_success(self) -> None:
        """Test successful ollama server start."""
        mock_process = MagicMock()
        mock_process.pid = 12345

        with patch("shutil.which", return_value="/usr/bin/ollama"), patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process
        ):
            result = await _start_ollama_server(11434, "llama3")

            assert result["success"] is True
            assert result["pid"] == 12345
            assert result["server_url"] == "http://127.0.0.1:11434"

    @pytest.mark.asyncio
    async def test_ollama_start_exception(self) -> None:
        """Test ollama start with exception."""
        with patch("shutil.which", return_value="/usr/bin/ollama"), patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            side_effect=OSError("Permission denied"),
        ):
            result = await _start_ollama_server(11434, "llama3")

            assert result["success"] is False
            assert "Permission denied" in result["message"]


class TestStartLlamaCppServer:
    """Tests for _start_llama_cpp_server function."""

    @pytest.mark.asyncio
    async def test_binary_not_found(self) -> None:
        """Test when llama.cpp binary is not found."""
        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.llm_discovery._find_llama_cpp_binary",
            return_value=None,
        ):
            result = await _start_llama_cpp_server(8080, "gemma-4-e2b")

            assert result["success"] is False
            assert "llama.cpp server not found" in result["message"]

    @pytest.mark.asyncio
    async def test_model_not_found(self) -> None:
        """Test when model file is not found."""
        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.llm_discovery._find_llama_cpp_binary",
            return_value="/usr/bin/llama-server",
        ), patch(
            "ciris_engine.logic.adapters.api.routes.setup.llm_discovery._find_model_file",
            return_value=None,
        ):
            result = await _start_llama_cpp_server(8080, "nonexistent")

            assert result["success"] is False
            assert "Model file" in result["message"]

    @pytest.mark.asyncio
    async def test_llama_cpp_start_success(self) -> None:
        """Test successful llama.cpp server start."""
        mock_process = MagicMock()
        mock_process.pid = 54321

        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.llm_discovery._find_llama_cpp_binary",
            return_value="/usr/bin/llama-server",
        ), patch(
            "ciris_engine.logic.adapters.api.routes.setup.llm_discovery._find_model_file",
            return_value="/models/gemma.gguf",
        ), patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process
        ):
            result = await _start_llama_cpp_server(8080, "gemma-4-e2b")

            assert result["success"] is True
            assert result["pid"] == 54321
            assert result["estimated_ready_seconds"] == 60


class TestFindLlamaCppBinary:
    """Tests for _find_llama_cpp_binary function."""

    def test_find_via_which(self) -> None:
        """Test finding binary via shutil.which."""
        with patch("shutil.which", side_effect=lambda n: "/usr/bin/llama-server" if n == "llama-server" else None):
            result = _find_llama_cpp_binary()
            assert result == "/usr/bin/llama-server"

    def test_find_via_common_paths(self) -> None:
        """Test finding binary in common paths."""
        with patch("shutil.which", return_value=None), patch(
            "os.path.isfile", side_effect=lambda p: p == "/usr/local/bin/llama-server"
        ), patch("os.access", return_value=True):
            result = _find_llama_cpp_binary()
            assert result == "/usr/local/bin/llama-server"

    def test_not_found(self) -> None:
        """Test when binary is not found anywhere."""
        with patch("shutil.which", return_value=None), patch(
            "os.path.isfile", return_value=False
        ):
            result = _find_llama_cpp_binary()
            assert result is None


class TestFindModelFile:
    """Tests for _find_model_file function."""

    def test_find_known_model(self, tmp_path: Any) -> None:
        """Test finding a known model pattern."""
        # Create a mock model file
        model_dir = tmp_path / ".cache" / "llama.cpp"
        model_dir.mkdir(parents=True)
        model_file = model_dir / "gemma-4-e2b-Q4_K_M.gguf"
        model_file.touch()

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = _find_model_file("gemma-4-e2b")
            assert result is not None
            assert "gemma" in result

    def test_find_custom_model(self, tmp_path: Any) -> None:
        """Test finding a custom model pattern."""
        model_dir = tmp_path / ".cache" / "llama.cpp"
        model_dir.mkdir(parents=True)
        model_file = model_dir / "custom-model.gguf"
        model_file.touch()

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = _find_model_file("custom-model")
            assert result is not None

    def test_model_not_found(self, tmp_path: Any) -> None:
        """Test when model is not found."""
        with patch("pathlib.Path.home", return_value=tmp_path):
            result = _find_model_file("nonexistent-model")
            assert result is None

    def test_ciris_home_priority(self, tmp_path: Any) -> None:
        """Test that CIRIS_HOME model directory has priority."""
        ciris_models = tmp_path / "ciris" / "models"
        ciris_models.mkdir(parents=True)
        model_file = ciris_models / "gemma-4-e2b.gguf"
        model_file.touch()

        with patch.dict("os.environ", {"CIRIS_HOME": str(tmp_path / "ciris")}), patch(
            "pathlib.Path.home", return_value=tmp_path
        ):
            result = _find_model_file("gemma-4-e2b")
            assert result is not None
            assert "ciris" in result
