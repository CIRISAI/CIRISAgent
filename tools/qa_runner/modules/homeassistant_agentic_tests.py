"""
Home Assistant live agentic QA tests.

This module is designed to reproduce and evaluate the current Home Assistant
issue cluster by driving the real configuration flow and then probing Music
Assistant behavior with the configured credentials and runtime state.

Environment variables:
    CIRIS_HA_BASE_URL: Required. Home Assistant base URL (for example http://homeassistant.local:8123)
    CIRIS_HA_TEST_USERNAME: Optional. Browser-login username for OAuth automation.
    CIRIS_HA_TEST_PASSWORD: Optional. Browser-login password for OAuth automation.
    CIRIS_HA_RUN_BROWSER_OAUTH: Optional boolean. Defaults to true when username/password are set.
    CIRIS_HA_OAUTH_HEADED: Optional boolean. Launch browser visibly for OAuth automation.
    CIRIS_HA_MEDIA_QUERY: Optional media query for ma_play verification (for example "Enya").
    CIRIS_HA_MEDIA_TYPE: Optional media type for ma_play verification (default: track).
    CIRIS_HA_ENQUEUE: Optional enqueue mode for ma_play verification (default: play).
    CIRIS_HA_PLAYER_ID: Optional explicit player entity_id. If omitted, a bedroom player is preferred automatically.
    CIRIS_HA_RUN_AGENTIC_SMOKE: Optional boolean. When true, submits a full agent prompt and validates audit coverage.
    CIRIS_HA_RUN_AGENTIC_PLAY: Optional boolean. When true, sends a natural-language playback request through the agent.
    CIRIS_HA_AGENTIC_PLAY_PROMPT: Optional override for the natural-language playback request.
"""

import asyncio
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from rich.console import Console

from ciris_adapters.home_assistant.service import HAIntegrationService
from ciris_adapters.home_assistant.tool_service import HAToolService

