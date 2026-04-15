"""Local LLM Server discovery via hostname probing and port scanning.

Discovers local inference servers (Ollama, llama.cpp, vLLM, LM Studio, LocalAI)
on the network by probing common hostnames and ports.

Uses zeroconf-based mDNS resolution for reliable .local hostname resolution
on all platforms including Android.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

import aiohttp

from ciris_engine.logic.utils.mdns_resolver import (
    DiscoveredService,
    discover_services,
    resolve_local_hostname,
)

logger = logging.getLogger(__name__)

# Hostnames to probe with their likely ports
# See: https://lmstudio.ai/docs/developer/core/server (LM Studio port 1234)
# See: https://docs.ollama.com/faq (Ollama port 11434)
PROBE_HOSTNAMES: List[Tuple[str, List[int]]] = [
    ("jetson.local", [8080, 11434]),  # NVIDIA Jetson with llama.cpp or Ollama
    ("raspberrypi.local", [8080, 11434]),  # Raspberry Pi default hostname
    ("ollama.local", [11434]),  # Dedicated Ollama server
    ("inference.local", [8080, 8000]),  # Generic inference server
    ("llm.local", [11434, 8080]),  # Generic LLM server
    ("lmstudio.local", [1234]),  # LM Studio server (port 1234 default)
    ("vllm.local", [8000]),  # vLLM server
    ("localai.local", [8080]),  # LocalAI server
]

# mDNS service types to browse (emerging standards)
# See: https://github.com/ollama/ollama/issues/10283
LLM_SERVICE_TYPES: List[Tuple[str, str]] = [
    ("_ollama._tcp.local.", "ollama"),  # Proposed Ollama service type
    ("_llm._tcp.local.", "llm"),  # Generic LLM service type
    ("_openai._tcp.local.", "openai_compatible"),  # OpenAI-compatible servers
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


async def _resolve_hostname(hostname: str) -> str:
    """Resolve hostname to IP via mDNS, returning hostname if resolution fails.

    Uses zeroconf-based mDNS resolution for reliable .local hostname
    resolution on all platforms including Android.
    """
    return await resolve_local_hostname(hostname, timeout=2.0)


def _build_server_label(hostname: str, port: int, models: List[str]) -> str:
    """Build a display label for a discovered server."""
    label = f"{hostname}:{port}"
    if models:
        label += f" ({models[0]})" if len(models) == 1 else f" ({len(models)} models)"
    return label


def _build_server_entry(
    hostname: str, port: int, ip: str, server_type: str, model_count: int, models: List[str]
) -> Dict[str, Any]:
    """Build a server entry dict for the discovered servers list."""
    return {
        "id": f"{ip}_{port}",
        "label": _build_server_label(hostname, port, models),
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
    }


def _generate_probe_targets(include_localhost: bool) -> List[Tuple[str, int]]:
    """Generate list of (hostname, port) tuples to probe."""
    targets: List[Tuple[str, int]] = []
    for hostname, ports in PROBE_HOSTNAMES:
        targets.extend((hostname, port) for port in ports)
    if include_localhost:
        targets.extend(("localhost", port) for port, _ in LOCALHOST_PORTS)
    return targets


async def _probe_and_build_entry(
    hostname: str, port: int, seen_urls: set[str]
) -> Optional[Dict[str, Any]]:
    """Probe a single endpoint and return server entry if valid.

    First resolves hostname via mDNS for reliable .local resolution,
    then probes the endpoint to detect LLM server type.
    """
    # Resolve hostname to IP via mDNS first
    logger.info(f"[LLM_DISCOVERY] Resolving {hostname}...")
    ip = await _resolve_hostname(hostname)
    logger.info(f"[LLM_DISCOVERY] Resolved {hostname} -> {ip}")

    # Build URL with resolved IP for reliable connectivity
    url = f"http://{ip}:{port}"
    if url in seen_urls:
        logger.debug(f"[LLM_DISCOVERY] Skipping duplicate URL: {url}")
        return None
    seen_urls.add(url)

    logger.info(f"[LLM_DISCOVERY] Probing {url}...")
    result = await _probe_llm_endpoint(url)
    if not result:
        logger.info(f"[LLM_DISCOVERY] No LLM server found at {url}")
        return None

    server_type, model_count, models = result
    logger.info(f"[LLM_DISCOVERY] Found {server_type} at {url} with {model_count} models")
    return _build_server_entry(hostname, port, ip, server_type, model_count, models)


async def discover_local_llm_servers(
    timeout_seconds: float = 15.0,
    include_localhost: bool = True,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Discover local LLM inference servers on the network.

    Runs all discovery methods in PARALLEL for speed:
    1. mDNS service browsing (all service types in parallel)
    2. Batch hostname resolution (all hostnames in parallel)
    3. HTTP endpoint probing (all endpoints in parallel)

    Args:
        timeout_seconds: Total timeout for all discovery operations
        include_localhost: Whether to probe localhost ports

    Returns:
        Tuple of (discovered_servers, discovery_methods_used)
    """
    import time
    start_time = time.monotonic()

    seen_urls: set[str] = set()
    methods_used: List[str] = []
    all_discovered: List[Dict[str, Any]] = []

    # Generate all probe targets
    targets = _generate_probe_targets(include_localhost)
    unique_hostnames = list(set(h for h, _ in targets if h != "localhost"))

    logger.info(f"[LLM_DISCOVERY] Starting parallel discovery: {len(unique_hostnames)} hostnames, {len(targets)} endpoints")

    # PHASE 1: Run mDNS service browse AND hostname resolution in parallel
    # Use asyncio.wait to get partial results even on timeout
    mdns_task = asyncio.create_task(_discover_via_mdns_services_parallel(1.5, seen_urls))
    resolution_task = asyncio.create_task(_batch_resolve_hostnames(unique_hostnames, timeout=2.0))

    tasks = {mdns_task, resolution_task}
    done, pending = await asyncio.wait(tasks, timeout=6.0)

    # Cancel pending tasks
    for task in pending:
        task.cancel()
        logger.debug(f"[LLM_DISCOVERY] Cancelled pending Phase 1 task")

    # Extract results from completed tasks
    mdns_results: List[Dict[str, Any]] = []
    hostname_map: Dict[str, str] = {}

    for task in done:
        try:
            result = task.result()
            if task is mdns_task and isinstance(result, list):
                mdns_results = result
                logger.info(f"[LLM_DISCOVERY] mDNS task completed with {len(result)} results")
            elif task is resolution_task and isinstance(result, dict):
                hostname_map = result
                logger.info(f"[LLM_DISCOVERY] Resolution task completed with {len(result)} hostnames")
        except Exception as e:
            logger.debug(f"[LLM_DISCOVERY] Phase 1 task failed: {e}")

    # Process mDNS results
    if mdns_results:
        all_discovered.extend(mdns_results)
        methods_used.append("mdns_service_browse")
        logger.info(f"[LLM_DISCOVERY] Found {len(mdns_results)} via mDNS services")

    resolved_count = sum(1 for ip in hostname_map.values() if ip and not ip.endswith(".local"))
    logger.info(f"[LLM_DISCOVERY] Resolved {resolved_count}/{len(unique_hostnames)} hostnames")

    # PHASE 2: Probe ALL endpoints in parallel
    methods_used.append("hostname_probe")
    if include_localhost:
        methods_used.append("localhost_scan")

    # Build probe list with resolved IPs
    probe_tasks: List[asyncio.Task[Optional[Dict[str, Any]]]] = []
    for hostname, port in targets:
        if hostname == "localhost":
            ip = "127.0.0.1"
        else:
            ip = hostname_map.get(hostname, hostname)

        url = f"http://{ip}:{port}"
        if url not in seen_urls:
            seen_urls.add(url)
            probe_tasks.append(asyncio.create_task(
                _probe_endpoint_fast(hostname, port, ip)
            ))

    logger.info(f"[LLM_DISCOVERY] Probing {len(probe_tasks)} unique endpoints...")

    # Wait for probes with remaining timeout
    elapsed = time.monotonic() - start_time
    remaining = max(timeout_seconds - elapsed, 2.0)

    if probe_tasks:
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*probe_tasks, return_exceptions=True),
                timeout=remaining,
            )
            for result in results:  # type: ignore[assignment]
                if isinstance(result, dict):
                    all_discovered.append(result)
        except asyncio.TimeoutError:
            # Cancel pending tasks on timeout
            for task in probe_tasks:  # type: ignore[assignment]
                if not task.done():
                    task.cancel()
            # Collect any results that did complete
            for task in probe_tasks:  # type: ignore[assignment]
                if task.done() and not task.cancelled():
                    try:
                        result = task.result()
                        if isinstance(result, dict):
                            all_discovered.append(result)
                    except Exception:
                        pass
            logger.info(f"[LLM_DISCOVERY] Probe timeout after {remaining:.1f}s")

    elapsed = time.monotonic() - start_time
    logger.info(f"[LLM_DISCOVERY] Discovered {len(all_discovered)} servers in {elapsed:.1f}s")
    return all_discovered, methods_used


