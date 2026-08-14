"""Preflight validation of the LLM provider/key/model, before any device work.

WHY THIS EXISTS
---------------
The filmstrip configures the agent's LLM through the setup wizard UI, so a bad
key or a mistyped model does not surface until the CHAT step — after install,
wizard, federation-ID mint, and login have all run. At that point the failure
presents as "no SPEAK + NO trace seal; ship-unconfirmed", which reads like an
agent or trace-pipeline defect. Three separate filmstrip runs were burned that
way: one on a 401 (stale ``~/.groq_key``), two on a 402 (Together credit
exhausted). None of those are agent defects and none should cost a full run.

This module answers one question — *will the agent's very first LLM call
succeed?* — by making that call ourselves, against the same base URL the client
will resolve, before the device is touched.

DETERMINISM
-----------
``PROVIDER_BASE_URLS`` mirrors ``LLMSettingsViewModel.kt``'s resolution table.
If the two drift, the preflight validates a different endpoint than the agent
uses and is worse than useless, so ``test_llm_preflight.py`` asserts the tables
match by parsing the Kotlin source.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Dict, Optional, Tuple

# MUST match LLMSettingsViewModel.kt's `when (providerId.lowercase())` block.
# Verified against the client by test_llm_preflight.py; do not edit one alone.
PROVIDER_BASE_URLS: Dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "together": "https://api.together.xyz/v1",
    "groq": "https://api.groq.com/openai/v1",
    "deepinfra": "https://api.deepinfra.com/v1/openai",
}

_TIMEOUT = 30

# Several provider edges sit behind Cloudflare, which rejects requests with no
# User-Agent as bot traffic — returning HTTP 403 with "error code: 1010". That
# is indistinguishable from a real per-model permission denial unless we send
# one, and it made the first version of this preflight report 403 for BOTH groq
# and together while curl succeeded against the same endpoints.
_UA = "ciris-qa-preflight/1.0"


def _post(url: str, key: str, payload: dict) -> Tuple[int, str]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": _UA,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # network/DNS/TLS
        return 0, f"{type(e).__name__}: {e}"


def _extract_message(body: str) -> str:
    try:
        d = json.loads(body)
    except Exception:
        return body[:300].strip()
    err = d.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err)[:300]
    if isinstance(err, str):
        return err[:300]
    return body[:300].strip()


def preflight_llm(provider: str, api_key: Optional[str], model: str) -> Tuple[bool, str]:
    """Make one real completion call. Returns (ok, human-readable diagnosis).

    Every failure names the provider, the resolved base URL, the exact model
    string, the HTTP status, and the provider's own message — so the operator
    can act without reading device logs.
    """
    head = "\n── LLM preflight ─────────────────────────────────────────"

    if not api_key:
        return False, (
            f"{head}\n"
            f"  FAIL: no API key.\n"
            f"  provider={provider!r} model={model or '(provider default)'!r}\n"
            f"  Pass --llm-key or --llm-key-file (default: ~/.groq_key).\n"
            f"  Without a key the wizard configures a mock LLM and the chat step\n"
            f"  cannot produce a real SPEAK, so the trace seal never forms."
        )

    base = PROVIDER_BASE_URLS.get(provider.lower())
    if base is None:
        return False, (
            f"{head}\n"
            f"  FAIL: unknown provider {provider!r}.\n"
            f"  known: {', '.join(sorted(PROVIDER_BASE_URLS))}\n"
            f"  The client resolves the base URL from this name; an unknown name\n"
            f"  means the wizard cannot configure a working endpoint."
        )

    if not model:
        return False, (
            f"{head}\n"
            f"  FAIL: no model specified for provider={provider!r} ({base}).\n"
            f"  Pass --llm-model with the EXACT, CASE-SENSITIVE id from the\n"
            f"  provider's catalog. Case matters: Together lists both\n"
            f"  'google/gemma-4-31B-it' and 'pearl-ai/gemma-4-31b-it'."
        )

    status, body = _post(
        f"{base}/chat/completions",
        api_key,
        {"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1},
    )
    msg = _extract_message(body)

    if status == 200:
        return True, (
            f"{head}\n"
            f"  OK: {provider} / {model}\n"
            f"     {base} answered a live completion."
        )

    # Each of these has been hit for real; the remediation is the point.
    hints = {
        401: "The key is invalid or revoked. Check the key FILE — a stale\n"
        "     ~/.groq_key has caused this before. Re-issue and overwrite it.",
        402: "The key is VALID but the account is out of credit. This is billing,\n"
        "     not configuration — top up, or switch --llm-provider to a funded one.",
        403: "Key valid, access denied for this model. Some models need explicit\n"
        "     enablement or a paid tier (Together's Llama-4 needs a dedicated endpoint).",
        404: "Model not found. Almost always CASE or a wrong prefix. Verify with:\n"
        f"     curl -H 'Authorization: Bearer <key>' {base}/models | grep -i <name>",
        429: "Rate limited. Wait, or use a different provider for this run.",
        0: "Could not reach the endpoint at all — DNS, TLS, or no network.",
    }
    hint = hints.get(status, "Unexpected status; the provider message above is authoritative.")

    return False, (
        f"{head}\n"
        f"  FAIL: HTTP {status} from {provider}\n"
        f"  base_url : {base}\n"
        f"  model    : {model!r}\n"
        f"  provider says: {msg}\n"
        f"  -> {hint}\n"
        f"  Aborting BEFORE the device run: the agent would configure this exact\n"
        f"  key/model and fail at the chat step as 'no SPEAK / ship-unconfirmed',\n"
        f"  which looks like an agent defect but is not one."
    )