from .base_test_module import BaseTestModule


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class HomeAssistantAgenticTests(BaseTestModule):
    """Live Home Assistant QA module focused on reproducible adapter + MA behavior."""

    def __init__(
        self,
        client: Any,
        console: Console,
        fail_fast: bool = True,
        test_timeout: float = 30.0,
    ):
        super().__init__(client, console, fail_fast, test_timeout)

        self._base_url = self._get_transport_base_url()
        self.ha_base_url = os.getenv("CIRIS_HA_BASE_URL", "").rstrip("/")
        self.ha_username = os.getenv("CIRIS_HA_TEST_USERNAME", "")
        self.ha_password = os.getenv("CIRIS_HA_TEST_PASSWORD", "")
        self.ha_media_query = os.getenv("CIRIS_HA_MEDIA_QUERY", "").strip()
        self.ha_media_type = os.getenv("CIRIS_HA_MEDIA_TYPE", "track").strip() or "track"
        self.ha_enqueue = os.getenv("CIRIS_HA_ENQUEUE", "play").strip() or "play"
        self.explicit_player_id = os.getenv("CIRIS_HA_PLAYER_ID", "").strip()
        self.run_browser_oauth = _env_flag(
            "CIRIS_HA_RUN_BROWSER_OAUTH",
            default=bool(self.ha_username and self.ha_password),
        )
        self.oauth_headed = _env_flag("CIRIS_HA_OAUTH_HEADED", default=False)
        self.run_agentic_smoke = _env_flag("CIRIS_HA_RUN_AGENTIC_SMOKE", default=False)
        self.run_agentic_play = _env_flag("CIRIS_HA_RUN_AGENTIC_PLAY", default=False)
        self.agentic_play_prompt = (
            os.getenv("CIRIS_HA_AGENTIC_PLAY_PROMPT", "").strip()
            or "Play Teardrop by Massive Attack in the bedroom."
        )

        self.session_id: Optional[str] = None
        self.adapter_id: Optional[str] = None
        self.applied_config: Dict[str, Any] = {}
        self.oauth_url: Optional[str] = None
        self.resolved_player_id: Optional[str] = self.explicit_player_id or None
        self._ha_service: Optional[HAIntegrationService] = None
        self._tool_service: Optional[HAToolService] = None

    def _get_transport_base_url(self) -> str:
        base_url = getattr(self.client, "_base_url", "http://localhost:8080")
        if hasattr(self.client, "_transport") and hasattr(self.client._transport, "base_url"):
            base_url = self.client._transport.base_url
        elif hasattr(self.client, "_transport") and hasattr(self.client._transport, "_base_url"):
            base_url = self.client._transport._base_url
        return str(base_url).rstrip("/")

    def _get_auth_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        token = None
        if hasattr(self.client, "api_key") and self.client.api_key:
            token = self.client.api_key
        elif hasattr(self.client, "_transport"):
            transport = self.client._transport
            if hasattr(transport, "api_key") and transport.api_key:
                token = transport.api_key
            elif hasattr(transport, "_api_key") and transport._api_key:
                token = transport._api_key
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        timeout: float = 60.0,
    ) -> requests.Response:
        url = f"{self._base_url}{path}"
        response = requests.request(
            method=method,
            url=url,
            headers=self._get_auth_headers(),
            params=params,
            json=json_body,
            timeout=timeout,
        )
        return response

    def _response_data(self, response: requests.Response) -> Dict[str, Any]:
        payload = response.json()
        return payload.get("data", {})

    async def run(self) -> List[Dict]:
        self.console.print("\n[cyan]Home Assistant Agentic Tests[/cyan]")

        if not self.ha_base_url:
            self._record_result(
                "environment",
                False,
                "CIRIS_HA_BASE_URL is required for live Home Assistant testing",
            )
            return self.results

        tests = [
            ("homeassistant_reachable", self.test_homeassistant_reachable),
            ("configure_homeassistant_adapter", self.test_configure_homeassistant_adapter),
            ("adapter_loaded", self.test_adapter_loaded),
            ("music_assistant_tools_visible", self.test_music_assistant_tools_visible),
            ("ma_players_direct", self.test_ma_players_direct),
        ]

        if self.ha_media_query:
            tests.append(("ma_play_probe", self.test_ma_play_probe))
        if self.run_agentic_smoke:
            tests.append(("agentic_player_smoke", self.test_agentic_player_smoke))
        if self.run_agentic_play:
            tests.append(("agentic_music_playback", self.test_agentic_music_playback))

        try:
            for test_name, test_func in tests:
                try:
                    await test_func()
                    self._record_result(test_name, True)
                except Exception as exc:
                    self._record_result(test_name, False, str(exc))
                    if self.fail_fast:
                        break
        finally:
            if self._tool_service is not None:
                await self._tool_service.stop()
            if self._ha_service is not None:
                await self._ha_service.cleanup()

        return self.results

    async def test_homeassistant_reachable(self) -> None:
        response = requests.get(f"{self.ha_base_url}/api/", timeout=10)
        if response.status_code not in {200, 401}:
            raise ValueError(f"Home Assistant probe failed with HTTP {response.status_code}")
        self.console.print(f"     [dim]HA probe: HTTP {response.status_code} from {self.ha_base_url}[/dim]")

    async def test_configure_homeassistant_adapter(self) -> None:
        start_response = self._request("POST", "/v1/system/adapters/home_assistant/configure/start")
        if start_response.status_code != 200:
            raise ValueError(f"Could not start config session: HTTP {start_response.status_code}")

        start_data = self._response_data(start_response)
        self.session_id = start_data.get("session_id")
        if not self.session_id:
            raise ValueError("Config session did not return session_id")

        discover_response = self._request(
            "POST",
            f"/v1/system/adapters/configure/{self.session_id}/step",
            json_body={"step_data": {"selected_url": self.ha_base_url}},
        )
        if discover_response.status_code != 200:
            raise ValueError(f"Discovery selection failed: HTTP {discover_response.status_code}")

        oauth_response = self._request(
            "POST",
            f"/v1/system/adapters/configure/{self.session_id}/step",
            json_body={
                "step_data": {
                    "base_url": self.ha_base_url,
                    "callback_base_url": self._base_url,
                }
            },
        )
        if oauth_response.status_code != 200:
            raise ValueError(f"OAuth URL generation failed: HTTP {oauth_response.status_code}")

        oauth_data = self._response_data(oauth_response)
        self.oauth_url = oauth_data.get("data", {}).get("oauth_url")
        if not self.oauth_url:
            raise ValueError("OAuth step did not return an oauth_url")

        if self.run_browser_oauth:
            await self._complete_oauth_via_browser()
        else:
            raise ValueError(
                "Browser OAuth is disabled. Set CIRIS_HA_RUN_BROWSER_OAUTH=1 and CIRIS_HA_TEST_USERNAME/CIRIS_HA_TEST_PASSWORD."
            )

        feature_response = self._request(
            "POST",
            f"/v1/system/adapters/configure/{self.session_id}/step",
            json_body={"step_data": {"selection": "device_control"}},
        )
        if feature_response.status_code != 200:
            raise ValueError(f"Feature selection failed: HTTP {feature_response.status_code}")

        camera_response = self._request(
            "POST",
            f"/v1/system/adapters/configure/{self.session_id}/step",
            json_body={"step_data": {"selection": "skip"}},
        )
        if camera_response.status_code != 200:
            raise ValueError(f"Camera selection failed: HTTP {camera_response.status_code}")

        complete_response = self._request(
            "POST",
            f"/v1/system/adapters/configure/{self.session_id}/complete",
            json_body={"persist": False},
            timeout=120,
        )
        if complete_response.status_code != 200:
            raise ValueError(f"Configuration completion failed: HTTP {complete_response.status_code}")

        complete_data = self._response_data(complete_response)
        if not complete_data.get("success", False):
            raise ValueError(complete_data.get("message", "Configuration completion returned success=false"))

        self.applied_config = complete_data.get("applied_config", {})
        if not self.applied_config.get("base_url"):
            raise ValueError("Applied config missing base_url after successful completion")

        self.console.print("     [dim]Home Assistant OAuth completed and adapter configuration applied[/dim]")

    async def _complete_oauth_via_browser(self) -> None:
        if not self.oauth_url:
            raise ValueError("OAuth URL missing")
        if not self.ha_username or not self.ha_password:
            raise ValueError("CIRIS_HA_TEST_USERNAME and CIRIS_HA_TEST_PASSWORD are required for browser OAuth")

        if shutil.which("npx") is None:
            raise ValueError("npx is required for Playwright browser automation")

        session_name = f"ciris-ha-{self.session_id[:8]}"
        playwright_cmd = self._playwright_cli_command()
        open_cmd = [*playwright_cmd, "--session", session_name, "open", self.oauth_url]
        if self.oauth_headed:
            open_cmd.append("--headed")
        self._run_playwright_command(open_cmd, timeout=60)

        login_script = f"""
async (page) => {{
const username = {json.dumps(self.ha_username)};
const password = {json.dumps(self.ha_password)};

async function clickFirst(candidates) {{
  for (const locator of candidates) {{
    if (await locator.count()) {{
      await locator.first().click();
      return true;
    }}
  }}
  return false;
}}

await page.waitForLoadState('domcontentloaded');
for (let i = 0; i < 90; i += 1) {{
  if (page.url().includes('/oauth/callback')) {{
    await page.waitForLoadState('networkidle').catch(() => null);
    return;
  }}

  const userField = page.locator('input[name="username"], input#username, input[type="text"]').first();
  const passField = page.locator('input[name="password"], input#password, input[type="password"]').first();
  if (await userField.count() && await passField.count()) {{
    await userField.fill(username);
    await passField.fill(password);
    const loginClicked = await clickFirst([
      page.getByRole('button', {{ name: /log in|sign in/i }}),
      page.locator('button[type="submit"]'),
      page.locator('input[type="submit"]'),
      page.locator('mwc-button'),
      page.locator('ha-progress-button'),
      page.locator('ha-button'),
    ]);
    if (!loginClicked) {{
      await passField.press('Enter').catch(() => null);
    }}
    await page.waitForLoadState('networkidle').catch(() => null);
    await page.waitForTimeout(500);
    continue;
  }}

  const authClicked = await clickFirst([
    page.getByRole('button', {{ name: /authorize|allow/i }}),
    page.locator('button[type="submit"]'),
    page.locator('mwc-button'),
    page.locator('ha-progress-button'),
    page.locator('ha-button'),
  ]);
  if (authClicked) {{
    await page.waitForLoadState('networkidle').catch(() => null);
  }}

  if (page.url().includes('/oauth/callback')) {{
    await page.waitForLoadState('networkidle').catch(() => null);
    return;
  }}

  await page.waitForTimeout(500);
}}

throw new Error(`OAuth browser flow stalled at ${{page.url()}}`);
}}
"""
        self._run_playwright_command(
            [*playwright_cmd, "--session", session_name, "run-code", login_script],
            timeout=120,
        )

        await self._wait_for_session_step(expected_index=2, timeout=60.0)

    def _playwright_cli_command(self) -> List[str]:
        return ["npx", "--yes", "--package", "@playwright/cli", "playwright-cli"]

    def _run_playwright_command(self, cmd: List[str], timeout: float) -> str:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        combined = (result.stdout or "") + (result.stderr or "")
        if "### Error" in combined:
            raise ValueError(f"Playwright command reported an error: {combined[-400:]}")
        if result.returncode != 0:
            raise ValueError(f"Playwright command failed: {' '.join(cmd[2:])} :: {combined[-400:]}")
        return combined

    async def _wait_for_session_step(self, expected_index: int, timeout: float) -> None:
        if not self.session_id:
            raise ValueError("Config session missing")

        start = time.time()
        last_step_index = -1
        last_status = "unknown"
        while time.time() - start < timeout:
            response = self._request(
                "GET",
                f"/v1/system/adapters/configure/{self.session_id}/status",
                timeout=30,
            )
            if response.status_code != 200:
                await asyncio.sleep(1.0)
                continue

            data = self._response_data(response)
            current_step_index = data.get("current_step_index", -1)
            status = data.get("status", "unknown")
            last_step_index = current_step_index
            last_status = status
            if current_step_index >= expected_index and status != "awaiting_oauth":
                return
            await asyncio.sleep(1.0)

        raise ValueError(
            f"OAuth session did not advance to step {expected_index} "
            f"(last_step_index={last_step_index}, last_status={last_status})"
        )

    async def test_adapter_loaded(self) -> None:
        adapters_response = self._request("GET", "/v1/system/adapters", timeout=30)
        if adapters_response.status_code != 200:
            raise ValueError(f"Could not list adapters: HTTP {adapters_response.status_code}")

        adapter_data = self._response_data(adapters_response)
        adapters = adapter_data.get("adapters", [])
        for adapter in adapters:
            adapter_type = str(adapter.get("adapter_type", "")).lower()
            if adapter_type in {"homeassistant", "home_assistant"} and adapter.get("is_running", False):
                self.adapter_id = adapter.get("adapter_id")
                break

        if not self.adapter_id:
            raise ValueError("No running Home Assistant adapter found after configuration")

        self.console.print(f"     [dim]Loaded Home Assistant adapter: {self.adapter_id}[/dim]")

    async def test_music_assistant_tools_visible(self) -> None:
        deadline = time.time() + 30.0
        while time.time() < deadline:
            tools_response = self._request("GET", "/v1/system/tools", timeout=30)
            if tools_response.status_code != 200:
                await asyncio.sleep(1.0)
                continue

            payload = tools_response.json()
            raw_tools = payload if isinstance(payload, list) else payload.get("data", payload.get("tools", []))
            names = []
            for tool in raw_tools:
                if isinstance(tool, dict):
                    names.append(tool.get("name", ""))
                else:
                    names.append(str(tool))

            if "ma_players" in names and "ma_play" in names:
                self.console.print("     [dim]Music Assistant tools visible through /v1/system/tools[/dim]")
                return
            await asyncio.sleep(1.0)

        raise ValueError("Music Assistant tools did not appear in /v1/system/tools within 30s")

    async def _ensure_local_tool_service(self) -> HAToolService:
        if self._tool_service is not None:
            return self._tool_service

        oauth_tokens = self.applied_config.get("oauth_tokens", {})
        access_token = self.applied_config.get("access_token") or oauth_tokens.get("access_token")
        refresh_token = self.applied_config.get("refresh_token") or oauth_tokens.get("refresh_token")
        client_id = self.applied_config.get("client_id") or oauth_tokens.get("client_id")
        base_url = self.applied_config.get("base_url") or self.ha_base_url

        if not access_token:
            raise ValueError("Applied configuration did not include an access token")

        if refresh_token:
            os.environ["HOME_ASSISTANT_REFRESH_TOKEN"] = refresh_token
        if client_id:
            os.environ["HOME_ASSISTANT_CLIENT_ID"] = client_id

        self._ha_service = HAIntegrationService()
        self._ha_service.ha_url = base_url
        self._ha_service.ha_token = access_token

        initialized = await self._ha_service.initialize()
        if not initialized:
            raise ValueError("Direct Home Assistant service initialization failed with configured token")

        self._tool_service = HAToolService(self._ha_service)
        await self._tool_service.start()
        await self._tool_service.notify_ha_initialized()
        return self._tool_service

    def _choose_player(self, players: List[Dict[str, Any]]) -> Optional[str]:
        if self.explicit_player_id:
            return self.explicit_player_id

        for player in players:
            haystack = f"{player.get('entity_id', '')} {player.get('name', '')}".lower()
            if "bedroom" in haystack:
                return player.get("entity_id")

        if players:
            return players[0].get("entity_id")
        return None

    async def test_ma_players_direct(self) -> None:
        tool_service = await self._ensure_local_tool_service()
        result = await tool_service.execute_tool("ma_players", {})
        if not result.success:
            raise ValueError(result.error or "ma_players failed")

        payload = result.data or {}
        players = payload.get("players", [])
        if not players:
            raise ValueError("ma_players returned no media players")

        self.resolved_player_id = self._choose_player(players)
        self.console.print(
            f"     [dim]Detected {len(players)} player(s); selected target={self.resolved_player_id or 'none'}[/dim]"
        )

    async def test_ma_play_probe(self) -> None:
        tool_service = await self._ensure_local_tool_service()
        if not self._ha_service:
            raise ValueError("HA service not initialized")

        if not self.resolved_player_id:
            raise ValueError("No target player resolved for ma_play probe")

        before_state = await self._ha_service.get_device_state(self.resolved_player_id)
        before_title = before_state.attributes.get("media_title", "") if before_state else ""
        before_position = before_state.attributes.get("media_position") if before_state else None

        result = await tool_service.execute_tool(
            "ma_play",
            {
                "media_id": self.ha_media_query,
                "player_id": self.resolved_player_id,
                "media_type": self.ha_media_type,
                "enqueue": self.ha_enqueue,
            },
        )

        await asyncio.sleep(2.0)
        after_state = await self._ha_service.get_device_state(self.resolved_player_id)
        after_title = after_state.attributes.get("media_title", "") if after_state else ""
        after_position = after_state.attributes.get("media_position") if after_state else None
        after_status = after_state.state if after_state else "missing"

        false_negative = (
            not result.success
            and after_state is not None
            and (
                after_status in {"playing", "buffering"}
                or (after_title and after_title != before_title)
                or (
                    before_position is not None
                    and after_position is not None
                    and isinstance(before_position, (int, float))
                    and isinstance(after_position, (int, float))
                    and after_position > before_position
                )
            )
        )

        if false_negative:
            raise ValueError(
                "ma_play returned failure but player evidence changed "
                f"(before_title={before_title!r}, after_title={after_title!r}, after_state={after_status!r}, "
                f"error={result.error!r})"
            )

        if not result.success:
            raise ValueError(
                f"ma_play failed without positive playback evidence: {result.error or 'unknown error'} "
                f"(after_state={after_status!r}, after_title={after_title!r})"
            )

        self.console.print(
            f"     [dim]ma_play verified on {self.resolved_player_id}: state={after_status}, title={after_title!r}[/dim]"
        )

    async def test_agentic_player_smoke(self) -> None:
        self._start_sse_monitoring()
        try:
            prompt = (
                "Use Home Assistant tools to list available music players and their current states. "
                "Highlight any bedroom player. Do not change anything."
            )
            interaction = await self._interact(prompt, timeout=max(self.test_timeout, 60.0))
            if interaction.task_id:
                valid_audit = await self._validate_audit_entry(interaction.task_id, "speak")
                if not valid_audit:
                    raise ValueError("Agentic smoke response missing expected audit trail evidence")
            if "bedroom" not in interaction.response.lower() and self.resolved_player_id and "bedroom" in self.resolved_player_id.lower():
                raise ValueError("Agent response did not mention the discovered bedroom player")
        finally:
            self._stop_sse_monitoring()

    def _find_successful_tool_event(self, tool_name: str) -> Optional[Dict[str, Any]]:
        if not self.sse_helper or not hasattr(self.sse_helper, "action_results"):
            return None

        for event in reversed(self.sse_helper.action_results):
            if str(event.get("action_executed", "")).upper() != "TOOL":
                continue
            if not bool(event.get("execution_success", False)):
                continue
            action_text = json.dumps(event.get("action_parameters", {}), sort_keys=True).lower()
            if tool_name.lower() in action_text:
                return event
        return None

    async def _wait_for_media_state(
        self,
        expected_title: str,
        expected_artist: str,
        timeout: float = 20.0,
    ) -> Dict[str, Any]:
        if not self._ha_service or not self.resolved_player_id:
            raise ValueError("HA service or player missing for playback verification")

        deadline = time.time() + timeout
        last_snapshot: Dict[str, Any] = {}
        while time.time() < deadline:
            state = await self._ha_service.get_device_state(self.resolved_player_id)
            attributes = state.attributes if state else {}
            media_title = str(attributes.get("media_title", "") or "")
            media_artist = str(attributes.get("media_artist", "") or "")
            playback_state = str(state.state if state else "missing")
            last_snapshot = {
                "state": playback_state,
                "title": media_title,
                "artist": media_artist,
            }
            if (
                expected_title.lower() in media_title.lower()
                and expected_artist.lower() in media_artist.lower()
                and playback_state in {"playing", "buffering"}
            ):
                return last_snapshot
            await asyncio.sleep(1.0)

        return last_snapshot

    async def test_agentic_music_playback(self) -> None:
        await self._ensure_local_tool_service()
        if not self._ha_service:
            raise ValueError("HA service not initialized")
        if not self.resolved_player_id:
            raise ValueError("No target player resolved for agentic playback")

        before_state = await self._ha_service.get_device_state(self.resolved_player_id)
        before_title = str(before_state.attributes.get("media_title", "") if before_state else "")
        before_artist = str(before_state.attributes.get("media_artist", "") if before_state else "")
        prompt = self.agentic_play_prompt
        if "media_player." not in prompt:
            prompt = (
                "Play Teardrop by Massive Attack on the Home Assistant player "
                f"{self.resolved_player_id}. Then confirm what started playing."
            )

        self._start_sse_monitoring()
        try:
            interaction = await self._interact(
                prompt,
                timeout=max(self.test_timeout, 90.0),
            )
            if interaction.task_id:
                speak_valid = await self._validate_audit_entry(interaction.task_id, "speak")
                task_complete_valid = await self._validate_audit_entry(interaction.task_id, "task_complete")
                if not speak_valid or not task_complete_valid:
                    raise ValueError(
                        "Agentic playback response missing expected SPEAK/TASK_COMPLETE audit evidence"
                    )

            tool_event = self._find_successful_tool_event("ma_play")
            if tool_event is None:
                event_summary = [
                    {
                        "action_executed": event.get("action_executed"),
                        "execution_success": event.get("execution_success"),
                        "action_parameters": event.get("action_parameters"),
                    }
                    for event in getattr(self.sse_helper, "action_results", [])
                ]
                raise ValueError(f"No successful ma_play tool event observed: {event_summary}")

            playback = await self._wait_for_media_state("Teardrop", "Massive Attack", timeout=20.0)
            if not (
                "teardrop" in playback.get("title", "").lower()
                and "massive attack" in playback.get("artist", "").lower()
            ):
                raise ValueError(
                    "Agentic ma_play did not produce the expected track metadata "
                    f"(before_title={before_title!r}, before_artist={before_artist!r}, after={playback})"
                )

            if playback.get("state") not in {"playing", "buffering"}:
                raise ValueError(f"Bedroom player is not active after agentic playback: {playback}")

            self.console.print(
                "     [dim]Agentic playback verified via reasoning stream and player state: "
                f"tool=ma_play state={playback['state']} title={playback['title']!r} "
                f"artist={playback['artist']!r}[/dim]"
            )
        finally:
            self._stop_sse_monitoring()
