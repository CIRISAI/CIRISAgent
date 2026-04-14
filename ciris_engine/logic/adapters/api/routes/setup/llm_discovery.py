"""Local LLM Server discovery via hostname probing and port scanning.

Discovers local inference servers (Ollama, llama.cpp, vLLM, LM Studio, LocalAI)
on the network by probing common hostnames and ports.
"""

import asyncio
import logging
import socket
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# Hostnames to probe with their likely ports
PROBE_HOSTNAMES: List[Tuple[str, List[int]]] = [
    ("jetson.local", [8080, 11434]),  # NVIDIA Jetson with llama.cpp or Ollama
    ("ollama.local", [11434]),  # Dedicated Ollama server
    ("inference.local", [8080, 8000]),  # Generic inference server
    ("llm.local", [11434, 8080]),  # Generic LLM server
    ("lmstudio.local", [1234]),  # LM Studio server
    ("vllm.local", [8000]),  # vLLM server
    ("localai.local", [8080]),  # LocalAI server
]

# Localhost ports to scan (always checked)
LOCALHOST_PORTS: List[Tuple[int, str]] = [
    (11434, "ollama"),  # Ollama default
    (1234, "lmstudio"),  # LM Studio default
    (8000, "vllm"),  # vLLM default
    (8080, "llama_cpp"),  # llama.cpp / LocalAI default
]

# Timeout for individual probes
PROBE_TIMEOUT = 2.0


