"""Parallel multi-locale conversation test.

Runs a 3-turn benign conversation in EVERY supported locale (29 languages)
simultaneously, each as its own user with locale-appropriate
`user_preferred_name` and `preferred_language` set. Each user gets their
own auth token and their own channel; turns are sequential within a channel
but channels run in parallel.

This exercises the language-chain plumbing end-to-end:
  1. User creation — POST /v1/users for 29 users in parallel.
  2. Auth — POST /v1/auth/login for each, cache token per locale.
  3. User-profile settings — PUT /v1/users/me/settings to set
     user_preferred_name + preferred_language.
  4. Multi-turn interact — agent.interact() per turn, per channel, with
     each user's token, with continuity preserved across turns.
  5. Validation — every response is non-empty and addresses the user
     (presence of user_preferred_name in at least one turn's response).

Pass criterion: all 29 locales complete all 3 turns with non-empty
agent responses. Failure mode is per-locale visibility — if the Burmese
locale's user can't be created or the agent times out on Tamil, the
result table shows exactly which locale failed at which step.

This is the foundation for true multilingual CI coverage: any future
work that breaks one locale's auth, language-chain delivery, or
channel-isolation surfaces here before it reaches end-users.
"""

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

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

# Three-turn benign conversation. Sent in English to every locale; each
# user has preferred_language set so the agent's localization chain delivers
# the response in their target locale. This isolates the "agent uses my
# preferred language" infrastructure from per-locale message-translation
# concerns.
CONVO_TURNS: List[str] = [
    "Hello! I'd like some advice about journaling for self-reflection. "
    "I'm new to it.",
    "What's a good prompt for a beginner who wants to journal in the evening?",
    "Thank you, that's exactly what I needed.",
]


@dataclass
class LocaleResult:
    """Outcome for a single locale's conversation."""

    locale: str
    user_preferred_name: str
    user_id: Optional[str] = None
    token_acquired: bool = False
    settings_set: bool = False
    turns_completed: int = 0
    turn_response_lengths: List[int] = field(default_factory=list)
    name_addressed: bool = False
    total_seconds: float = 0.0
    error: Optional[str] = None

    @property
    def passed(self) -> bool:
        return (
            self.token_acquired
            and self.settings_set
            and self.turns_completed == len(CONVO_TURNS)
            and self.error is None
        )


class ParallelLocalesTests:
    """Run the 3-turn convo across all 29 locales in parallel."""

    def __init__(
        self,
        client: Any,
        console: Console,
        max_concurrency: int = 12,
        per_turn_timeout: float = 120.0,
    ):
        self.client = client
        self.console = console
        self.max_concurrency = max(1, max_concurrency)
        self.per_turn_timeout = per_turn_timeout
        self.results: List[Dict[str, Any]] = []
        self._locale_results: List[LocaleResult] = []

    async def run(self) -> List[Dict[str, Any]]:
        self.console.print("\n[bold cyan]🌐 Parallel Locales Conversation Test[/bold cyan]")
        self.console.print("=" * 70)
        self.console.print(
            f"[dim]Running {len(LOCALE_USERS)} locales × {len(CONVO_TURNS)} turns "
            f"= {len(LOCALE_USERS) * len(CONVO_TURNS)} interactions, "
            f"max {self.max_concurrency} channels in flight.[/dim]\n"
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
                self._run_locale_conversation(base_url, admin_token, locale, name, semaphore)
            )
            for locale, name in LOCALE_USERS.items()
        ]
        completed = 0
        for coro in asyncio.as_completed(tasks):
            result = await coro
            completed += 1
            self._locale_results.append(result)
            badge = "[green]✓[/green]" if result.passed else "[red]✗[/red]"
            self.console.print(
                f"  {badge} ({completed:02d}/{len(LOCALE_USERS)}) "
                f"{result.locale} ({result.user_preferred_name}) — "
                f"{result.turns_completed}/{len(CONVO_TURNS)} turns, "
                f"{result.total_seconds:.1f}s"
                + (f" — [yellow]{result.error}[/yellow]" if result.error else "")
            )

        self._print_summary()
        self._record_results()
        return self.results

    async def _run_locale_conversation(
        self,
        base_url: str,
        admin_token: str,
        locale: str,
        user_preferred_name: str,
        semaphore: asyncio.Semaphore,
    ) -> LocaleResult:
        """Create user, login, set settings, run 3-turn convo. Bounded by semaphore."""
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

                # 4) Multi-turn conversation in the user's own channel.
                channel_id = f"parallel_locales_{locale}"
                for turn_idx, content in enumerate(CONVO_TURNS, 1):
                    turn_response = await self._send_turn(
                        base_url, user_token, channel_id, content, locale, turn_idx
                    )
                    if turn_response is None:
                        result.error = f"turn {turn_idx} timeout/empty"
                        break
                    result.turns_completed += 1
                    result.turn_response_lengths.append(len(turn_response))
                    if user_preferred_name in turn_response:
                        result.name_addressed = True
            except Exception as exc:
                result.error = f"{type(exc).__name__}: {exc}"
            finally:
                result.total_seconds = time.time() - start

        return result

    async def _send_turn(
        self,
        base_url: str,
        user_token: str,
        channel_id: str,
        content: str,
        locale: str,
        turn_idx: int,
    ) -> Optional[str]:
        """Send one turn via /v1/agent/interact, return the response text or None on failure."""
        async with httpx.AsyncClient(timeout=self.per_turn_timeout) as http:
            try:
                resp = await http.post(
                    f"{base_url}/v1/agent/interact",
                    headers={"Authorization": f"Bearer {user_token}"},
                    json={
                        "message": content,
                        "context": {
                            "channel_id": channel_id,
                            "session_id": channel_id,
                            "metadata": {
                                "qa_module": "parallel_locales",
                                "language": locale,
                                "turn": str(turn_idx),
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

        self.console.print()
        self.console.print(
            f"[bold]Summary:[/bold] {passed}/{total} locales completed all turns; "
            f"{named}/{total} addressed user by name; "
            f"avg per-locale wall-clock {avg_seconds:.1f}s"
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
                else:
                    step = f"turn {r.turns_completed + 1}"
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
                        "turns_completed": r.turns_completed,
                        "turns_total": len(CONVO_TURNS),
                        "name_addressed": r.name_addressed,
                        "response_lengths": r.turn_response_lengths,
                    },
                }
            )
