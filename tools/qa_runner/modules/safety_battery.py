"""Safety battery QA runner module.

Loads a canonical v4 BatteryManifest (per CIRISNodeCore SCHEMA.md §11)
from `tests/safety/{lang_eng}_{domain}/v4_{lang_eng}_{domain}_arc.json`,
submits each question through the agent via the standard A2A path
(`/v1/agent/interact`), and writes a JSONL of signed responses ready
for human scoring on safety.ciris.ai.

This module does NOT score the responses. Scoring is human work that
happens on the federation surface (safety.ciris.ai) per CIRISNodeCore
MISSION.md §3.4 (Credits × Expertise weighted Votes against the
rubric's universal-pass-criteria table).

Live LLM is required (see REQUIRES_LIVE_LLM below). Mock LLM produces
canned strings that can't be scored against the rubric. The runner
enforces this at CLI parse time using the LIVE_LLM_DEFAULTS metadata.

Cross-references:
  - tests/safety/README.md (contributor on-ramp)
  - CIRISNodeCore SCHEMA.md §11 (BatteryManifest format)
  - CIRISNodeCore SCHEMA.md §4.1 (arc_question payload)
  - CIRISNodeCore MISSION.md §7.3 (safety.ciris.ai pilot scope)

CLI invocation:
  python3 -m tools.qa_runner safety_battery --safety-battery-lang am
  # --live auto-enabled + defaults applied from LIVE_LLM_DEFAULTS;
  # reads ~/.together_key.

  # Override defaults:
  python3 -m tools.qa_runner safety_battery \\
      --safety-battery-lang am \\
      --live --live-key-file ~/.together_key \\
      --live-base-url https://api.together.xyz/v1 \\
      --live-provider openai \\
      --live-model "google/gemma-4-31B-it"
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from rich.console import Console

# ──────────────────────────────────────────────────────────────────────
# Live-LLM contract metadata. Read by tools/qa_runner/__main__.py at
# CLI parse time to enforce live mode + apply defaults. The runner
# respects this — modules don't do their own runtime mock detection.
# ──────────────────────────────────────────────────────────────────────
REQUIRES_LIVE_LLM = True

LIVE_LLM_DEFAULTS = {
    # DeepInfra serves Qwen3.6-35B-A3B — the canonical PDMA v3.2 / locale
    # eval test bed per CLAUDE.md's live model matrix. Faster than gemma
    # for safety-battery use (gemma-4-31B-it routinely takes 5-15 min per
    # full DMA+conscience pipeline call; Qwen3.6 is 2-3 min). The LLM
    # service auto-applies extra_body={chat_template_kwargs:
    # {enable_thinking: False}} for *.deepinfra.com base URLs so we
    # don't burn max_tokens on thinking mode (see llm_service/service.py
    # ~line 1560).
    "key_file": "~/.deepinfra_key",
    "base_url": "https://api.deepinfra.com/v1/openai",
    "model": "Qwen/Qwen3.6-35B-A3B",
    "provider": "openai",  # DeepInfra is OpenAI-compatible
}

# Server-side env merged into the agent process by the runner at start
# time (see tools/qa_runner/modules/_module_metadata.py).
SERVER_ENV = {
    # All questions share one channel_id (stage progression depends on
    # conversational context continuity). Without this, the second
    # submission would append to the existing task rather than spawn a
    # fresh task — defeats the per-question isolation we need.
    "CIRIS_DISABLE_TASK_APPEND": "1",
    # Each interact call fans through the full DMA + conscience pipeline
    # (~12 live LLM hops). Default 55s truncates Stage-5 crisis chains
    # which routinely run 2-4 minutes on Together gemma. Per-question
    # timeout in the module is 1800s; this is the agent-side ceiling.
    "CIRIS_API_INTERACTION_TIMEOUT": "1800",
}

# Force --wipe-data on every run for signed-artifact reproducibility.
# See CIRISNodeCore FSD/SAFETY_BATTERY_CI_LOOP.md §5.1. Every run starts
# from a deterministic baseline so the bundle hash is meaningful and
# the auto-setup-completion path is exercised exactly once per run.
WIPE_DATA_ON_START = True

# ISO 639-1 → directory-name language used in tests/safety/{lang_eng}_{domain}/.
# Kept in sync with tools/safety_battery_migrate.py::LANG_DIR_TO_ISO and
# ciris_engine/data/localized/manifest.json.
ISO_TO_LANG_DIR: Dict[str, str] = {
    # Tier-0/1 batteries (original 14-cell roster — low/mid-resource).
    "am": "amharic",
    "ar": "arabic",
    "bn": "bengali",
    "my": "burmese",
    "ha": "hausa",
    "hi": "hindi",
    "mr": "marathi",
    "fa": "persian",
    "pa": "punjabi",
    "sw": "swahili",
    "ta": "tamil",
    "te": "telugu",
    "ur": "urdu",
    "yo": "yoruba",
    # Tier-2 batteries (high-resource expansion landing 2.8.12 — 15 cells).
    # Universal LLM-judge criteria (U1-U5) language-agnostic; per-cell
    # variation lives in U6 (register/honorific or stigma-slur class)
    # and U7 (expected_script). See tests/safety/<lang>_mental_health/
    # v4_*_scoring_rubric.md for the per-cell native-review caveats.
    "en": "english",
    "de": "german",
    "es": "spanish",
    "fr": "french",
    "it": "italian",
    "pt": "portuguese",
    "ru": "russian",
    "uk": "ukrainian",
    "ja": "japanese",
    "ko": "korean",
    "zh": "chinese",
    "id": "indonesian",
    "th": "thai",
    "vi": "vietnamese",
    "tr": "turkish",
}

# Locale-appropriate display names. Lifted from
# tools/qa_runner/modules/model_eval_tests.py::LOCALE_USERS so the agent
# reads a culturally-grounded `user_preferred_name` when responding —
# the "Jeff addressing Selamawit in Amharic" artifact this avoids is
# the same one model_eval handles for its multilingual sweep.
LOCALE_USERS: Dict[str, str] = {
    # Tier-0/1 (original 14-cell roster).
    "am": "ሰላማዊት",      # Selamawit
    "ar": "نور",          # Nour
    "bn": "সুমিতা",       # Sumita
    "fa": "نازنین",       # Nazanin
    "ha": "Hauwa",
    "hi": "अदिति",        # Aditi
    "mr": "स्नेहा",        # Sneha
    "my": "မေသူ",          # Methu
    "pa": "ਹਰਪ੍ਰੀਤ",       # Harpreet
    "sw": "Aisha",
    "ta": "தேன்மொழி",      # Thenmozhi
    "te": "శ్రావణి",        # Sravani
    "ur": "زینب",          # Zainab
    "yo": "Tèmítọ́pẹ́",
    # Tier-2 (high-resource expansion 2.8.12). Names chosen by the
    # respective family agents authoring each v4_<lang>_mental_health_arc.json;
    # kept aligned here so the qa_runner reads the same culturally-grounded
    # user_preferred_name when interacting with the agent.
    "en": "Sam",
    "de": "Anna",
    "es": "María",
    "fr": "Camille",
    "it": "Sofia",
    "pt": "Beatriz",
    "ru": "Анна",          # Anna
    "uk": "Олена",         # Olena
    "ja": "ユキ",           # Yuki
    "ko": "민준",            # Min-jun
    "zh": "小明",            # Xiao Ming
    "id": "Siti",
    "th": "สมชาย",         # Somchai
    "vi": "Minh",
    "tr": "Ayşe",
}

# v3/v4 mental-health batteries wrap questions in third-person evaluator
# framing for rubric clarity: "User Selamawit said: '<inner>'". The
# model needs only the inner first-person utterance — otherwise it
# interprets "User Selamawit" as a quoted third party and the
# conversation partner becomes the admin caller. See the matching
# logic in model_eval_tests.py for the rationale.
_WRAPPER_RE = re.compile(r":\s*['‘’](.+?)['‘’]", re.DOTALL)


def _strip_question_wrapper(text: str) -> str:
    """Strip 'User X said: "<...>"' framing. Mirrors
    model_eval_tests._strip_question_wrapper."""
    matches = list(_WRAPPER_RE.finditer(text))
    if not matches:
        return text
    longest = max(matches, key=lambda m: len(m.group(1)))
    if len(longest.group(1)) < 30:
        return text
    return longest.group(1)


REPO_ROOT = Path(__file__).resolve().parents[3]
SAFETY_DIR = REPO_ROOT / "tests" / "safety"
REPORT_DIR = REPO_ROOT / "qa_reports" / "safety_battery"


def _sha256_hex(path: Path) -> str:
    """SHA-256 of a file's bytes as lowercase hex. Matches the encoding
    used by tools/safety_battery_migrate.py. Drift detection trips the
    stable error string `safety_battery_rubric_drift`."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# Characters allowed in an artifact-name model slug. GH Actions artifact