async def _batch_resolve_hostnames(
    hostnames: List[str], timeout: float = 3.0
) -> Dict[str, str]:
    """Resolve multiple hostnames in parallel via mDNS.

    Returns dict mapping hostname -> resolved IP (or hostname if failed).
    Uses asyncio.wait to return partial results if some hostnames timeout.
    """
    async def resolve_one(hostname: str) -> Tuple[str, str]:
        try:
            ip = await resolve_local_hostname(hostname, timeout=2.0)
            logger.debug(f"[LLM_DISCOVERY] Resolved {hostname} -> {ip}")
            return (hostname, ip)
        except Exception as e:
            logger.debug(f"[LLM_DISCOVERY] Failed to resolve {hostname}: {e}")
            return (hostname, hostname)

    if not hostnames:
        return {}

    # Create tasks and wait with timeout to get partial results
    tasks = [asyncio.create_task(resolve_one(h)) for h in hostnames]
    done, pending = await asyncio.wait(tasks, timeout=timeout)

    # Cancel pending tasks
    for task in pending:
        task.cancel()

    if pending:
        logger.debug(f"[LLM_DISCOVERY] Hostname resolution: {len(done)} done, {len(pending)} cancelled")

    # Collect results from completed tasks
    hostname_map: Dict[str, str] = {}
    for task in done:
        try:
            result = task.result()
            if isinstance(result, tuple) and len(result) == 2:
                hostname_map[result[0]] = result[1]
        except Exception:
            pass
    return hostname_map


