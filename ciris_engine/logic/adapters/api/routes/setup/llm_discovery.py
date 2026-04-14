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
        except Exception:
            pass

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
        except Exception:
            pass

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
        except Exception:
            pass

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
        first_model = models[0] if models else {}
        # vLLM includes 'max_model_len' in model info
        if "max_model_len" in first_model:
            return "vllm"
        # LM Studio includes 'publisher' field
        if "publisher" in first_model:
            return "lmstudio"

    # Default to generic llama.cpp/OpenAI-compatible
    return "llama_cpp"