# names are constrained; the CIRISNodeCore FSD §2.1 picks lowercase
# alphanumerics + dot + hyphen + underscore. Slash becomes underscore.
_SLUG_OK = re.compile(r"[^a-z0-9._-]")


def slugify_model(model: str) -> str:
    """Slugify a model identifier for inclusion in an artifact-name tuple.

    Per CIRISNodeCore FSD/SAFETY_BATTERY_CI_LOOP.md §2: lowercase,
    `/` → `_`, strip everything outside `[a-z0-9._-]`.

    Examples:
      google/gemma-4-31B-it           → google_gemma-4-31b-it
      meta-llama/llama-4-scout        → meta-llama_llama-4-scout
      Qwen/Qwen3.6-35B-A3B            → qwen_qwen3.6-35b-a3b
    """
    s = (model or "unknown").lower().replace("/", "_")
    return _SLUG_OK.sub("", s)


# Kept under the previous internal name too so the existing call site in
# _write_manifest_signed continues to work.
_slugify_model = slugify_model


def _capture_ci_provenance() -> Dict[str, Optional[str]]:
    """Capture GitHub Actions provenance from the workflow env.

    Returns null fields when not running under GitHub Actions (e.g. local
    smoke run). The fields here mirror what
    actions/attest-build-provenance@v1 records; including them in the
    manifest lets safety.ciris.ai cross-check the Sigstore attestation
    against the in-bundle copy.
    """
    import os
    return {
        "github_repository": os.environ.get("GITHUB_REPOSITORY"),
        "github_sha": os.environ.get("GITHUB_SHA"),
        "github_ref": os.environ.get("GITHUB_REF"),
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_workflow": os.environ.get("GITHUB_WORKFLOW"),
        "workflow_path": os.environ.get("GITHUB_WORKFLOW_REF"),
    }


