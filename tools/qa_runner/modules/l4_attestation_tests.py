"""L4 attestation validation module — runtime contract for verify_tree() (Algorithm A).

Validates that the wheel-installed agent under test actually wires the
``ciris_verify.verify_tree()`` Algorithm-A path end-to-end:

- The CIRISVerify library loaded (the right version, libtss2 deps satisfied).
- ``run_attestation()`` produced a cached result (no pydantic validation
  failure between ``verify_tree()`` and ``AttestationResult``).
- The python integrity walk completed against the install tree, with a
  canonical ``sha256:<hex>`` total hash and a non-zero modules-checked count.
- ``python_failed_modules`` is shaped as ``Dict[str, str]`` (the bug class
  the cache-population fix in 7180902b6 closed — guards against List drift).
- ``max_level >= 3`` (binary self-check + DNS + HTTPS sources can all be
  verified at staged-QA time even when the build hasn't been registered yet
  — registry_match=True / max_level=4 require post-register validation,
  which lives in a separate post-deploy gate).

Why a dedicated module instead of folding into ``streaming``: streaming
verifies the reasoning pipeline; this verifies the attestation pipeline.
Different surfaces, different failure modes — keeping them separate makes
either-side regressions land in the right test name.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

import requests

from ..config import QAModule, QATestCase

logger = logging.getLogger(__name__)


# Canonical sha256 hash format used by both stage_runtime and verify_tree.
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

# Minimum level achievable at staged-QA time. The level depends on the
# *broader* attestation pipeline state (TPM, network, registry), not just
# Algorithm A wiring. GitHub-hosted runners have no TPM and partial network
# — they reach max_level=1 even when verify_tree itself is fully wired.
# Local TPM-emulated dev hosts often hit max_level=3 with ephemeral keys.
# We assert max_level >= 1 here (attestation pipeline didn't error out
# entirely); the deeper Algorithm A correctness checks below
# (`binary_ok`, `python_modules_checked`, `python_total_hash` format,
# `has_cached_result`) are what actually pin verify_tree wiring.
# After `ciris-build-sign register` runs in CI, post-deploy validation
# should expect MAX_LEVEL_REGISTERED below.
MIN_LEVEL_STAGED = 1
MAX_LEVEL_REGISTERED = 4


class L4AttestationModule:
    """Test module for L4 attestation runtime contract (Algorithm A)."""

    @staticmethod
    def get_l4_attestation_tests() -> List[QATestCase]:
        """HTTP + custom test cases for the verify_tree() runtime path."""
        return [
            QATestCase(
                module=QAModule.L4_ATTESTATION,
                name="verify-status reachable (full mode)",
                endpoint="/v1/setup/verify-status?mode=full",
                method="GET",
                requires_auth=True,
                expected_status=200,
                description="Triggers full attestation including verify_tree() walk.",
                timeout=120,
            ),
            QATestCase(
                module=QAModule.L4_ATTESTATION,
                name="attestation-status cache populated",
                endpoint="/v1/setup/attestation-status",
                method="GET",
                requires_auth=True,
                expected_status=200,
                description="Cache populated post-startup attestation (regression guard for the python_failed_modules dict-vs-list bug).",
                timeout=10,
            ),
            QATestCase(
                module=QAModule.L4_ATTESTATION,
                name="L4 attestation contract — Algorithm A end-to-end",
                endpoint="",
                method="CUSTOM",
                requires_auth=True,
                expected_status=200,
                custom_handler="verify_l4_attestation_contract",
                description="Asserts verify_tree() wired correctly: hash format, modules checked, failed_modules dict shape, level floor.",
                timeout=120,
            ),
        ]

    @staticmethod
    def verify_l4_attestation_contract(base_url: str, token: str) -> Dict[str, Any]:
        """Run structural assertions on the live attestation result.

        Calls /v1/setup/verify-status?mode=full, then /v1/setup/attestation-status,
        and validates each load-bearing field. Returns the qa_runner-standard
        result dict (success / message / details / errors).
        """
        errors: List[str] = []
        details: Dict[str, Any] = {}

        # 1) Full attestation — drives verify_tree() if Algorithm A is wired.
        try:
            r = requests.get(
                f"{base_url}/v1/setup/verify-status?mode=full",
                headers={"Authorization": f"Bearer {token}"},
                timeout=120,
            )
        except Exception as e:
            return {
                "success": False,
                "message": f"verify-status request failed: {e}",
                "errors": [str(e)],
                "details": {},
            }

        if r.status_code != 200:
            return {
                "success": False,
                "message": f"verify-status returned {r.status_code}: {r.text[:200]}",
                "errors": [f"http {r.status_code}"],
                "details": {"raw": r.text[:500]},
            }

        verify_data = r.json().get("data") or r.json()
        details["verify_status"] = {
            k: verify_data.get(k)
            for k in (
                "loaded",
                "version",
                "agent_version",
                "max_level",
                "attestation_mode",
                "binary_ok",
                "python_integrity_ok",
                "python_modules_checked",
                "python_modules_passed",
                "python_total_hash",
                "python_hash_valid",
                "registry_ok",
                "registry_key_status",
            )
        }

        # --- Mechanics assertions (independent of registry state) ---

        if not verify_data.get("loaded", False):
            errors.append("CIRISVerify library did not report `loaded=True`.")

        version = verify_data.get("version") or ""
        # Algorithm A floor was originally CIRISVerify v1.13.x (verify_tree()
        # runtime walker). v2.0 was the CanonicalBuild v2 wire bump on the
        # register side (CIRISVerify#8) — same verify_tree() contract on the
        # client. So the floor on the agent side is now 1.13.x OR any 2.x.
        if not (version.startswith("1.13.") or version.startswith("2.")):
            errors.append(
                f"Expected ciris-verify version >=1.13.x (Algorithm A floor); got '{version}'."
            )

        # The wheel-installed agent must have walked SOMETHING — even a stub
        # walk should produce > 100 modules across ciris_engine + ciris_adapters
        # + ciris_sdk. Zero means the include_roots / exempt_dirs got mismatched
        # against what the wheel actually shipped (a previous bug class).
        checked = verify_data.get("python_modules_checked") or 0
        if checked < 100:
            errors.append(
                f"python_modules_checked={checked} (<100). verify_tree() either didn't run or "
                f"walked an empty tree — check include_roots vs install layout."
            )

        total_hash = verify_data.get("python_total_hash") or ""
        if total_hash and not _HASH_RE.match(total_hash):
            errors.append(
                f"python_total_hash='{total_hash}' doesn't match canonical 'sha256:<64-hex>' format. "
                f"verify_tree may be running but mis-reporting."
            )
        elif not total_hash:
            errors.append(
                "python_total_hash is empty — verify_tree didn't populate the hash field."
            )

        # binary_ok = self-verification of libciris_verify_ffi.so. If this is
        # False, libtss2 deps probably didn't load (or the wheel's .so is wrong).
        if not verify_data.get("binary_ok", False):
            errors.append(
                "binary_ok=False: libciris_verify_ffi.so failed self-verification. "
                "Likely libtss2 system libs missing or wheel/.so mismatch."
            )

        # max_level floor. At staged-QA time the achievable level depends on
        # TPM/network/registry — not just our Algorithm A wiring — so this
        # is a coarse sanity check (>=1 means the attestation pipeline
        # completed without erroring). The structural Algorithm A checks
        # above catch verify_tree-wiring bugs precisely.
        max_level = verify_data.get("max_level", 0)
        if max_level < MIN_LEVEL_STAGED:
            errors.append(
                f"max_level={max_level} (<{MIN_LEVEL_STAGED}). The attestation pipeline returned 0, "
                f"meaning no checks passed at all — startup attestation likely errored out. "
                f"Check has_cached_result and the agent's incidents log."
            )

        # 2) Cache populated. Catches the python_failed_modules dict-vs-list
        # bug class — that bug made startup attestation throw inside pydantic
        # validation, which left the cache as None and broke every downstream
        # thought. The endpoint here is read-only (no fresh attestation), so
        # if has_cached_result=False the structural failure is on us.
        try:
            r2 = requests.get(
                f"{base_url}/v1/setup/attestation-status",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            cache_data = r2.json().get("data") or r2.json()
            details["cache_status"] = cache_data
            if not cache_data.get("has_cached_result", False):
                errors.append(
                    "attestation-status reports has_cached_result=False after a successful "
                    "verify-status?mode=full — the cache write path broke. This is the "
                    "python_failed_modules dict-vs-list regression class — see e8acb3e9a."
                )
            if cache_data.get("attestation_in_progress", False):
                # Soft warning, not an error — partial overlap is possible
                # if the QA fires fast.
                logger.info("attestation_in_progress=True at second check (transient)")
        except Exception as e:
            errors.append(f"attestation-status request failed: {e}")

        ok = len(errors) == 0
        if ok:
            return {
                "success": True,
                "message": (
                    f"✓ L4 contract: ciris-verify {version}, "
                    f"max_level={max_level}, "
                    f"python_modules_checked={checked}, "
                    f"total_hash={total_hash[:32] if total_hash else '?'}…"
                ),
                "details": details,
                "errors": [],
            }
        return {
            "success": False,
            "message": "❌ L4 attestation contract failed: " + "; ".join(errors),
            "errors": errors,
            "details": details,
        }

    @staticmethod
    def run_custom_test(test: QATestCase, config: Any, token: str) -> Dict[str, Any]:
        """Custom-handler dispatch. Mirrors the StreamingVerificationModule shape
        so runner.py can pick this up without special-casing in the dispatcher
        (matched by module rather than handler name)."""
        if test.custom_handler == "verify_l4_attestation_contract":
            return L4AttestationModule.verify_l4_attestation_contract(config.base_url, token)
        return {
            "success": False,
            "message": f"Unknown L4 custom_handler: {test.custom_handler}",
            "errors": [f"unknown handler: {test.custom_handler}"],
            "details": {},
        }