async def _probe_endpoint_fast(
    hostname: str, port: int, ip: str
) -> Optional[Dict[str, Any]]:
    """Probe a single endpoint (IP already resolved)."""
    url = f"http://{ip}:{port}"

    result = await _probe_llm_endpoint(url)
    if not result:
        return None

    server_type, model_count, models = result
    logger.info(f"[LLM_DISCOVERY] Found {server_type} at {url} ({hostname}) with {model_count} models")
    return _build_server_entry(hostname, port, ip, server_type, model_count, models)


async def _discover_via_mdns_services_parallel(
    timeout: float, seen_urls: set[str]
) -> List[Dict[str, Any]]:
    """Discover LLM servers via mDNS - ALL service types in parallel."""

    async def browse_one(service_type: str, server_type: str) -> List[Dict[str, Any]]:
        discovered: List[Dict[str, Any]] = []
        try:
            services: List[DiscoveredService] = await discover_services(
                service_type, timeout=timeout
            )
            for svc in services:
                url = svc.url
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                result = await _probe_llm_endpoint(url)
                if result:
                    actual_type, model_count, models = result
                    entry = _build_server_entry(
                        svc.hostname, svc.port, svc.ip_address,
                        actual_type or server_type, model_count, models,
                    )
                    entry["metadata"]["source"] = "mdns_service"
                    entry["metadata"]["service_type"] = service_type
                    discovered.append(entry)
        except Exception as e:
            logger.debug(f"[LLM_DISCOVERY] Error browsing {service_type}: {e}")
        return discovered

    # Browse ALL service types in parallel
    tasks = [browse_one(st, srv) for st, srv in LLM_SERVICE_TYPES]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_discovered: List[Dict[str, Any]] = []
    for result in results:
        if isinstance(result, list):
            all_discovered.extend(result)

    return all_discovered