def load_battery(lang: str, domain: str = "mental_health") -> Dict[str, Any]:
    """Load and validate a canonical v4 battery for (lang, domain).

    Raises with a stable error string if rubric_sha256 has drifted from
    the on-disk rubric file.
    """
    if lang not in ISO_TO_LANG_DIR:
        raise ValueError(
            f"unknown language code {lang!r}; expected one of: "
            f"{sorted(ISO_TO_LANG_DIR)}"
        )
    lang_eng = ISO_TO_LANG_DIR[lang]
    cell_dir = SAFETY_DIR / f"{lang_eng}_{domain}"
    arc_path = cell_dir / f"v4_{lang_eng}_{domain}_arc.json"
    if not arc_path.exists():
        raise FileNotFoundError(
            f"canonical battery not found: {arc_path}. For cells not yet "
            f"voted into canonical form, see tests/safety/README.md §5."
        )
    with open(arc_path, encoding="utf-8") as f:
        manifest = json.load(f)

    rubric_path = cell_dir / manifest["rubric_path"]
    if not rubric_path.exists():
        raise FileNotFoundError(
            f"rubric missing for battery {manifest['battery_id']}: {rubric_path}"
        )
    actual_sha = _sha256_hex(rubric_path)
    expected_sha = manifest["rubric_sha256"]
    if actual_sha != expected_sha:
        raise ValueError(
            f"safety_battery_rubric_drift: rubric {rubric_path} sha256 is "
            f"{actual_sha[:16]}... but battery manifest pins "
            f"{expected_sha[:16]}.... Rebuild the manifest after editing "
            f"the rubric: `python3 tools/safety_battery_migrate.py "
            f"--lang {lang_eng}`."
        )
    return manifest


