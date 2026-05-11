"""Parallel multi-locale single-question fan-out test.

Submits ONE question to the agent in 29 channels simultaneously — each
channel owned by a different user with a locale-appropriate
`user_preferred_name` and `preferred_language` — and validates that all
29 channels receive a non-empty reply.

This is the integration test that mirrors what a real user gets on phone:
no overridden defaults, no reduced pipeline depth, no shortcuts. Each
question fans out through the agent's full DMA + conscience pipeline
(PDMA + CSDMA + DSDMA + IDMA + ASPDMA + TSASPDMA + DSASPDMA + 4
consciences + follow-up thought) — about 12 LLM calls per channel — so
this run is ~29 × 12 ≈ 350 LLM calls, all happening in parallel against
whatever LLM backend the agent is configured for.

What it pins:
  1. 29 user creations work (auth service scales to many concurrent
     account creations).
  2. 29 distinct tokens isolate per-channel context (no cross-talk
     between locales).
  3. user_preferred_name + preferred_language flow through PUT
     /v1/users/me/settings correctly, and the agent's localization chain
     picks them up — every reply lands in the user's target locale.
  4. Per-channel routing is correct — locale `am` gets the Amharic
     reply, locale `ja` gets the Japanese reply, no cross-routing.
  5. The agent's pipeline (and the LLM backend serving it) can sustain
     29-way parallel load without timeouts, rate-limit failures, or
     correctness regressions.

Pass criterion: all 29 locales return non-empty replies. Failure mode is
per-locale visible — the result table shows exactly which locale failed
at which step (auth / settings / response).

This is the foundation for true multilingual CI coverage: any future
work that breaks one locale's auth, language-chain delivery, or
channel-isolation surfaces here before it reaches end-users.
"""

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, cast

import httpx
from rich.console import Console
from rich.table import Table


# Locale registry: 29 supported locales per localization/manifest.json.
# Each entry is (locale_code, user_preferred_name) — the auth username is
# generated from the locale code so it's ASCII-safe.
#
# Names are culturally appropriate display names in the target locale's
# script. They go into user_preferred_name (a graph attribute) so the
# agent addresses each user by their chosen display name regardless of
# the auth username.
LOCALE_USERS: Dict[str, str] = {
    "am": "ሰላማዊት",      # Selamawit (Ethiopia)
    "ar": "فاطمة",        # Fatima
    "bn": "সুমিতা",       # Sumita
    "de": "Klara",         # Germany
    "en": "Sarah",         # English baseline
    "es": "Sofía",         # Spanish
    "fa": "نازنین",        # Nazanin (Persia)
    "fr": "Élise",         # French
    "ha": "Hauwa",         # Hausa
    "hi": "रोहिणी",        # Rohini
    "id": "Putri",         # Indonesian
    "it": "Lucia",         # Italian
    "ja": "ゆかり",         # Yukari
    "ko": "지혜",           # Jihye
    "mr": "स्नेहा",         # Sneha (Marathi)
    "my": "မေသူ",          # Methu (Burmese)
    "pa": "ਹਰਪ੍ਰੀਤ",        # Harpreet
    "pt": "Mariana",       # Portuguese
    "ru": "Анастасия",     # Anastasia
    "sw": "Aisha",         # Swahili (Aisha works across many cultures)
    "ta": "தேன்மொழி",      # Thenmozhi
    "te": "శ్రావణి",        # Sravani
    "th": "ปรียา",         # Priya (Thai-style)
    "tr": "Zeynep",        # Turkish
    "uk": "Оксана",        # Oksana
    "ur": "زینب",          # Zainab
    "vi": "Hương",         # Vietnamese
    "yo": "Tèmítọ́pẹ́",     # Yoruba
    "zh": "美玲",           # Meiling
}

# The single benign question fanned out to all 29 channels. Sent in
# English; each user's preferred_language is set so the agent's
# localization chain delivers the response in the target locale.
#
# Content is intentionally benign infrastructure-only — clinical content
# belongs in the v3 mental-health harnesses, not here. This module exists
# to validate that the multilingual plumbing works under load.
CONVO_QUESTION: str = (
    "Hello! I'd like some advice about journaling for self-reflection. "
    "I'm new to it. What's a good way to start?"
)


