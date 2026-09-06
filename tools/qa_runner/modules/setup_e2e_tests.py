"""
End-to-End Setup Wizard Test Module.

Tests the complete first-run setup wizard flow, simulating the user journey
from welcome screen through LLM configuration, optional features, account
creation, and login verification.

Based on KMP SetupViewModel patterns - supports both BYOK and future Node flows.
"""

import asyncio
import logging
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ..config import QAConfig, QAModule, QATestCase
from tools.qa_runner.announce_bundle import DEFAULT_NODE_URL, check_announce_bundle

logger = logging.getLogger(__name__)

# ============================================================================
# Test Configuration
# ============================================================================

# API key files (same as setup_tests.py)
_KEY_FILES: Dict[str, str] = {
    "anthropic": os.path.expanduser("~/.anthropic_key"),
    "google": os.path.expanduser("~/.google_key"),
    "groq": os.path.expanduser("~/.groq_key"),
    "openrouter": os.path.expanduser("~/.openrouter_key"),
    "together": os.path.expanduser("~/.together_key"),
    "openai": os.path.expanduser("~/.openai_key"),
}


def _load_api_key(provider: str) -> Optional[str]:
    """Load API key from key file."""
    key_file = _KEY_FILES.get(provider)
    if not key_file or not Path(key_file).exists():
        return None
    try:
        return Path(key_file).read_text().strip()
    except Exception:
        return None


@dataclass
class SetupE2EResult:
    """Result of an E2E setup test."""

    step: str
    passed: bool
    duration_ms: float
    message: str = ""
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SetupE2EReport:
    """Complete E2E test report."""

    total_steps: int = 0
    passed_steps: int = 0
    failed_steps: int = 0
    total_duration_ms: float = 0.0
    results: List[SetupE2EResult] = field(default_factory=list)
    setup_completed: bool = False
    login_verified: bool = False
    #: CIRISAgent#1144 Lesson 1 -- the announce bundle as the node reported it
    #: (None when the server predates the report or the node was unreachable).
    federation_key_id: Optional[str] = None
    node_claimed: bool = False
    announce_bundle: Optional[Dict[str, Any]] = None
    federation_discoverable: Optional[bool] = None

    @property
    def success(self) -> bool:
        return self.failed_steps == 0 and self.setup_completed and self.login_verified


# ============================================================================
# E2E Test Module
# ============================================================================