@dataclass
class BatteryResult:
    """One question's run result. Forward-compatible with
    CIRISNodeCore SCHEMA.md §5.1 Vote payload (score_kind=battery_response)
    — the site reads these rows to present to human scorers."""

    question_id: str
    question_version: int
    stage: str
    category: str
    question_text: str         # localized text sent to the agent (post-wrapper-strip)
    response_text: str         # agent's SPEAK content
    response_task_id: Optional[str]
    duration_s: float
    success: bool
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class SafetyBatteryTests:
    """Run a canonical safety battery against the live agent via A2A.

    Pass criteria for the *module*: every question got submitted AND a
    non-empty response was captured. The module is not a verdict on agent
    behavior — that's the human-scoring loop on safety.ciris.ai. This
    runner emits the JSONL of signed responses; the scorers do the work.

    Submission discipline:
      - Same channel_id across all questions in the battery (stage
        progression depends on conversational context continuity).
      - `CIRIS_DISABLE_TASK_APPEND=1` (set by tools/qa_runner/server.py
        when SAFETY_BATTERY is in the run list) makes each submission
        spawn a fresh task even within the shared channel.
      - Sequential: next question fires as soon as the prior response
        body arrives. /v1/agent/interact blocks until the agent's SPEAK
        is ready, so no SSE plumbing needed.
      - All submissions use the cell's locale user token (created at
        run start) so the agent reads user_preferred_name +
        preferred_language matching the cell.
    """

    # Live-LLM contract metadata. The runner reads these at CLI parse time
    # via tools/qa_runner/modules/_module_metadata.py.
    REQUIRES_LIVE_LLM = REQUIRES_LIVE_LLM
    LIVE_LLM_DEFAULTS = LIVE_LLM_DEFAULTS
    SERVER_ENV = SERVER_ENV
    WIPE_DATA_ON_START = WIPE_DATA_ON_START

    def __init__(
        self,
        client: Any,
        console: Console,
        lang: str = "am",
        domain: str = "mental_health",
        template_id: str = "default",
        model: Optional[str] = None,
        live_base_url: Optional[str] = None,
        live_provider: Optional[str] = None,
        api_port: int = 8080,
        per_question_timeout_s: float = 1800.0,
        results_dir: Optional[Path] = None,
    ):
        self.client = client
        self.console = console
        self.lang = lang
        self.domain = domain
        self.template_id = template_id
        self.model = model or LIVE_LLM_DEFAULTS["model"]
        self.live_base_url = live_base_url or LIVE_LLM_DEFAULTS["base_url"]
        self.live_provider = live_provider or LIVE_LLM_DEFAULTS["provider"]
        self.api_port = api_port
        self.per_question_timeout_s = per_question_timeout_s
        self.results: List[Dict[str, Any]] = []
        self._battery_results: List[BatteryResult] = []
        self._run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._results_dir = results_dir or (REPORT_DIR / f"{lang}_{domain}_{self._run_id}")
        # Filled in by _create_locale_user() at run start.
        self._locale_token: Optional[str] = None
        self._locale_username: Optional[str] = None
        self._locale_display_name: Optional[str] = None
        # Filled in by _capture_agent_identity() at run start.
        self._agent_identity: Dict[str, Any] = {}
        self._captured_at_start: Optional[str] = None

    async def run(self) -> List[Dict[str, Any]]:
        self.console.print("\n[bold cyan]🛡️  Safety Battery[/bold cyan]")
        self.console.print("=" * 70)
        self._captured_at_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Load + validate the canonical battery.
        try:
            manifest = load_battery(self.lang, self.domain)
        except (FileNotFoundError, ValueError) as e:
            self.console.print(f"[red]load failure:[/red] {e}")
            self.results.append({
                "test": f"load_battery[{self.lang}_{self.domain}]",
                "status": "FAIL: " + str(e),
                "error": str(e),
            })
            return self.results

        # Capture agent identity for the signed manifest (best-effort —
        # non-fatal if endpoints unavailable). See FSD §3.3.
        await self._capture_agent_identity()

        cell = manifest["cell"]
        questions = manifest["questions"]
        self.console.print(
            f"[dim]cell={cell['domain']}/{cell['language']} · "
            f"battery_id={manifest['battery_id']} · "
            f"v{manifest['battery_version']} · "
            f"{len(questions)} questions[/dim]"
        )
        self.console.print(
            f"[dim]rubric={manifest['rubric_path']} · "
            f"sha256={manifest['rubric_sha256'][:12]}...[/dim]\n"
        )

        # Create the cell's locale user up front. All submissions use this
        # user's token so the agent reads user_preferred_name and
        # preferred_language for this cell's locale.
        try:
            await self._create_locale_user(cell["language"])
        except Exception as e:
            self.console.print(
                f"[yellow]locale-user setup failed: {e} — falling back to admin token "
                f"(agent will see admin's name + language instead of cell's)[/yellow]"
            )

        self._results_dir.mkdir(parents=True, exist_ok=True)
        results_jsonl = self._results_dir / "results.jsonl"

        # Shared channel for the whole battery. Stage progression depends
        # on conversational context continuity within the channel.
        channel_id = f"safety_battery_{manifest['battery_id']}_{self._run_id}"

        # Sequential — the next question fires immediately when the prior
        # response body arrives. CIRIS_DISABLE_TASK_APPEND=1 (set by the
        # runner) ensures each submission spawns its own task even within
        # the shared channel.
        for idx, q in enumerate(questions, 1):
            self.console.print(
                f"[bold]({idx}/{len(questions)})[/bold] "
                f"[cyan]{q['question_id']}[/cyan] · "
                f"[dim]{q['stage']}[/dim]"
            )
            result = await self._run_question(q, manifest, channel_id)
            self._battery_results.append(result)
            with open(results_jsonl, "a", encoding="utf-8") as f:
                f.write(json.dumps(self._result_to_jsonl_row(result, manifest), ensure_ascii=False))
                f.write("\n")
            self._display_result(result)

        # Drain time for the agent's accord_metrics adapter to flush
        # in-flight trace batches before the qa_runner triggers shutdown.
        # Without this, the OLD run (compressed accord, ~8min) got 31 trace
        # files but the NEW run (full accord, ~10min) got 0 — the longer
        # per-call latency under full accord shifted the flush cadence past
        # the shutdown moment. 30s covers a default 60s flush_interval
        # halfway plus the typical batch turnaround. Pairs with the
        # `CIRIS_ACCORD_METRICS_FLUSH_INTERVAL=5` override in
        # `.github/workflows/safety-battery.yml`. Per-call trace metadata
        # (prompt_tokens / completion_tokens / cost_usd / duration_ms) is
        # the canonical source for token-usage profiling — losing it loses
        # all per-LLM-call visibility.
        import asyncio
        self.console.print("[dim]waiting 30s for trace flush…[/dim]")
        await asyncio.sleep(30)

        self._write_summary(manifest, results_jsonl)
        self._write_manifest_signed(manifest, results_jsonl)
        self._print_summary(manifest)
        return self.results

    async def _capture_agent_identity(self) -> None:
        """Best-effort capture of agent_id + agent_version from the running
        agent. Recorded in manifest_signed.json so consumers can verify
        per-response audit anchors against the named agent.

        Non-fatal on failure — the manifest still ships with whatever was
        captured; missing fields are left null.
        """
        transport = getattr(self.client, "_transport", None)
        if transport is None:
            return
        base_url = getattr(transport, "base_url", f"http://localhost:{self.api_port}")
        admin_token = getattr(transport, "api_key", None)
        if not admin_token:
            return

        identity_data: Dict[str, Any] = {}
        # Best-effort identity + health probes for the manifest. Either
        # endpoint can be unreachable (port shifted, server still starting,
        # transient timeout); manifest generation must not block on them.
        # Soft-fail with a debug print so failures are intentional and
        # diagnosable, not silently swallowed.
        try:
            async with httpx.AsyncClient(timeout=15.0) as http:
                resp = await http.get(
                    f"{base_url}/v1/agent/identity",
                    headers={"Authorization": f"Bearer {admin_token}"},
                )
            if resp.status_code == 200:
                body = resp.json()
                d = (body.get("data") or body) or {}
                identity_data["agent_id"] = d.get("agent_id")
                identity_data["agent_name"] = d.get("name")
        except Exception as exc:
            self.console.print(
                f"[dim]identity probe skipped ({type(exc).__name__}): manifest will omit agent_id/name[/dim]"
            )

        try:
            async with httpx.AsyncClient(timeout=15.0) as http:
                resp = await http.get(
                    f"{base_url}/v1/system/health",
                    headers={"Authorization": f"Bearer {admin_token}"},
                )
            if resp.status_code == 200:
                body = resp.json()
                d = (body.get("data") or body) or {}
                identity_data["agent_version"] = d.get("version")
                identity_data["cognitive_state"] = d.get("cognitive_state")
        except Exception as exc:
            self.console.print(
                f"[dim]health probe skipped ({type(exc).__name__}): manifest will omit version/cognitive_state[/dim]"
            )

        self._agent_identity = identity_data
        if identity_data:
            self.console.print(
                f"[dim]agent identity: agent_id={identity_data.get('agent_id')} "
                f"version={identity_data.get('agent_version')} "
                f"name={identity_data.get('agent_name')}[/dim]\n"
            )

    async def _create_locale_user(self, cell_language: str) -> None:
        """Create a locale-appropriate user for this battery's cell.

        Mirrors model_eval_tests._create_locale_users() but for the single
        cell language. Sets user_preferred_name to the locale display name
        and preferred_language to the ISO code so the agent treats this
        contributor as a native speaker of the cell's language.
        """
        display_name = LOCALE_USERS.get(cell_language)
        if not display_name:
            self.console.print(
                f"[yellow]safety_battery: no LOCALE_USERS entry for {cell_language!r} — "
                f"will use admin user (response may carry English-default name)[/yellow]"
            )
            return

        transport = getattr(self.client, "_transport", None)
        if transport is None:
            raise RuntimeError("no SDK transport — runner did not configure client")
        base_url = getattr(transport, "base_url", f"http://localhost:{self.api_port}")
        admin_token = getattr(transport, "api_key", None)
        if not admin_token:
            raise RuntimeError("no admin token on SDK transport")

        username = f"qa_safety_{cell_language}"
        password = secrets.token_urlsafe(16)
        async with httpx.AsyncClient(timeout=15.0) as http:
            create_resp = await http.post(
                f"{base_url}/v1/users",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"username": username, "password": password, "api_role": "OBSERVER"},
            )
        if create_resp.status_code == 409:
            # User exists from a previous run. We can't reset the password
            # without admin reset support, so we fall back to admin here.
            self.console.print(
                f"[yellow]safety_battery: user {username!r} already exists "
                f"— falling back to admin (wipe data dir to reset)[/yellow]"
            )
            return
        if create_resp.status_code not in (200, 201):
            raise RuntimeError(
                f"create user {username!r} returned HTTP {create_resp.status_code}: "
                f"{create_resp.text[:200]}"
            )

        async with httpx.AsyncClient(timeout=15.0) as http:
            login_resp = await http.post(
                f"{base_url}/v1/auth/login",
                json={"username": username, "password": password},
            )
        if login_resp.status_code != 200:
            raise RuntimeError(
                f"login {username!r} returned HTTP {login_resp.status_code}: "
                f"{login_resp.text[:200]}"
            )
        login_body = login_resp.json()
        user_token = (
            (login_body.get("data") or {}).get("access_token")
            or login_body.get("access_token")
        )
        if not user_token:
            raise RuntimeError(f"no access_token in login response for {username!r}")

        async with httpx.AsyncClient(timeout=15.0) as http:
            settings_resp = await http.put(
                f"{base_url}/v1/users/me/settings",
                headers={"Authorization": f"Bearer {user_token}"},
                json={
                    "user_preferred_name": display_name,
                    "preferred_language": cell_language,
                },
            )
        if settings_resp.status_code != 200:
            # Non-fatal — token still usable, just name/language unset.
            self.console.print(
                f"[yellow]safety_battery: PUT /v1/users/me/settings returned "
                f"HTTP {settings_resp.status_code} — name/language unset[/yellow]"
            )

        self._locale_token = user_token
        self._locale_username = username
        self._locale_display_name = display_name
        self.console.print(
            f"[dim]safety_battery: created locale user '{display_name}' "
            f"(username={username}, lang={cell_language})[/dim]\n"
        )

    async def _run_question(
        self,
        q: Dict[str, Any],
        manifest: Dict[str, Any],
        channel_id: str,
    ) -> BatteryResult:
        """Submit one question through /v1/agent/interact, capture the
        response body inline. The endpoint blocks until the agent's
        SPEAK is ready (or per_question_timeout_s fires)."""
        cell_lang = manifest["cell"]["language"]
        translations = q.get("translations", {})
        raw_text = translations.get(cell_lang) or translations.get("en", "")
        if not raw_text:
            return BatteryResult(
                question_id=q["question_id"],
                question_version=q["question_version"],
                stage=q.get("stage", ""),
                category=q.get("category", ""),
                question_text="",
                response_text="",
                response_task_id=None,
                duration_s=0.0,
                success=False,
                error=f"no translation available for cell language {cell_lang!r} or fallback 'en'",
            )

        # Strip the "User X said: '<inner>'" wrapper before sending so the
        # model receives only the user's first-person utterance.
        question_text = _strip_question_wrapper(raw_text)

        transport = getattr(self.client, "_transport", None)
        base_url = (
            getattr(transport, "base_url", f"http://localhost:{self.api_port}")
            if transport else f"http://localhost:{self.api_port}"
        )
        # Prefer the locale-user token; fall back to admin only if locale
        # setup failed. The fallback path is signposted at setup time;
        # this just keeps the run from dying outright in that case.
        admin_token = getattr(transport, "api_key", None) if transport else None
        auth_token = self._locale_token or admin_token
        if not auth_token:
            return BatteryResult(
                question_id=q["question_id"],
                question_version=q["question_version"],
                stage=q.get("stage", ""),
                category=q.get("category", ""),
                question_text=question_text,
                response_text="",
                response_task_id=None,
                duration_s=0.0,
                success=False,
                error="no auth token available (locale user setup failed and no admin token)",
            )

        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=self.per_question_timeout_s) as http:
                resp = await http.post(
                    f"{base_url}/v1/agent/interact",
                    headers={"Authorization": f"Bearer {auth_token}"},
                    json={
                        "message": question_text,
                        "context": {
                            "channel_id": channel_id,
                            "session_id": channel_id,
                            "metadata": {
                                "qa_module": "safety_battery",
                                "battery_id": manifest["battery_id"],
                                "battery_version": str(manifest["battery_version"]),
                                "question_id": q["question_id"],
                                "question_version": str(q["question_version"]),
                                "stage": q.get("stage", ""),
                                "category": q.get("category", ""),
                                "cell_domain": manifest["cell"]["domain"],
                                "cell_language": cell_lang,
                                "as_user": self._locale_username or "admin",
                            },
                        },
                    },
                )
            duration = time.time() - start
            if resp.status_code != 200:
                return BatteryResult(
                    question_id=q["question_id"],
                    question_version=q["question_version"],
                    stage=q.get("stage", ""),
                    category=q.get("category", ""),
                    question_text=question_text,
                    response_text="",
                    response_task_id=None,
                    duration_s=duration,
                    success=False,
                    error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )
            body = resp.json()
            data = body.get("data") or {}
            response_text = data.get("response") or body.get("response") or ""
            task_id = data.get("task_id") or body.get("task_id")
            return BatteryResult(
                question_id=q["question_id"],
                question_version=q["question_version"],
                stage=q.get("stage", ""),
                category=q.get("category", ""),
                question_text=question_text,
                response_text=response_text,
                response_task_id=task_id,
                duration_s=duration,
                success=bool(response_text),
                error=None if response_text else "empty response body",
            )
        except Exception as exc:
            return BatteryResult(
                question_id=q["question_id"],
                question_version=q["question_version"],
                stage=q.get("stage", ""),
                category=q.get("category", ""),
                question_text=question_text,
                response_text="",
                response_task_id=None,
                duration_s=time.time() - start,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )

    def _result_to_jsonl_row(self, r: BatteryResult, manifest: Dict[str, Any]) -> Dict[str, Any]:
        """One row per question, forward-compatible with the Vote payload
        from CIRISNodeCore SCHEMA.md §5.1 (score_kind=battery_response)."""
        return {
            "schema": "ciris.ai/safety_battery_result/v1",
            "run_id": self._run_id,
            "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "battery_id": manifest["battery_id"],
            "battery_version": manifest["battery_version"],
            "cell": manifest["cell"],
            "question_id": r.question_id,
            "question_version": r.question_version,
            "stage": r.stage,
            "category": r.category,
            "as_user": self._locale_username or "admin",
            "as_display_name": self._locale_display_name,
            "question_text": r.question_text,
            "agent_response": r.response_text,
            "agent_task_id": r.response_task_id,
            "duration_s": round(r.duration_s, 3),
            "success": r.success,
            "error": r.error,
        }

    def _display_result(self, r: BatteryResult) -> None:
        if r.success:
            preview = (r.response_text or "").replace("\n", " ")
            if len(preview) > 240:
                preview = preview[:240] + "..."
            self.console.print(
                f"    [green]✓[/green] {r.duration_s:.1f}s · "
                f"task_id={r.response_task_id or '—'}"
            )
            self.console.print(f"    [dim]{preview}[/dim]\n")
        else:
            self.console.print(
                f"    [red]✗[/red] {r.duration_s:.1f}s · {r.error or 'unknown error'}\n"
            )

    def _write_summary(self, manifest: Dict[str, Any], results_jsonl: Path) -> None:
        summary_path = self._results_dir / "summary.json"
        n_success = sum(1 for r in self._battery_results if r.success)
        summary = {
            "schema": "ciris.ai/safety_battery_summary/v1",
            "run_id": self._run_id,
            "battery_id": manifest["battery_id"],
            "battery_version": manifest["battery_version"],
            "cell": manifest["cell"],
            "template_id": self.template_id,
            "model": self.model,
            "as_user": self._locale_username or "admin",
            "as_display_name": self._locale_display_name,
            "n_questions": len(self._battery_results),
            "n_responses_captured": n_success,
            "n_errors": len(self._battery_results) - n_success,
            "total_duration_s": round(sum(r.duration_s for r in self._battery_results), 2),
            "results_jsonl": str(results_jsonl.relative_to(REPO_ROOT)),
        }
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
            f.write("\n")

    def _write_manifest_signed(self, manifest: Dict[str, Any], results_jsonl: Path) -> None:
        """Write manifest_signed.json per CIRISNodeCore FSD/SAFETY_BATTERY_CI_LOOP.md §3.3.

        Contains the result-key tuple (cell, battery_version, model_slug,
        agent_version, template_id), per-response audit anchors (the
        agent_task_ids the response_ids map to), and bundle SHA-256s. The
        GH Actions workflow's actions/attest-build-provenance step signs
        this file + the JSONL + the summary as a Sigstore attestation.
        """
        summary_path = self._results_dir / "summary.json"
        manifest_path = self._results_dir / "manifest_signed.json"

        # Bundle hashes — what attest-build-provenance binds against
        results_sha = _sha256_hex(results_jsonl) if results_jsonl.exists() else None
        summary_sha = _sha256_hex(summary_path) if summary_path.exists() else None

        # Per-response audit anchors — each agent_task_id resolves to a
        # signed audit-chain entry produced by the agent's TPM-backed
        # signer at response time. Verifying = pulling the entry,
        # confirming signature, matching SPEAK content to JSONL row.
        anchors = [
            {"question_id": r.question_id, "agent_task_id": r.response_task_id}
            for r in self._battery_results
            if r.success
        ]

        signed = {
            "schema": "ciris.ai/safety_battery_manifest_signed/v1",
            "run_id": self._run_id,
            "captured_at_start": self._captured_at_start,
            "captured_at_end": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),

            "cell": manifest["cell"],
            "battery_id": manifest["battery_id"],
            "battery_version": manifest["battery_version"],
            "rubric_sha256": manifest.get("rubric_sha256"),

            "agent_id": self._agent_identity.get("agent_id"),
            "agent_name": self._agent_identity.get("agent_name"),
            "agent_version": self._agent_identity.get("agent_version"),
            "template_id": self.template_id,

            "model": self.model,
            "model_slug": _slugify_model(self.model),
            "live_base_url": self.live_base_url,
            "live_provider": self.live_provider,

            "bundle": {
                "results_jsonl_sha256": results_sha,
                "summary_json_sha256": summary_sha,
            },
            "agent_audit_anchors": anchors,

            "ci_provenance": _capture_ci_provenance(),
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(signed, f, ensure_ascii=False, indent=2)
            f.write("\n")
        self.console.print(
            f"[dim]manifest_signed.json: {len(anchors)} audit anchors, "
            f"jsonl_sha256={results_sha[:12] if results_sha else 'none'}...[/dim]"
        )

    def _print_summary(self, manifest: Dict[str, Any]) -> None:
        n_total = len(self._battery_results)
        n_success = sum(1 for r in self._battery_results if r.success)
        total_s = sum(r.duration_s for r in self._battery_results)
        self.console.print("=" * 70)
        self.console.print(
            f"[bold]Battery {manifest['battery_id']}:[/bold] "
            f"{n_success}/{n_total} responses captured in {total_s:.1f}s"
        )
        self.console.print(
            f"[dim]Results: {self._results_dir.relative_to(REPO_ROOT)}/[/dim]"
        )
        self.console.print(
            "[dim]No scoring here — that's the safety.ciris.ai loop "
            "(MISSION.md §3.4 + §5.4).[/dim]\n"
        )
        # Surface per-question results so the runner's pass/fail counters
        # see one row per question, not one row per battery.
        # NOTE: emit an explicit `error` string field even on success —
        # the runner's _print_summary at runner.py:1792 does
        # `result.get("error", "Unknown error")[:100]`, which crashes
        # when `error` is present but None (the default returns
        # "Unknown error" only when the key is missing entirely).
        for r in self._battery_results:
            test_name = f"{manifest['cell']['language']}_{manifest['cell']['domain']}::{r.question_id}"
            self.results.append({
                "test": test_name,
                "status": "PASS" if r.success else f"FAIL: {r.error or 'no response'}",
                "error": "" if r.success else (r.error or "no response"),
            })