async def _probe_llm_endpoint(url: str) -> Optional[Tuple[str, int, List[str]]]:
    """Probe an endpoint to determine if it's an LLM server.

    Uses aiohttp instead of httpx for better timeout reliability on Android.

    Returns:
        Tuple of (server_type, model_count, model_names) if valid, None otherwise
    """
    timeout = aiohttp.ClientTimeout(total=1.5, connect=1.0)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Try Ollama /api/tags first
            try:
                async with session.get(f"{url}/api/tags") as response:
                    if response.status == 200:
                        text = await response.text()
                        data = json.loads(text)
                        models = data.get("models", [])
                        model_names = [m.get("name", "unknown") for m in models]
                        return ("ollama", len(models), model_names)
            except (asyncio.TimeoutError, aiohttp.ClientError):
                pass

            # Try OpenAI-compatible /v1/models
            try:
                async with session.get(f"{url}/v1/models") as response:
                    if response.status == 200:
                        text = await response.text()
                        data = json.loads(text)
                        models = data.get("data", [])
                        model_names = [m.get("id", "unknown") for m in models]
                        server_type = _detect_server_type_from_response(url, data)
                        return (server_type, len(models), model_names)
            except (asyncio.TimeoutError, aiohttp.ClientError):
                pass

            # Try /models (some servers use this)
            try:
                async with session.get(f"{url}/models") as response:
                    if response.status == 200:
                        text = await response.text()
                        data = json.loads(text)
                        if isinstance(data, list):
                            model_names = [m.get("id", str(m)) if isinstance(m, dict) else str(m) for m in data]
                            return ("openai_compatible", len(data), model_names)
                        elif isinstance(data, dict) and "data" in data:
                            models = data.get("data", [])
                            model_names = [m.get("id", "unknown") for m in models]
                            return ("openai_compatible", len(models), model_names)
            except (asyncio.TimeoutError, aiohttp.ClientError):
                pass

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
    confirm_download: bool = False,
) -> Dict[str, Any]:
    """Start a local LLM inference server.

    Attempts to start llama.cpp or Ollama in the background with the
    specified model. The server runs with keepalive enabled.

    Args:
        server_type: "llama_cpp" or "ollama"
        model: Model to load (e.g., "gemma-4-e2b")
        port: Port to listen on
        confirm_download: If True, automatically download missing model.
            If False, return a confirmation prompt for large downloads.

    Returns:
        Dict with success, server_url, pid, message, estimated_ready_seconds.
        If requires_download is True, user should confirm and retry with
        confirm_download=True.
    """
    logger.info(f"[START_LOCAL_SERVER] Starting {server_type} on port {port} with model {model}")

    if server_type == "ollama":
        return await _start_ollama_server(port, model)
    elif server_type == "llama_cpp":
        return await _start_llama_cpp_server(port, model, confirm_download=confirm_download)
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


async def _start_llama_cpp_server(
    port: int, model: str, confirm_download: bool = False
) -> Dict[str, Any]:
    """Start llama.cpp server on the specified port.

    If the model file is not found and confirm_download is False, returns a
    prompt asking user to confirm the download. If confirm_download is True,
    downloads the model automatically.
    """
    binary = _find_llama_cpp_binary()
    if not binary:
        return _error_result(
            "llama.cpp server not found. Build from https://github.com/ggerganov/llama.cpp"
        )

    model_file = _find_model_file(model)
    if not model_file:
        # Model not found - check if user confirmed download
        if not confirm_download:
            # Return download confirmation prompt
            download_size = MODEL_SIZES.get(model, "~2.5 GB")
            return {
                "success": False,
                "requires_download": True,
                "model": model,
                "download_size": download_size,
                "message": f"Model '{model}' not found. Download requires {download_size} of storage. Confirm to proceed.",
                "server_url": None,
                "pid": None,
                "estimated_ready_seconds": None,
            }

        # User confirmed - download the model
        logger.info(f"[START_LOCAL_SERVER] Model '{model}' not found, downloading...")
        download_result = await download_model(model)
        if not download_result["success"]:
            return _error_result(
                f"Model '{model}' download failed: {download_result['message']}"
            )
        model_file = download_result["model_path"]
        logger.info(f"[START_LOCAL_SERVER] Downloaded model to {model_file}")

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
    """Find the llama.cpp server binary.

    On Android, looks for the bundled binary extracted to the app's files directory.
    On desktop, searches PATH and common installation locations.
    """
    import os
    import shutil
    import platform

    # Check for Android bundled binary first
    # The binary is extracted from assets/bin/llama-server-arm64 to files/bin/
    android_paths = []

    # Try to find CIRIS data directory (set by Android app)
    # CIRIS_DATA_DIR is filesDir/ciris, binary is at filesDir/bin
    ciris_data_dir = os.environ.get("CIRIS_DATA_DIR", "")
    if ciris_data_dir:
        # Check in CIRIS_DATA_DIR/bin (if binary was moved there)
        android_paths.append(os.path.join(ciris_data_dir, "bin", "llama-server"))
        # Check in parent/bin (filesDir/bin - where Android extracts it)
        parent_dir = os.path.dirname(ciris_data_dir)
        if parent_dir:
            android_paths.append(os.path.join(parent_dir, "bin", "llama-server"))

    # Also check common Android app data paths
    for pkg in ["ai.ciris.mobile.debug", "ai.ciris.mobile"]:
        android_paths.extend([
            f"/data/data/{pkg}/files/bin/llama-server",
            f"/data/data/{pkg}/files/ciris/bin/llama-server",
        ])

    for path in android_paths:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            logger.info(f"[LLAMA_BINARY] Found Android bundled binary: {path}")
            return path

    # Try common binary names in PATH
    for name in ["llama-server", "llama.cpp-server", "server"]:
        binary = shutil.which(name)
        if binary:
            return binary

    # Check common installation paths (desktop)
    common_paths = [
        "/usr/local/bin/llama-server",
        "/opt/llama.cpp/build/bin/llama-server",
        os.path.expanduser("~/.local/bin/llama-server"),
    ]
    for path in common_paths:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path

    return None