class SetupE2ETestModule:
    """End-to-end tests for the complete setup wizard flow.

    Tests the full journey:
    1. Check setup status (first-run detection)
    2. Load providers and templates
    3. Validate LLM configuration
    4. Load available models (live API)
    5. Complete setup with all fields
    6. Verify login with created user
    7. Verify system is operational
    """

    def __init__(self, config: QAConfig):
        self.config = config
        self.base_url = config.base_url
        self.client: Optional[httpx.AsyncClient] = None
        self.report = SetupE2EReport()

        # E2E test configuration
        self.test_username = f"e2e_user_{int(time.time())}"
        self.test_password = "E2E_Test_Password_12345!"
        self.admin_password = "E2E_Admin_Password_67890!"

        # LLM configuration - prefer live provider if available
        self.llm_provider = "openrouter"  # The QA default (CLAUDE.md model matrix)
        self.llm_api_key: Optional[str] = None
        self.llm_model = "qwen/qwen3.6-35b-a3b"
        self.llm_base_url: Optional[str] = None

        # Try to load a real API key
        self._load_llm_config()

    def _load_llm_config(self) -> None:
        """Load LLM configuration from available API keys."""
        # Priority order follows the CLAUDE.md model matrix: OpenRouter/Qwen default; Groq (Scout) and Together supported
        provider_priority = ["openrouter", "groq", "anthropic", "openai", "together", "google"]

        for provider in provider_priority:
            api_key = _load_api_key(provider)
            if api_key:
                self.llm_provider = provider
                self.llm_api_key = api_key

                # Set default models per provider
                if provider == "groq":
                    self.llm_model = "meta-llama/llama-4-scout-17b-16e-instruct"
                elif provider == "openrouter":
                    self.llm_model = "qwen/qwen3.6-35b-a3b"
                elif provider == "anthropic":
                    self.llm_model = "claude-haiku-4-5-20251001"
                elif provider == "openai":
                    self.llm_model = "gpt-4o-mini"
                elif provider == "together":
                    self.llm_model = "google/gemma-4-31B-it"
                elif provider == "google":
                    self.llm_model = "gemini-2.0-flash-exp"

                logger.info(f"[E2E] Using {provider} with model {self.llm_model}")
                return

        # Fallback to mock/invalid key for testing error paths
        logger.warning("[E2E] No valid API key found, using mock configuration")
        self.llm_api_key = "sk-mock-e2e-test-key"

    async def _record_step(
        self,
        step: str,
        passed: bool,
        duration_ms: float,
        message: str = "",
        error: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a test step result."""
        result = SetupE2EResult(
            step=step,
            passed=passed,
            duration_ms=duration_ms,
            message=message,
            error=error,
            details=details or {},
        )
        self.report.results.append(result)
        self.report.total_steps += 1
        if passed:
            self.report.passed_steps += 1
        else:
            self.report.failed_steps += 1
        self.report.total_duration_ms += duration_ms

        # Log result
        status = "PASS" if passed else "FAIL"
        logger.info(f"[E2E] [{status}] {step}: {message}")
        if error:
            logger.error(f"[E2E] Error: {error}")

    async def run_e2e_flow(self) -> SetupE2EReport:
        """Run the complete E2E setup wizard flow."""
        logger.info("=" * 60)
        logger.info("[E2E] Starting End-to-End Setup Wizard Test")
        logger.info("=" * 60)

        async with httpx.AsyncClient(timeout=30.0) as client:
            self.client = client

            # Step 1: Check setup status
            await self._test_setup_status()

            # Step 2: Load providers
            await self._test_load_providers()

            # Step 3: Load templates
            await self._test_load_templates()

            # Step 4: Load adapters
            await self._test_load_adapters()

            # Step 5: Validate LLM (if we have a real key)
            if self.llm_api_key and not self.llm_api_key.startswith("sk-mock"):
                await self._test_validate_llm()

                # Step 6: Load models (live API)
                await self._test_load_models()

            # Step 6b/6c: the wizard's order -- mint the owner's federation ID and
            # self-claim the node with its one-time PIN BEFORE completing setup.
            # Both are open during first-run (no ROOT yet, loopback-only) and
            # owner-gated after; the PIN is minted only while the node is unowned
            # (CIRISAgent#1144 Lesson 1: an unclaimed node cannot announce).
            await self._test_mint_federation_id()
            await self._test_claim_ownership()

            # Step 7: Complete setup
            await self._test_complete_setup()

            # Step 8: Verify login
            await self._test_verify_login()

            # Step 8b: the announce bundle -- is the node discoverable on the
            # federation? (#1144 Lesson 1: an un-announced node is P2P-only)
            await self._test_announce_bundle()

            # Step 9: Verify system operational
            await self._test_system_operational()

        logger.info("=" * 60)
        logger.info(f"[E2E] Test Complete: {self.report.passed_steps}/{self.report.total_steps} steps passed")
        logger.info(f"[E2E] Setup Completed: {self.report.setup_completed}")
        logger.info(f"[E2E] Login Verified: {self.report.login_verified}")
        logger.info("=" * 60)

        return self.report

    async def _test_setup_status(self) -> None:
        """Test: Check setup status endpoint."""
        start = time.perf_counter()
        step = "check_setup_status"

        try:
            response = await self.client.get(f"{self.base_url}/v1/setup/status")
            duration_ms = (time.perf_counter() - start) * 1000

            if response.status_code != 200:
                await self._record_step(
                    step, False, duration_ms, f"Status code: {response.status_code}", error=response.text
                )
                return

            data = response.json()
            is_first_run = data.get("data", {}).get("is_first_run", data.get("is_first_run"))
            setup_required = data.get("data", {}).get("setup_required", data.get("setup_required"))

            await self._record_step(
                step,
                True,
                duration_ms,
                f"First run: {is_first_run}, Setup required: {setup_required}",
                details={"is_first_run": is_first_run, "setup_required": setup_required},
            )

        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            await self._record_step(step, False, duration_ms, "Exception occurred", error=str(e))

    async def _test_load_providers(self) -> None:
        """Test: Load LLM providers."""
        start = time.perf_counter()
        step = "load_providers"

        try:
            response = await self.client.get(f"{self.base_url}/v1/setup/providers")
            duration_ms = (time.perf_counter() - start) * 1000

            if response.status_code != 200:
                await self._record_step(
                    step, False, duration_ms, f"Status code: {response.status_code}", error=response.text
                )
                return

            data = response.json()
            providers = data.get("data", data) if isinstance(data.get("data"), list) else data
            if isinstance(providers, dict):
                providers = providers.get("providers", [])

            provider_ids = [p.get("id") for p in providers] if isinstance(providers, list) else []

            # Verify expected providers
            expected = ["openai", "anthropic", "groq", "local"]
            missing = [p for p in expected if p not in provider_ids]

            if missing:
                await self._record_step(
                    step,
                    False,
                    duration_ms,
                    f"Missing providers: {missing}",
                    details={"found": provider_ids, "missing": missing},
                )
            else:
                await self._record_step(
                    step,
                    True,
                    duration_ms,
                    f"Loaded {len(provider_ids)} providers",
                    details={"providers": provider_ids},
                )

        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            await self._record_step(step, False, duration_ms, "Exception occurred", error=str(e))

    async def _test_load_templates(self) -> None:
        """Test: Load agent templates."""
        start = time.perf_counter()
        step = "load_templates"

        try:
            response = await self.client.get(f"{self.base_url}/v1/setup/templates")
            duration_ms = (time.perf_counter() - start) * 1000

            if response.status_code != 200:
                await self._record_step(
                    step, False, duration_ms, f"Status code: {response.status_code}", error=response.text
                )
                return

            data = response.json()
            templates = data.get("data", data) if isinstance(data.get("data"), list) else data
            if isinstance(templates, dict):
                templates = templates.get("templates", [])

            template_ids = [t.get("id") for t in templates] if isinstance(templates, list) else []

            # Verify default template exists
            if "default" not in template_ids:
                await self._record_step(
                    step,
                    False,
                    duration_ms,
                    "Default template not found",
                    details={"found": template_ids},
                )
            else:
                await self._record_step(
                    step,
                    True,
                    duration_ms,
                    f"Loaded {len(template_ids)} templates",
                    details={"templates": template_ids},
                )

        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            await self._record_step(step, False, duration_ms, "Exception occurred", error=str(e))

    async def _test_load_adapters(self) -> None:
        """Test: Load available adapters."""
        start = time.perf_counter()
        step = "load_adapters"

        try:
            response = await self.client.get(f"{self.base_url}/v1/setup/adapters")
            duration_ms = (time.perf_counter() - start) * 1000

            if response.status_code != 200:
                await self._record_step(
                    step, False, duration_ms, f"Status code: {response.status_code}", error=response.text
                )
                return

            data = response.json()
            adapters = data.get("data", data) if isinstance(data.get("data"), list) else data
            if isinstance(adapters, dict):
                adapters = adapters.get("adapters", [])

            adapter_ids = [a.get("id") for a in adapters] if isinstance(adapters, list) else []

            # Verify API adapter exists (required)
            if "api" not in adapter_ids:
                await self._record_step(
                    step,
                    False,
                    duration_ms,
                    "API adapter not found",
                    details={"found": adapter_ids},
                )
            else:
                await self._record_step(
                    step, True, duration_ms, f"Loaded {len(adapter_ids)} adapters", details={"adapters": adapter_ids}
                )

        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            await self._record_step(step, False, duration_ms, "Exception occurred", error=str(e))

    async def _test_validate_llm(self) -> None:
        """Test: Validate LLM configuration."""
        start = time.perf_counter()
        step = "validate_llm"

        try:
            payload = {
                "provider": self.llm_provider,
                "api_key": self.llm_api_key,
                "base_url": self.llm_base_url,
                "model": self.llm_model,
            }

            response = await self.client.post(f"{self.base_url}/v1/setup/validate-llm", json=payload)
            duration_ms = (time.perf_counter() - start) * 1000

            if response.status_code != 200:
                await self._record_step(
                    step, False, duration_ms, f"Status code: {response.status_code}", error=response.text
                )
                return

            data = response.json()
            result = data.get("data", data)
            valid = result.get("valid", False)
            message = result.get("message", "")

            if valid:
                await self._record_step(
                    step,
                    True,
                    duration_ms,
                    f"LLM validated: {message}",
                    details={"provider": self.llm_provider, "model": self.llm_model},
                )
            else:
                error = result.get("error", "Validation failed")
                await self._record_step(
                    step,
                    False,
                    duration_ms,
                    f"LLM validation failed: {message}",
                    error=error,
                    details={"provider": self.llm_provider, "model": self.llm_model},
                )

        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            await self._record_step(step, False, duration_ms, "Exception occurred", error=str(e))

    async def _test_load_models(self) -> None:
        """Test: Load available models from provider API."""
        start = time.perf_counter()
        step = "load_models"

        try:
            payload = {
                "provider": self.llm_provider,
                "api_key": self.llm_api_key,
                "base_url": self.llm_base_url,
            }

            response = await self.client.post(f"{self.base_url}/v1/setup/list-models", json=payload, timeout=15.0)
            duration_ms = (time.perf_counter() - start) * 1000

            if response.status_code != 200:
                await self._record_step(
                    step, False, duration_ms, f"Status code: {response.status_code}", error=response.text
                )
                return

            data = response.json()
            result = data.get("data", data)
            models = result.get("models", [])
            source = result.get("source", "unknown")
            error = result.get("error")

            if source == "live" and models:
                # Update model selection if we got recommended
                recommended = next((m for m in models if m.get("ciris_recommended")), None)
                if recommended:
                    self.llm_model = recommended.get("id", self.llm_model)

                await self._record_step(
                    step,
                    True,
                    duration_ms,
                    f"Loaded {len(models)} models from {source}",
                    details={"model_count": len(models), "source": source, "selected": self.llm_model},
                )
            elif models:
                await self._record_step(
                    step,
                    True,
                    duration_ms,
                    f"Loaded {len(models)} models (static fallback)",
                    details={"model_count": len(models), "source": source, "error": error},
                )
            else:
                await self._record_step(
                    step,
                    False,
                    duration_ms,
                    "No models returned",
                    error=error,
                    details={"source": source},
                )

        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            await self._record_step(step, False, duration_ms, "Exception occurred", error=str(e))

    async def _test_complete_setup(self) -> None:
        """Test: Complete setup with full configuration."""
        start = time.perf_counter()
        step = "complete_setup"

        try:
            # Build complete setup request
            payload = {
                "llm_provider": self.llm_provider,
                "llm_api_key": self.llm_api_key,
                "llm_base_url": self.llm_base_url,
                "llm_model": self.llm_model,
                "template_id": "default",
                "enabled_adapters": ["api"],
                "adapter_config": {},
                "admin_username": self.test_username,
                "admin_password": self.test_password,
                "system_admin_password": self.admin_password,
                "agent_port": self.config.api_port,
            }

            response = await self.client.post(f"{self.base_url}/v1/setup/complete", json=payload, timeout=30.0)
            duration_ms = (time.perf_counter() - start) * 1000

            if response.status_code != 200:
                await self._record_step(
                    step, False, duration_ms, f"Status code: {response.status_code}", error=response.text
                )
                return

            data = response.json()
            message = data.get("message", data.get("data", {}).get("message", "Setup completed"))

            self.report.setup_completed = True
            await self._record_step(
                step,
                True,
                duration_ms,
                f"Setup completed: {message}",
                details={
                    "username": self.test_username,
                    "provider": self.llm_provider,
                    "model": self.llm_model,
                },
            )

        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            await self._record_step(step, False, duration_ms, "Exception occurred", error=str(e))

    async def _test_verify_login(self) -> None:
        """Test: Verify login with created user."""
        start = time.perf_counter()
        step = "verify_login"

        if not self.report.setup_completed:
            await self._record_step(step, False, 0, "Skipped - setup not completed")
            return

        try:
            payload = {"username": self.test_username, "password": self.test_password}

            response = await self.client.post(f"{self.base_url}/v1/auth/login", json=payload)
            duration_ms = (time.perf_counter() - start) * 1000

            if response.status_code != 200:
                await self._record_step(
                    step, False, duration_ms, f"Status code: {response.status_code}", error=response.text
                )
                return

            data = response.json()
            token = data.get("access_token", data.get("data", {}).get("access_token"))

            if token:
                self.report.login_verified = True
                # Store token for subsequent requests
                self.client.headers["Authorization"] = f"Bearer {token}"
                await self._record_step(
                    step,
                    True,
                    duration_ms,
                    f"Login successful for user: {self.test_username}",
                    details={"token_length": len(token)},
                )
            else:
                await self._record_step(step, False, duration_ms, "No access token in response", error=str(data))

        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            await self._record_step(step, False, duration_ms, "Exception occurred", error=str(e))

    async def _test_mint_federation_id(self) -> None:
        """Test: mint the owner's federation ID, as the wizard's mint step does.

        Announcing is the OWNER stating their ownership at a federation-wide
        audience, which needs the owner's signing key on this node. The wizard
        mints it (`POST /v1/self/identity`: open during first-run, owner-gated
        once the node is owned, idempotent) before it claims and completes;
        without it the claim has no fed-ID to bind and every announce answers
        503. Sent through the brain (8080), which proxies it to the node -- the
        same path client >= 0.5.196 uses.
        """
        start = time.perf_counter()
        step = "mint_federation_id"

        try:
            response = await self.client.post(
                f"{self.base_url}/v1/self/identity", json={"label": self.test_username}, timeout=60.0
            )
            duration_ms = (time.perf_counter() - start) * 1000
            if response.status_code != 200:
                await self._record_step(
                    step, False, duration_ms, f"Status code: {response.status_code}", error=response.text[:300]
                )
                return
            data = response.json()
            key_id = str(data.get("key_id", ""))
            self.report.federation_key_id = key_id or None
            await self._record_step(
                step,
                bool(key_id),
                duration_ms,
                f"Federation ID minted: {key_id} ({data.get('hardware_type', '?')})" if key_id else "No key_id in mint response",
                details={"key_id": key_id, "hardware_type": data.get("hardware_type"), "fedcode_prefix": str(data.get("fedcode", ""))[:24]},
            )
        except Exception as e:  # noqa: BLE001
            duration_ms = (time.perf_counter() - start) * 1000
            await self._record_step(step, False, duration_ms, "Exception occurred", error=str(e))

    async def _test_claim_ownership(self) -> None:
        """Test: self-claim the local node with its one-time PIN, as the wizard does.

        The node mints a claim PIN at boot while it is UNOWNED and writes it to
        `<node home>/claim_pin` (the node's home is the backend's CIRIS_HOME).
        The wizard reads that file and posts `POST /v1/setup/claim-remote`
        with the node's own NodeCode; that writes the owner->node binding the
        announce later widens. Without it the node completes setup UNCLAIMED
        and answers 409 to every announce (CIRISAgent#1144 Lesson 1).
        """
        start = time.perf_counter()
        step = "claim_ownership"
        node_url = os.environ.get("CIRIS_NODE_URL") or DEFAULT_NODE_URL

        # The PIN: the node's home is the backend's CIRIS_HOME; a run that does
        # not export it puts the backend's home in the repo checkout (server.py).
        homes = [os.environ.get("CIRIS_HOME"), str(Path(__file__).resolve().parents[3]), os.path.expanduser("~/ciris")]
        pin_paths = [Path(h) / "claim_pin" for h in homes if h]
        pin: Optional[str] = None
        pin_file: Optional[Path] = None
        for candidate in pin_paths:
            try:
                raw = candidate.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if raw.startswith("{"):
                try:
                    obj = json.loads(raw)
                    raw = str(obj.get("pin") or obj.get("claim_pin") or "")
                except ValueError:
                    raw = ""
            if raw:
                pin, pin_file = raw, candidate
                break
        if pin is None:
            duration_ms = (time.perf_counter() - start) * 1000
            await self._record_step(
                step,
                False,
                duration_ms,
                "No claim PIN readable -- the node minted none (already ROOT-owned: setup ran against a "
                "database that already has an owner) or wrote it to a home this runner is not looking at",
                error=f"looked in: {', '.join(str(p) for p in pin_paths)}",
            )
            return

        try:
            # The node's own NodeCode (served on the federation surface, proxied by the brain).
            r = await self.client.get(f"{self.base_url}/v1/federation/node-code", timeout=30.0)
            if r.status_code != 200:
                r = await self.client.get(f"{node_url}/v1/federation/node-code", timeout=30.0)
            r.raise_for_status()
            body = r.json()
            payload = body.get("data", body) if isinstance(body, dict) else {}
            node_code = str(payload.get("node_code") or payload.get("code") or "")
            if not node_code:
                raise RuntimeError(f"no node_code in {str(body)[:200]}")

            claim = {
                "node_code": node_code,
                "claim_pin": pin,
                "cohort_scope": "self",
                # A self-claim's NodeCode may carry no transport hint; the target IS this node.
                "target_url": node_url,
                "owner_username": self.test_username,
                "owner_password": self.test_password,
            }
            # claim-remote is a NODE route; the brain's own /v1/setup router shadows
            # the prefix, so it is posted to the node directly.
            response = await self.client.post(f"{node_url}/v1/setup/claim-remote", json=claim, timeout=120.0)
            duration_ms = (time.perf_counter() - start) * 1000
            if response.status_code != 200:
                await self._record_step(
                    step, False, duration_ms, f"Status code: {response.status_code}", error=response.text[:400]
                )
                return
            data = response.json()
            self.report.node_claimed = True
            await self._record_step(
                step,
                True,
                duration_ms,
                f"Node self-claimed (PIN from {pin_file}): owner={data.get('owner') or data.get('responsible_user_key_id')}",
                details={"pin_file": str(pin_file), "node_code_prefix": node_code[:24], "response_keys": sorted(data.keys()) if isinstance(data, dict) else []},
            )
        except Exception as e:  # noqa: BLE001
            duration_ms = (time.perf_counter() - start) * 1000
            await self._record_step(step, False, duration_ms, "Exception occurred", error=str(e))

    async def _test_announce_bundle(self) -> None:
        """Test: the node's announce bundle is complete and federation-visible.

        Setup-complete binds owner->node at `cohort_scope: self`; until the
        owner announces, no peer can place this node in ANY community audience
        (CIRISAgent#1144 Lesson 1). The announce is idempotent and, from
        ciris-server 0.5.197, returns the bundle it walked. Asserted here with
        the session verify_login obtained: `federation_discoverable` and
        `bundle_expected == 5` (owner key, node key, owner->node binding,
        owner->agent binding, agent key).
        """
        start = time.perf_counter()
        step = "announce_bundle"

        if not self.report.login_verified:
            await self._record_step(step, False, 0, "Skipped - login not verified (no owner session to announce with)")
            return

        node_url = os.environ.get("CIRIS_NODE_URL") or DEFAULT_NODE_URL
        try:
            check = await check_announce_bundle(self.client, node_url, dict(self.client.headers))
        except Exception as e:  # noqa: BLE001
            duration_ms = (time.perf_counter() - start) * 1000
            await self._record_step(step, False, duration_ms, "Exception occurred", error=str(e))
            return
        duration_ms = (time.perf_counter() - start) * 1000

        self.report.announce_bundle = check.details()
        self.report.federation_discoverable = check.discoverable
        for line in check.render().splitlines():
            logger.info(f"[E2E] {line}")

        if check.asserted:
            await self._record_step(step, check.passed, duration_ms, check.message, details=check.details())
        elif check.status == "not_reported":
            # The announce itself succeeded; only the report is missing. Not a
            # failure of THIS node -- a floor the pin has not reached yet.
            await self._record_step(step, True, duration_ms, check.message, details=check.details())
        else:
            # unreachable / unauthorized / error: the bundle could NOT be asserted.
            # Say so in the runner's words rather than passing a check that did
            # not run (the gate lesson: a skipped assertion is not a green one).
            await self._record_step(step, False, duration_ms, check.message, error=check.status, details=check.details())

    async def _test_system_operational(self) -> None:
        """Test: Verify system is operational after setup."""
        start = time.perf_counter()
        step = "verify_system"

        if not self.report.login_verified:
            await self._record_step(step, False, 0, "Skipped - login not verified")
            return

        try:
            # Right after setup-complete the processor is still starting and health
            # says `critical` for a few seconds; wait it out (bounded) before judging.
            response = await self.client.get(f"{self.base_url}/v1/system/health", timeout=10.0)
            for _attempt in range(20):
                if response.status_code == 200:
                    _p = response.json().get("data", response.json())
                    if _p.get("status") not in ("critical", "initializing", "starting"):
                        break
                await asyncio.sleep(3)
                response = await self.client.get(f"{self.base_url}/v1/system/health", timeout=10.0)
            duration_ms = (time.perf_counter() - start) * 1000

            if response.status_code != 200:
                await self._record_step(
                    step, False, duration_ms, f"Status code: {response.status_code}", error=response.text
                )
                return

            data = response.json()
            payload = data.get("data", data)
            # /v1/system/health says `status: "healthy"` and lists per-service
            # {available, healthy} counts; it has never carried a `healthy` bool,
            # so reading one reported "not healthy" on a healthy system.
            healthy = payload.get("status") == "healthy" or bool(payload.get("healthy", False))
            per_service = payload.get("services", {}) or {}
            services = payload.get("services_online") or sum(
                int(v.get("healthy", 0)) for v in per_service.values() if isinstance(v, dict)
            )
            unhealthy = [k for k, v in per_service.items() if isinstance(v, dict) and v.get("healthy", 0) < v.get("available", 0)]

            if healthy:
                await self._record_step(
                    step,
                    True,
                    duration_ms,
                    f"System healthy with {services} services online",
                    details={"healthy": healthy, "services_online": services},
                )
            else:
                await self._record_step(
                    step,
                    False,
                    duration_ms,
                    f"System not healthy: status={payload.get('status')!r}"
                    + (f", degraded: {', '.join(unhealthy)}" if unhealthy else ""),
                    details={"healthy": healthy, "status": payload.get("status"), "services": services, "degraded": unhealthy},
                )

        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            await self._record_step(step, False, duration_ms, "Exception occurred", error=str(e))

    @staticmethod
    def get_all_tests() -> List[QATestCase]:
        """Get E2E test cases for QA runner integration.

        Note: The actual E2E flow is run via run_e2e_flow().
        These test cases are for compatibility with the standard runner.
        """
        return [
            QATestCase(
                name="E2E Setup Wizard Flow",
                module=QAModule.SETUP_E2E,
                endpoint="/v1/setup/status",
                method="GET",
                expected_status=200,
                requires_auth=False,
                description="End-to-end setup wizard flow test (status check entry point)",
            ),
        ]


# ============================================================================
# Standalone execution support
# ============================================================================


async def run_standalone(base_url: str = "http://localhost:8080") -> SetupE2EReport:
    """Run E2E tests standalone (for debugging)."""
    config = QAConfig(base_url=base_url, api_port=8080)
    module = SetupE2ETestModule(config)
    return await module.run_e2e_flow()


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
    report = asyncio.run(run_standalone(url))

    print(f"\n{'=' * 60}")
    print(f"E2E Test Summary: {'PASS' if report.success else 'FAIL'}")
    print(f"Steps: {report.passed_steps}/{report.total_steps} passed")
    print(f"Duration: {report.total_duration_ms:.0f}ms")
    print(f"{'=' * 60}")

    sys.exit(0 if report.success else 1)