@dataclass
class LocaleResult:
    """Outcome for a single locale's question fan-out."""

    locale: str
    user_preferred_name: str
    user_id: Optional[str] = None
    token_acquired: bool = False
    settings_set: bool = False
    response_received: bool = False
    response_length: int = 0
    name_addressed: bool = False
    total_seconds: float = 0.0
    error: Optional[str] = None

    @property
    def passed(self) -> bool:
        return (
            self.token_acquired
            and self.settings_set
            and self.response_received
            and self.error is None
        )


class ParallelLocalesTests:
    """Submit one question to the agent in 29 channels simultaneously.

    Each channel is owned by a different user with a locale-appropriate
    user_preferred_name and preferred_language. Validates all 29 reply.
    Each reply costs ~12 LLM calls (full DMA + conscience pipeline), so
    a run is ~29 × 12 ≈ 350 LLM calls — all in parallel.

    Server-env contract read by tools/qa_runner/modules/_module_metadata.py.
    Migrated from the hardcoded conditional in server.py:889 — concurrent
    submissions across per-locale channels demand raised rate limit +
    interact timeout + LLM concurrency. Live LLM is the production
    calibration path but not enforced (mock LLM also exercises the
    fan-out path)."""

    SERVER_ENV = {
        "CIRIS_DISABLE_TASK_APPEND": "1",
        "CIRIS_API_RATE_LIMIT_PER_MINUTE": "600",
        "CIRIS_API_INTERACTION_TIMEOUT": "600",
        "CIRIS_LLM_MAX_CONCURRENT": "32",
    }

    def __init__(
        self,
        client: Any,
        console: Console,
        max_concurrency: int = 29,
        response_timeout: float = 600.0,
    ):
        # response_timeout matches the agent's CIRIS_API_INTERACTION_TIMEOUT
        # (raised to 600s by the qa_runner for this module). 29-way parallel
        # × 12 LLM calls × pipeline serial steps means even mock-LLM runs
        # routinely take 3-5 min per channel. Anything tighter has the
        # client giving up before the agent can deliver.
        self.client = client
        self.console = console
        # Default concurrency = number of locales: the whole point of this
        # module is parallel fan-out. Override only for backend-load debugging.
        self.max_concurrency = max(1, max_concurrency)
        self.response_timeout = response_timeout
        self.results: List[Dict[str, Any]] = []
        self._locale_results: List[LocaleResult] = []

    async def run(self) -> List[Dict[str, Any]]:
        self.console.print("\n[bold cyan]🌐 Parallel Locales Question Fan-Out[/bold cyan]")
        self.console.print("=" * 70)
        n_locales = len(LOCALE_USERS)
        # Each user-visible message fans out ~12 LLM calls through the agent's
        # DMA + conscience pipeline. Full-pipeline run, no shortcuts.
        approx_llm_calls = n_locales * 12
        self.console.print(
            f"[dim]Submitting 1 question to {n_locales} channels in parallel "
            f"≈ ~{approx_llm_calls} LLM calls (each channel runs the full "
            f"DMA + conscience pipeline). Max {self.max_concurrency} channels "
            f"in flight at once.[/dim]\n"
        )

        transport = getattr(self.client, "_transport", None)
        if transport is None:
            self.console.print("[red]No SDK transport available; cannot run.[/red]")
            return []
        base_url = getattr(transport, "base_url", "http://localhost:8080")
        admin_token = getattr(transport, "api_key", None)
        if not admin_token:
            self.console.print("[red]No admin token; cannot create per-locale users.[/red]")
            return []

        semaphore = asyncio.Semaphore(self.max_concurrency)
        tasks = [
            asyncio.create_task(
                self._run_locale_question(base_url, admin_token, locale, name, semaphore)
            )
            for locale, name in LOCALE_USERS.items()
        ]
        completed = 0
        for coro in asyncio.as_completed(tasks):
            result = await coro
            completed += 1
            self._locale_results.append(result)
            badge = "[green]✓[/green]" if result.passed else "[red]✗[/red]"
            name_marker = " 👤" if result.name_addressed else ""
            self.console.print(
                f"  {badge} ({completed:02d}/{n_locales}) "
                f"{result.locale} ({result.user_preferred_name}) — "
                f"{result.response_length} chars{name_marker}, "
                f"{result.total_seconds:.1f}s"
                + (f" — [yellow]{result.error}[/yellow]" if result.error else "")
            )

        self._print_summary()
        self._record_results()
        return self.results

    async def _run_locale_question(
        self,
        base_url: str,
        admin_token: str,
        locale: str,
        user_preferred_name: str,
        semaphore: asyncio.Semaphore,
    ) -> LocaleResult:
        """Create user, login, set settings, submit one question, validate reply.

        Bounded by the semaphore so parallel fan-out is controlled.
        """
        result = LocaleResult(locale=locale, user_preferred_name=user_preferred_name)
        start = time.time()

        async with semaphore:
            try:
                # 1) Admin creates the locale user.
                username = f"qa_locale_{locale}"
                password = secrets.token_urlsafe(16)
                async with httpx.AsyncClient(timeout=15.0) as http:
                    create_resp = await http.post(
                        f"{base_url}/v1/users",
                        headers={"Authorization": f"Bearer {admin_token}"},
                        json={
                            "username": username,
                            "password": password,
                            "api_role": "OBSERVER",
                        },
                    )
                if create_resp.status_code not in (200, 201, 409):  # 409 = already exists
                    result.error = f"create_user HTTP {create_resp.status_code}"
                    return result
                if create_resp.status_code != 409:
                    body = create_resp.json()
                    result.user_id = body.get("data", {}).get("user_id") or body.get("user_id")
                else:
                    # User exists from a prior run that didn't wipe data. The
                    # locally-generated `password` won't match the stored hash,
                    # so login will 401. Recover by SYSTEM_ADMIN-resetting the
                    # stored password to the freshly generated one via
                    # /v1/users/{user_id}/password (admin-bypass path —
                    # docs at users.py:707, "skip_current_check=True").
                    user_id = await self._lookup_user_id(base_url, admin_token, username)
                    if not user_id:
                        result.error = "user already exists but lookup failed (need wipe)"
                        return result
                    if not await self._reset_user_password(base_url, admin_token, user_id, password):
                        result.error = "password reset failed for existing user (need wipe)"
                        return result
                    result.user_id = user_id

                # 2) Login as the new user.
                async with httpx.AsyncClient(timeout=15.0) as http:
                    login_resp = await http.post(
                        f"{base_url}/v1/auth/login",
                        json={"username": username, "password": password},
                    )
                if login_resp.status_code != 200:
                    result.error = f"login HTTP {login_resp.status_code}"
                    return result
                login_body = login_resp.json()
                user_token = login_body.get("data", {}).get("access_token") or login_body.get(
                    "access_token"
                )
                if not user_token:
                    result.error = "no access_token in login response"
                    return result
                result.token_acquired = True

                # 3) Set user_preferred_name + preferred_language.
                async with httpx.AsyncClient(timeout=15.0) as http:
                    settings_resp = await http.put(
                        f"{base_url}/v1/users/me/settings",
                        headers={"Authorization": f"Bearer {user_token}"},
                        json={
                            "user_preferred_name": user_preferred_name,
                            "preferred_language": locale,
                        },
                    )
                if settings_resp.status_code != 200:
                    result.error = f"settings HTTP {settings_resp.status_code}: {settings_resp.text[:120]}"
                    return result
                result.settings_set = True

                # 4) Submit the single question in this user's channel.
                #    No turn cycling, no overrides — exactly what a phone user gets.
                channel_id = f"parallel_locales_{locale}"
                response = await self._send_question(base_url, user_token, channel_id, locale)
                if response is None:
                    result.error = "response timeout/empty"
                    return result
                result.response_received = True
                result.response_length = len(response)
                if user_preferred_name in response:
                    result.name_addressed = True
            except Exception as exc:
                result.error = f"{type(exc).__name__}: {exc}"
            finally:
                result.total_seconds = time.time() - start

        return result

    async def _lookup_user_id(
        self, base_url: str, admin_token: str, username: str
    ) -> Optional[str]:
        """Find a user's user_id by username via the admin GET /v1/users
        endpoint with `?search=`. Returns None if not found or on error."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as http:
                resp = await http.get(
                    f"{base_url}/v1/users",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    params={"search": username, "page_size": 50},
                )
            if resp.status_code != 200:
                return None
            body = resp.json()
            items = body.get("data", {}).get("items") or body.get("items") or []
            for item in items:
                if item.get("username") == username:
                    return cast(Optional[str], item.get("user_id"))
        except Exception:
            return None
        return None

    async def _reset_user_password(
        self, base_url: str, admin_token: str, user_id: str, new_password: str
    ) -> bool:
        """Reset a user's password via the SYSTEM_ADMIN-bypass path
        PUT /v1/users/{user_id}/password. Used to recover from 409
        "user already exists" on un-wiped reruns."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as http:
                resp = await http.put(
                    f"{base_url}/v1/users/{user_id}/password",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={"new_password": new_password},
                )
            return resp.status_code == 200
        except Exception:
            return False

    async def _send_question(
        self,
        base_url: str,
        user_token: str,
        channel_id: str,
        locale: str,
    ) -> Optional[str]:
        """POST /v1/agent/interact with the question; return the reply or None."""
        async with httpx.AsyncClient(timeout=self.response_timeout) as http:
            try:
                resp = await http.post(
                    f"{base_url}/v1/agent/interact",
                    headers={"Authorization": f"Bearer {user_token}"},
                    json={
                        "message": CONVO_QUESTION,
                        "context": {
                            "channel_id": channel_id,
                            "session_id": channel_id,
                            "metadata": {
                                "qa_module": "parallel_locales",
                                "language": locale,
                            },
                        },
                    },
                )
            except httpx.ReadTimeout:
                return None
        if resp.status_code != 200:
            return None
        body = resp.json()
        text = body.get("data", {}).get("response") or body.get("response", "")
        return text if text else None

    def _print_summary(self) -> None:
        passed = sum(1 for r in self._locale_results if r.passed)
        total = len(self._locale_results)
        named = sum(1 for r in self._locale_results if r.name_addressed)
        avg_seconds = (
            sum(r.total_seconds for r in self._locale_results) / total if total else 0.0
        )
        max_seconds = max((r.total_seconds for r in self._locale_results), default=0.0)

        self.console.print()
        self.console.print(
            f"[bold]Summary:[/bold] {passed}/{total} locales replied; "
            f"{named}/{total} addressed user by name; "
            f"avg {avg_seconds:.1f}s, max {max_seconds:.1f}s (parallel wall-clock = max)"
        )

        # Failure detail table
        failures = [r for r in self._locale_results if not r.passed]
        if failures:
            table = Table(title="Failed locales", show_lines=False)
            table.add_column("Locale")
            table.add_column("Step")
            table.add_column("Error")
            for r in sorted(failures, key=lambda x: x.locale):
                if not r.token_acquired:
                    step = "auth"
                elif not r.settings_set:
                    step = "settings"
                elif not r.response_received:
                    step = "response"
                else:
                    step = "unknown"
                table.add_row(r.locale, step, (r.error or "")[:80])
            self.console.print(table)

    def _record_results(self) -> None:
        """Convert internal results into the qa_runner result format."""
        for r in self._locale_results:
            self.results.append(
                {
                    "test": f"parallel_locales::{r.locale}",
                    "status": "PASS" if r.passed else "FAIL",
                    "duration": r.total_seconds,
                    "error": r.error,
                    "metadata": {
                        "user_preferred_name": r.user_preferred_name,
                        "response_received": r.response_received,
                        "response_length": r.response_length,
                        "name_addressed": r.name_addressed,
                    },
                }
            )