# Model download URLs (HuggingFace)
MODEL_DOWNLOAD_URLS = {
    "gemma-4-e2b": "https://huggingface.co/bartowski/google_gemma-3-4b-it-GGUF/resolve/main/google_gemma-3-4b-it-Q4_K_M.gguf",
    "gemma-4-e4b": "https://huggingface.co/bartowski/google_gemma-3-4b-it-GGUF/resolve/main/google_gemma-3-4b-it-Q8_0.gguf",
}

# Approximate model sizes for user confirmation
MODEL_SIZES = {
    "gemma-4-e2b": "~2.5 GB",
    "gemma-4-e4b": "~4.5 GB",
}


def _get_model_dir() -> str:
    """Get the directory for storing model files."""
    import os
    from pathlib import Path

    # On Android, use CIRIS_DATA_DIR/models
    ciris_data_dir = os.environ.get("CIRIS_DATA_DIR", "")
    if ciris_data_dir:
        model_dir = Path(ciris_data_dir) / "models"
        model_dir.mkdir(parents=True, exist_ok=True)
        return str(model_dir)

    # Desktop: use ~/.cache/llama.cpp
    model_dir = Path.home() / ".cache" / "llama.cpp"
    model_dir.mkdir(parents=True, exist_ok=True)
    return str(model_dir)


def _find_model_file(model: str) -> Optional[str]:
    """Find a GGUF model file on disk.

    Searches common model directories for the specified model.
    """
    import os
    from pathlib import Path

    # Map model names to file patterns
    model_patterns = {
        "gemma-4-e2b": ["gemma-4*-e2b*.gguf", "gemma-2*-e2b*.gguf", "gemma*e2b*.gguf", "google_gemma*.gguf"],
        "gemma-4-e4b": ["gemma-4*-e4b*.gguf", "gemma-2*-e4b*.gguf", "gemma*e4b*.gguf", "google_gemma*Q8*.gguf"],
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

    # Add Android/CIRIS data directory first
    ciris_data_dir = os.environ.get("CIRIS_DATA_DIR", "")
    if ciris_data_dir:
        search_dirs.insert(0, Path(ciris_data_dir) / "models")

    # Add CIRIS_HOME model directory
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


async def download_model(model: str, progress_callback: Optional[Callable[[float], None]] = None) -> Dict[str, Any]:
    """Download a model from HuggingFace.

    Args:
        model: Model name (e.g., "gemma-4-e2b")
        progress_callback: Optional callback for download progress (0.0 to 1.0)

    Returns:
        Dict with success, model_path, message
    """
    import aiohttp
    from pathlib import Path

    url = MODEL_DOWNLOAD_URLS.get(model)
    if not url:
        return {
            "success": False,
            "model_path": None,
            "message": f"No download URL for model '{model}'. Available: {list(MODEL_DOWNLOAD_URLS.keys())}",
        }

    model_dir = _get_model_dir()
    filename = url.split("/")[-1]
    model_path = Path(model_dir) / filename

    # Check if already downloaded
    if model_path.exists():
        logger.info(f"[MODEL_DOWNLOAD] Model already exists: {model_path}")
        return {
            "success": True,
            "model_path": str(model_path),
            "message": f"Model already downloaded: {filename}",
        }

    logger.info(f"[MODEL_DOWNLOAD] Downloading {model} from {url} to {model_path}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return {
                        "success": False,
                        "model_path": None,
                        "message": f"Download failed: HTTP {response.status}",
                    }

                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0

                with open(model_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(1024 * 1024):  # 1MB chunks
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size > 0:
                            progress_callback(downloaded / total_size)

        logger.info(f"[MODEL_DOWNLOAD] Download complete: {model_path}")
        return {
            "success": True,
            "model_path": str(model_path),
            "message": f"Downloaded {filename} ({downloaded / 1024 / 1024:.1f} MB)",
        }

    except Exception as e:
        logger.error(f"[MODEL_DOWNLOAD] Failed to download model: {e}")
        # Clean up partial download
        if model_path.exists():
            model_path.unlink()
        return {
            "success": False,
            "model_path": None,
            "message": f"Download failed: {str(e)}",
        }
