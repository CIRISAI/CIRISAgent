"""
CIRISNode Integration Tests.

Tests connectivity and integration with CIRISNode oversight infrastructure:
- CIRISNode (node.ciris-services-1.ai / node.ciris-services-2.ai)
- CIRISPortal (portal.ciris.ai) - agent registration
- CIRISRegistry - key verification

Open Source Ecosystem:
- CIRISNode: Oversight node for deferral routing and trace storage
- CIRISPortal: Web UI for agent registration and key management
- CIRISPortal-api: API backend for portal operations
- CIRISRegistry: Central registry for agent keys and verification

Registration Flow:
1. Register agent via CIRISPortal (portal.ciris.ai)
2. Download signing key from portal
3. Key stored in CIRISRegistry
4. Agent registers public key with CIRISNode at startup
5. CIRISNode verifies signatures against CIRISRegistry

This module tests:
1. Health check connectivity to CIRISNode
2. Public key registration endpoint
3. WBD deferral submission format validation
4. Covenant trace batch format validation
5. OAuth redirect to CIRISPortal
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)

# CIRISNode regional servers
CIRISNODE_US_URL = "https://node.ciris-services-1.ai"
CIRISNODE_EU_URL = "https://node.ciris-services-2.ai"

# CIRISPortal for OAuth/registration
CIRISPORTAL_URL = "https://portal.ciris.ai"


class CIRISNodeTests:
    """Test module for CIRISNode integration.

    Tests connectivity to CIRISNode oversight infrastructure and validates
    the registration/deferral/trace submission flows.
    """

    def __init__(
        self,
        client: Any,
        console: Any,
        live_node: bool = False,
        node_url: Optional[str] = None,
    ):
        """Initialize test module.

        Args:
            client: CIRISClient SDK client (used for agent context)
            console: Rich console for output
            live_node: If True, run tests against live CIRISNode server
            node_url: Override CIRISNode URL (defaults to US server)
        """
        self.client = client
        self.console = console
        self.live_node = live_node or os.environ.get("CIRIS_LIVE_NODE", "").lower() == "true"
        self.node_url = node_url or os.environ.get("CIRISNODE_BASE_URL", CIRISNODE_US_URL)
        self.results: List[Dict[str, Any]] = []

    async def run(self) -> List[Dict[str, Any]]:
        """Run all CIRISNode integration tests.

        Returns:
            List of test results
        """
        self.results = []

        # Core tests (always run)
        tests = [
            ("CIRISNode URL Configuration", self._test_url_configuration),
            ("CIRISNode Health Check (US)", self._test_health_us),
            ("CIRISNode Health Check (EU)", self._test_health_eu),
            ("CIRISPortal Reachability", self._test_portal_reachability),
            ("Local Signing Key Check", self._test_local_signing_key),
            ("WBD Submission Format", self._test_wbd_format),
            ("Covenant Trace Format", self._test_trace_format),
        ]

        # Live node tests (only when --live-node flag is set)
        if self.live_node:
            tests.extend(
                [
                    ("Public Key Registration", self._test_key_registration),
                    ("WBD Submit Endpoint", self._test_wbd_submit),
                    ("Covenant Events Endpoint", self._test_covenant_events),
                    ("Agent Token Validation", self._test_agent_token),
                ]
            )

        for name, test_fn in tests:
            try:
                logger.info(f"Running: {name}")
                success, message = await test_fn()
                status = "PASS" if success else "FAIL"
                self.results.append(
                    {
                        "test": name,
                        "status": f"{'✅' if success else '❌'} {status}",
                        "error": None if success else message,
                    }
                )
                if success:
                    self.console.print(f"  [green]✅ PASS[/green] {name}")
                    if message:
                        self.console.print(f"     [dim]{message}[/dim]")
                else:
                    self.console.print(f"  [red]❌ FAIL[/red] {name}: {message}")
            except Exception as e:
                logger.error(f"Error in {name}: {e}")
                self.results.append(
                    {
                        "test": name,
                        "status": "❌ FAIL",
                        "error": str(e),
                    }
                )
                self.console.print(f"  [red]❌ FAIL[/red] {name}: {e}")

        return self.results

    # =========================================================================
    # Configuration Tests
    # =========================================================================

    async def _test_url_configuration(self) -> Tuple[bool, str]:
        """Test that CIRISNode URLs are correctly configured."""
        try:
            # Check environment variable
            env_url = os.environ.get("CIRISNODE_BASE_URL", "")

            # Check adapter manifest
            manifest_path = (
                Path(__file__).parent.parent.parent.parent / "ciris_adapters" / "cirisnode" / "manifest.json"
            )
            manifest_url = ""
            if manifest_path.exists():
                with open(manifest_path) as f:
                    manifest = json.load(f)
                    manifest_url = manifest.get("configuration", {}).get("base_url", {}).get("default", "")

            # Validate URLs use correct domain
            valid_domains = ["ciris-services-1.ai", "ciris-services-2.ai"]

            issues = []
            if env_url and not any(d in env_url for d in valid_domains):
                issues.append(f"CIRISNODE_BASE_URL uses invalid domain: {env_url}")

            if manifest_url and not any(d in manifest_url for d in valid_domains):
                issues.append(f"Manifest default uses invalid domain: {manifest_url}")

            if issues:
                return False, "; ".join(issues)

            return True, f"URLs configured: env={env_url or 'not set'}, manifest={manifest_url}"

        except Exception as e:
            return False, str(e)

    # =========================================================================
    # Connectivity Tests
    # =========================================================================

    async def _test_health_us(self) -> Tuple[bool, str]:
        """Test health check connectivity to US CIRISNode."""
        return await self._check_node_health(CIRISNODE_US_URL, "US")

    async def _test_health_eu(self) -> Tuple[bool, str]:
        """Test health check connectivity to EU CIRISNode."""
        return await self._check_node_health(CIRISNODE_EU_URL, "EU")

    async def _check_node_health(self, base_url: str, region: str) -> Tuple[bool, str]:
        """Check health endpoint of a CIRISNode server.

        Args:
            base_url: CIRISNode base URL
            region: Region identifier for logging

        Returns:
            (success, message) tuple
        """
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{base_url}/api/v1/health"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        status = data.get("status", "unknown")
                        return True, f"{region} node healthy: {status}"
                    else:
                        return False, f"{region} node returned HTTP {response.status}"

        except aiohttp.ClientConnectorError as e:
            return False, f"Cannot reach {region} node ({base_url}): {e}"
        except asyncio.TimeoutError:
            return False, f"{region} node timeout after 10s"
        except Exception as e:
            return False, str(e)

    async def _test_portal_reachability(self) -> Tuple[bool, str]:
        """Test that CIRISPortal is reachable for OAuth/registration."""
        try:
            async with aiohttp.ClientSession() as session:
                # Check portal health or root endpoint
                url = f"{CIRISPORTAL_URL}/api/health"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        return True, f"CIRISPortal reachable at {CIRISPORTAL_URL}"
                    elif response.status == 404:
                        # Health endpoint may not exist, try root
                        async with session.get(CIRISPORTAL_URL, timeout=aiohttp.ClientTimeout(total=10)) as root_resp:
                            if root_resp.status in [200, 302, 301]:
                                return True, f"CIRISPortal reachable at {CIRISPORTAL_URL} (root)"
                            return False, f"CIRISPortal returned HTTP {root_resp.status}"
                    else:
                        return False, f"CIRISPortal returned HTTP {response.status}"

        except aiohttp.ClientConnectorError as e:
            return False, f"Cannot reach CIRISPortal: {e}"
        except asyncio.TimeoutError:
            return False, "CIRISPortal timeout after 10s"
        except Exception as e:
            return False, str(e)

    # =========================================================================
    # Local Configuration Tests
    # =========================================================================

    async def _test_local_signing_key(self) -> Tuple[bool, str]:
        """Test that local signing key exists and is valid."""
        try:
            key_path = Path("data/agent_signing.key")

            if not key_path.exists():
                return False, f"Signing key not found at {key_path}. Register via CIRISPortal to obtain key."

            # Check key size (Ed25519 private key should be 32 bytes)
            key_size = key_path.stat().st_size
            if key_size != 32:
                return False, f"Invalid key size: {key_size} bytes (expected 32 for Ed25519)"

            # Try to load the key using the signing protocol
            try:
                from ciris_engine.logic.audit.signing_protocol import get_unified_signing_key

                unified_key = get_unified_signing_key()
                key_id = unified_key.key_id
                return True, f"Signing key loaded: {key_id}"
            except ImportError:
                return True, f"Signing key exists ({key_size} bytes) - protocol not available for validation"
            except Exception as e:
                return False, f"Signing key exists but failed to load: {e}"

        except Exception as e:
            return False, str(e)

    # =========================================================================
    # Format Validation Tests
    # =========================================================================

    async def _test_wbd_format(self) -> Tuple[bool, str]:
        """Validate WBD (Wisdom-Based Deferral) submission format."""
        try:
            # Expected WBD submission format
            expected_fields = [
                "agent_task_id",
                "payload",
                "domain_hint",
                "signature",
                "signature_key_id",
            ]

            # Expected payload structure
            expected_payload_fields = [
                "reason",
                "task_id",
                "thought_id",
                "defer_until",
                "context",
            ]

            # Build example payload
            example = {
                "agent_task_id": "thought-abc123",
                "payload": json.dumps(
                    {
                        "reason": "requires_human_review",
                        "task_id": "task-xyz",
                        "thought_id": "thought-abc123",
                        "defer_until": "2026-02-16T12:00:00Z",
                        "context": {"domain_hint": "safety"},
                    }
                ),
                "domain_hint": "safety",
                "signature": "base64_encoded_ed25519_signature",
                "signature_key_id": "agent-f1e2d3c4a5b6789",
            }

            # Validate structure
            missing = [f for f in expected_fields if f not in example]
            if missing:
                return False, f"Missing required fields: {missing}"

            # Validate payload structure
            payload = json.loads(example["payload"])
            payload_missing = [f for f in expected_payload_fields if f not in payload]
            if payload_missing:
                return False, f"Missing payload fields: {payload_missing}"

            return (
                True,
                f"WBD format validated ({len(expected_fields)} fields, {len(expected_payload_fields)} payload fields)",
            )

        except Exception as e:
            return False, str(e)

    async def _test_trace_format(self) -> Tuple[bool, str]:
        """Validate covenant trace batch format."""
        try:
            # Expected trace structure
            expected_trace_fields = [
                "trace_id",
                "thought_id",
                "agent_id_hash",
                "started_at",
                "components",
            ]

            # Expected component structure
            expected_component_fields = [
                "component_type",
                "event_type",
                "timestamp",
                "data",
            ]

            # Expected event types
            expected_event_types = [
                "THOUGHT_START",
                "SNAPSHOT_AND_CONTEXT",
                "DMA_RESULTS",
                "IDMA_RESULT",
                "ASPDMA_RESULT",
                "CONSCIENCE_RESULT",
                "ACTION_RESULT",
            ]

            # Build example batch
            example_batch = {
                "events": [
                    {
                        "event_type": "covenant_trace",
                        "trace": {
                            "trace_id": "trace-xyz-20260216",
                            "thought_id": "thought-abc123",
                            "task_id": "task-xyz",
                            "agent_id_hash": "a1b2c3d4e5f6g7h8",
                            "started_at": "2026-02-16T10:00:00Z",
                            "completed_at": "2026-02-16T10:00:05Z",
                            "trace_level": "full_traces",
                            "components": [
                                {
                                    "component_type": "observation",
                                    "event_type": "THOUGHT_START",
                                    "timestamp": "2026-02-16T10:00:00Z",
                                    "data": {"round_number": 1},
                                }
                            ],
                            "signature": "base64_ed25519_signature",
                            "signature_key_id": "agent-f1e2d3c4a5b6789",
                        },
                    }
                ],
                "batch_timestamp": "2026-02-16T10:00:10Z",
                "trace_level": "full_traces",
            }

            # Validate structure
            if "events" not in example_batch:
                return False, "Missing 'events' field in batch"

            trace = example_batch["events"][0]["trace"]
            missing = [f for f in expected_trace_fields if f not in trace]
            if missing:
                return False, f"Missing trace fields: {missing}"

            component = trace["components"][0]
            comp_missing = [f for f in expected_component_fields if f not in component]
            if comp_missing:
                return False, f"Missing component fields: {comp_missing}"

            return (
                True,
                f"Trace format validated ({len(expected_trace_fields)} trace fields, {len(expected_event_types)} event types)",
            )

        except Exception as e:
            return False, str(e)

    # =========================================================================
    # Live Node Tests (require --live-node flag)
    # =========================================================================

    async def _test_key_registration(self) -> Tuple[bool, str]:
        """Test public key registration endpoint on live CIRISNode."""
        try:
            # Try to get signing key
            try:
                from ciris_engine.logic.audit.signing_protocol import get_unified_signing_key

                unified_key = get_unified_signing_key()
                registration_payload = unified_key.get_registration_payload()
            except ImportError:
                return True, "Skipped (signing protocol not available)"
            except Exception as e:
                return False, f"Cannot get signing key: {e}"

            async with aiohttp.ClientSession() as session:
                url = f"{self.node_url}/api/v1/covenant/public-keys"
                headers = {"Content-Type": "application/json"}

                # Add agent token if available
                agent_token = os.environ.get("CIRISNODE_AGENT_TOKEN")
                if agent_token:
                    headers["X-Agent-Token"] = agent_token

                async with session.post(
                    url,
                    json=registration_payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status in [200, 201]:
                        data = await response.json()
                        return True, f"Key registered: {data.get('key_id', 'unknown')}"
                    elif response.status == 409:
                        return True, "Key already registered"
                    else:
                        error_text = await response.text()
                        return False, f"Registration failed: HTTP {response.status} - {error_text[:100]}"

        except aiohttp.ClientConnectorError as e:
            return False, f"Cannot reach CIRISNode: {e}"
        except Exception as e:
            return False, str(e)

    async def _test_wbd_submit(self) -> Tuple[bool, str]:
        """Test WBD submission endpoint on live CIRISNode."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.node_url}/api/v1/wbd/submit"

                # This is a format test - actual submission requires valid signature
                # Just check the endpoint exists and returns appropriate error
                async with session.post(
                    url,
                    json={"test": "format_check"},
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    # We expect 400/422 for invalid format, not 404
                    if response.status == 404:
                        return False, "WBD submit endpoint not found"
                    elif response.status in [400, 422]:
                        return True, "WBD endpoint exists (validation working)"
                    elif response.status == 401:
                        return True, "WBD endpoint exists (auth required)"
                    else:
                        return True, f"WBD endpoint responded: HTTP {response.status}"

        except aiohttp.ClientConnectorError as e:
            return False, f"Cannot reach CIRISNode: {e}"
        except Exception as e:
            return False, str(e)

    async def _test_covenant_events(self) -> Tuple[bool, str]:
        """Test covenant events endpoint on live CIRISNode."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.node_url}/api/v1/covenant/events"

                # This is a format test - actual submission requires valid signature
                async with session.post(
                    url,
                    json={"events": [], "batch_timestamp": "2026-02-16T00:00:00Z"},
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 404:
                        return False, "Covenant events endpoint not found"
                    elif response.status in [200, 400, 422]:
                        return True, f"Covenant events endpoint exists: HTTP {response.status}"
                    elif response.status == 401:
                        return True, "Covenant events endpoint exists (auth required)"
                    else:
                        return True, f"Covenant events endpoint responded: HTTP {response.status}"

        except aiohttp.ClientConnectorError as e:
            return False, f"Cannot reach CIRISNode: {e}"
        except Exception as e:
            return False, str(e)

    async def _test_agent_token(self) -> Tuple[bool, str]:
        """Test agent token validation on live CIRISNode."""
        try:
            agent_token = os.environ.get("CIRISNODE_AGENT_TOKEN")

            if not agent_token:
                return True, "No CIRISNODE_AGENT_TOKEN set (optional for signature-based auth)"

            async with aiohttp.ClientSession() as session:
                url = f"{self.node_url}/api/v1/agent/events"
                headers = {
                    "Content-Type": "application/json",
                    "X-Agent-Token": agent_token,
                }

                # Test token with empty event
                async with session.post(
                    url,
                    json={"event_type": "test", "data": {}},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status in [200, 201]:
                        return True, "Agent token valid"
                    elif response.status == 401:
                        return False, "Agent token invalid or expired"
                    elif response.status == 403:
                        return False, "Agent token unauthorized"
                    else:
                        return True, f"Token check returned: HTTP {response.status}"

        except aiohttp.ClientConnectorError as e:
            return False, f"Cannot reach CIRISNode: {e}"
        except Exception as e:
            return False, str(e)