async def discover_local_llm_servers(
    timeout_seconds: float = 5.0,
    include_localhost: bool = True,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Discover local LLM inference servers on the network.

    Uses hostname probing and port scanning to find running LLM servers.

    Args:
        timeout_seconds: Total timeout for all discovery operations
        include_localhost: Whether to probe localhost ports

    Returns:
        Tuple of (discovered_servers, discovery_methods_used)
    """
    discovered: List[Dict[str, Any]] = []
    methods_used: List[str] = []
    seen_urls: set[str] = set()

    async def add_if_valid(url: str, hostname: str, port: int) -> None:
        """Probe a URL and add to discovered if it's a valid LLM server."""
        if url in seen_urls:
            return
        seen_urls.add(url)

        result = await _probe_llm_endpoint(url)
        if result:
            server_type, model_count, models = result
            # Resolve hostname to IP for reliability
            try:
                ip = socket.gethostbyname(hostname)
            except socket.gaierror:
                ip = hostname

            server_id = f"{ip}_{port}"
            label = f"{hostname}:{port}"
            if models:
                label += f" ({models[0]})" if len(models) == 1 else f" ({len(models)} models)"

            discovered.append({
                "id": server_id,
                "label": label,
                "url": f"http://{ip}:{port}",
                "server_type": server_type,
                "model_count": model_count,
                "models": models,
                "metadata": {
                    "hostname": hostname,
                    "ip": ip,
                    "port": port,
                    "source": "hostname_probe" if hostname != "localhost" else "localhost_scan",
                },
            })

    # Probe hostnames in parallel
    tasks = []
    for hostname, ports in PROBE_HOSTNAMES:
        for port in ports:
            url = f"http://{hostname}:{port}"
            tasks.append(add_if_valid(url, hostname, port))
    methods_used.append("hostname_probe")

    # Probe localhost ports
    if include_localhost:
        for port, _ in LOCALHOST_PORTS:
            url = f"http://localhost:{port}"
            tasks.append(add_if_valid(url, "localhost", port))
        methods_used.append("localhost_scan")

    # Run all probes with overall timeout
    try:
        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        logger.warning("[LLM_DISCOVERY] Overall timeout reached during discovery")

    logger.info(f"[LLM_DISCOVERY] Discovered {len(discovered)} LLM servers")
    return discovered, methods_used


async def _probe_llm_endpoint(url: str) -> Optional[Tuple[str, int, List[str]]]:
    """Probe an endpoint to determine if it's an LLM server.

    Returns:
        Tuple of (server_type, model_count, model_names) if valid, None otherwise
    """
    async with httpx.AsyncClient(timeout=PROBE_TIMEOUT) as client:
        # Try Ollama /api/tags first
        try:
            response = await client.get(f"{url}/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                model_names = [m.get("name", "unknown") for m in models]
                return ("ollama", len(models), model_names)
        except Exception as exc:
            # Not an Ollama server (or unreachable) — fall through to next probe.
            logger.debug("[LLM_DISCOVERY] Ollama probe failed for %s/api/tags: %s", url, exc)

        # Try OpenAI-compatible /v1/models
        try:
            response = await client.get(f"{url}/v1/models")
            if response.status_code == 200:
                data = response.json()
                models = data.get("data", [])
                model_names = [m.get("id", "unknown") for m in models]

                # Detect server type by response characteristics
                server_type = _detect_server_type_from_response(url, data)
                return (server_type, len(models), model_names)
        except Exception as exc:
            # Not an OpenAI-compatible /v1/models server — fall through.
            logger.debug("[LLM_DISCOVERY] /v1/models probe failed for %s: %s", url, exc)

        # Try /models (some servers use this)
        try:
            response = await client.get(f"{url}/models")
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    model_names = [m.get("id", str(m)) if isinstance(m, dict) else str(m) for m in data]
                    return ("openai_compatible", len(data), model_names)
                elif isinstance(data, dict) and "data" in data:
                    models = data.get("data", [])
                    model_names = [m.get("id", "unknown") for m in models]
                    return ("openai_compatible", len(models), model_names)
        except Exception as exc:
            # Final probe — return None below if we get here without a hit.
            logger.debug("[LLM_DISCOVERY] /models probe failed for %s: %s", url, exc)

    return None


def _detect_server_type_from_response(url: str, data: Dict[str, Any]) -> str:
    """Detect server type from response data and URL patterns."""
    # Check URL port for hints
    if ":11434" in url:
        return "ollama"
    if ":1234" in url:
        return "lmstudio"
    if ":8000" in url:
        return "vllm"

    # Check response for hints
    models = data.get("data", [])
    if models:
        first_model = models[0]
        # vLLM includes 'max_model_len' in model info
        if "max_model_len" in first_model:
            return "vllm"
        # LM Studio includes 'publisher' field
        if "publisher" in first_model:
            return "lmstudio"

    # Default to generic llama.cpp/OpenAI-compatible
    return "llama_cpp"


async def start_local_llm_server(
    server_type: str = "llama_cpp",
    model: str = "gemma-4-e2b",
    port: int = 8080,
) -> Dict[str, Any]:
    """Start a local LLM inference server.

    Attempts to start llama.cpp or Ollama in the background with the
    specified model. The server runs with keepalive enabled.

    Args:
        server_type: "llama_cpp" or "ollama"
        model: Model to load (e.g., "gemma-4-e2b")
        port: Port to listen on

    Returns:
        Dict with success, server_url, pid, message, estimated_ready_seconds
    """
    logger.info(f"[START_LOCAL_SERVER] Starting {server_type} on port {port} with model {model}")

    if server_type == "ollama":
        return await _start_ollama_server(port, model)
    elif server_type == "llama_cpp":
        return await _start_llama_cpp_server(port, model)
    else:
        return _error_result(f"Unknown server type: {server_type}. Use 'llama_cpp' or 'ollama'.")


def _error_result(message: str) -> Dict[str, Any]:
    """Create an error result dict."""
    return {"success": False, "message": message, "estimated_ready_seconds": 0}


def _success_result(port: int, pid: int, message: str, ready_seconds: int) -> Dict[str, Any]:
    """Create a success result dict."""
    return {
        "success": True,
        "server_url": f"http://127.0.0.1:{port}",
        "pid": pid,
        "message": message,
        "estimated_ready_seconds": ready_seconds,
    }


async def _start_ollama_server(port: int, model: str) -> Dict[str, Any]:
    """Start Ollama server on the specified port."""
    import os
    import shutil

    binary = shutil.which("ollama")
    if not binary:
        return _error_result("Ollama not found. Install from https://ollama.ai")

    try:
        env = os.environ.copy()
        env["OLLAMA_HOST"] = f"127.0.0.1:{port}"

        process = await asyncio.create_subprocess_exec(
            binary, "serve",
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )

        return _success_result(
            port, process.pid or 0,
            f"Ollama server started on port {port}. Pull model with: ollama pull {model}",
            ready_seconds=30,
        )
    except Exception as e:
        logger.error(f"[START_LOCAL_SERVER] Failed to start Ollama: {e}")
        return _error_result(f"Failed to start Ollama: {str(e)}")


async def _start_llama_cpp_server(port: int, model: str) -> Dict[str, Any]:
    """Start llama.cpp server on the specified port."""
    binary = _find_llama_cpp_binary()
    if not binary:
        return _error_result(
            "llama.cpp server not found. Build from https://github.com/ggerganov/llama.cpp"
        )

    model_file = _find_model_file(model)
    if not model_file:
        return _error_result(f"Model file for '{model}' not found. Download GGUF from HuggingFace.")

    try:
        process = await asyncio.create_subprocess_exec(
            binary,
            "--model", model_file,
            "--host", "127.0.0.1",
            "--port", str(port),
            "--ctx-size", "8192",
            "--n-gpu-layers", "99",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )

        return _success_result(
            port, process.pid or 0,
            f"llama.cpp server started with {model}. Loading model...",
            ready_seconds=60,
        )
    except Exception as e:
        logger.error(f"[START_LOCAL_SERVER] Failed to start llama.cpp: {e}")
        return _error_result(f"Failed to start llama.cpp: {str(e)}")


def _find_llama_cpp_binary() -> Optional[str]:
    """Find the llama.cpp server binary."""
    import os
    import shutil

    # Try common binary names
    for name in ["llama-server", "llama.cpp-server", "server"]:
        binary = shutil.which(name)
        if binary:
            return binary

    # Check common installation paths
    common_paths = [
        "/usr/local/bin/llama-server",
        "/opt/llama.cpp/build/bin/llama-server",
        os.path.expanduser("~/.local/bin/llama-server"),
    ]
    for path in common_paths:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path

    return None


def _find_model_file(model: str) -> Optional[str]:
    """Find a GGUF model file on disk.

    Searches common model directories for the specified model.
    """
    import os
    from pathlib import Path

    # Map model names to file patterns
    model_patterns = {
        "gemma-4-e2b": ["gemma-4*-e2b*.gguf", "gemma-2*-e2b*.gguf", "gemma*e2b*.gguf"],
        "gemma-4-e4b": ["gemma-4*-e4b*.gguf", "gemma-2*-e4b*.gguf", "gemma*e4b*.gguf"],
    }

    patterns = model_patterns.get(model, [f"*{model}*.gguf"])

    # Common model directories
    search_dirs = [
        Path.home() / ".cache" / "llama.cpp",
        Path.home() / ".local" / "share" / "llama.cpp" / "models",
        Path.home() / "models",
        Path("/usr/share/llama.cpp/models"),
        Path("/opt/models"),
    ]

    # Add CIRIS model directory
    ciris_home = os.environ.get("CIRIS_HOME")
    if ciris_home:
        search_dirs.insert(0, Path(ciris_home) / "models")

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for pattern in patterns:
            matches = list(search_dir.glob(pattern))
            if matches:
                # Return the first match
                return str(matches[0])

    return None
