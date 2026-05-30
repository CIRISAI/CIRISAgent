"""Federation screen walk-test.

Drives the CIRIS desktop app's federation (Network) screens through the
TestAutomationServer on :8091 and reports which canonical testTags from
`federation_screen_tags` are present / missing / wrong.

The walk-test is the contract: the upcoming Compose-side `testable` /
`testableClickable` pass is guided by exactly which tags this test
demands. When a tag is missing, the report emits

    MISSING_TAG: <tag>  on  <screen>

so the next agent knows what to wire up.

Flow:
1. login
2. navigate to Network hub
3. verify HUB_REQUIRED_TAGS
4. for each screen in SCREENS: click nav tile, verify root + probes, click targets, refresh, back
5. mode-change flow: PROXY → CLIENT (cancel) → CLIENT (confirm) → PROXY (confirm)
6. add-peer flow: Peers → add → invalid input → error → cancel
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .desktop_app_helper import DesktopAppHelper, ElementInfo
from .federation_screen_tags import (
    BTN_MODE_CANCEL,
    BTN_MODE_CLIENT,
    BTN_MODE_CONFIRM,
    BTN_MODE_PROXY,
    DIALOG_MODE_CONFIRM,
    HUB_REQUIRED_TAGS,
    NETWORK_HUB,
    SCREENS,
    FederationScreen,
)
from .federation_walk_report import (
    AddPeerFlowResult,
    DiagnosticSnapshot,
    FederationWalkReport,
    HubCheckResult,
    ModeFlowResult,
    ScreenWalkResult,
    WalkStatus,
)

# Tags for the add-peer dialog (Peers screen). Documented here, used below.
BTN_ADD_PEER = "btn_add_peer"
DIALOG_ADD_PEER = "dialog_add_peer"
INPUT_ADD_PEER_CODE = "input_add_peer_code"
BTN_ADD_PEER_SUBMIT = "btn_add_peer_submit"
BTN_ADD_PEER_CANCEL = "btn_add_peer_cancel"
TEXT_ADD_PEER_ERROR = "text_add_peer_error"

INVALID_NODE_CODE = "CIRIS-V1-INVALID"

# Screen-name guesses for the desktop wait_for_screen() check after nav.
# If your route doesn't surface a screen name, the walk still verifies via
# the root testTag, which is the real source of truth.
NETWORK_SCREEN_NAME = "Network"


class FederationWalkTest:
    """Drives the desktop app through the federation suite.

    Args:
        helper: an already-started DesktopAppHelper
        verbose: prints progress messages while walking
        navigate_timeout_ms: timeout for each nav transition
        login_username/password: credentials used by the login step

    Returns from `run()`: a FederationWalkReport.
    """

    def __init__(
        self,
        helper: DesktopAppHelper,
        verbose: bool = False,
        navigate_timeout_ms: int = 3000,
        login_username: str = "admin",
        login_password: str = "qa_test_password_12345",
    ) -> None:
        self.helper = helper
        self.verbose = verbose
        self.navigate_timeout_ms = navigate_timeout_ms
        self.login_username = login_username
        self.login_password = login_password
        self.report = FederationWalkReport()

    # ─── Logging ──────────────────────────────────────────────────
    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"  [walk] {msg}")

    # ─── Diagnostic capture ───────────────────────────────────────
    async def _capture_diagnostic(self) -> DiagnosticSnapshot:
        """Snapshot the current screen + visible tags for failure context."""
        try:
            status = await self.helper.status()
            return DiagnosticSnapshot(
                screen=str(status.get("screen", "unknown")),
                visible_tags=list(status.get("elements", [])),
                element_count=int(status.get("count", 0)),
            )
        except Exception as e:  # noqa: BLE001 — best-effort diagnostic
            return DiagnosticSnapshot(screen=f"<diagnostic-error: {e}>")

    # ─── Helpers ──────────────────────────────────────────────────
    async def _present_tags(self, tags: List[str]) -> Dict[str, Optional[ElementInfo]]:
        """Resolve each tag via /element. None = missing."""
        result: Dict[str, Optional[ElementInfo]] = {}
        for tag in tags:
            try:
                elem = await self.helper.get_element(tag)
            except Exception:  # noqa: BLE001 — treat any helper error as "missing"
                elem = None
            result[tag] = elem
        return result

    async def _missing(self, tags: List[str]) -> List[str]:
        present = await self._present_tags(tags)
        return [t for t, e in present.items() if e is None]

    async def _try_click(self, tag: str) -> bool:
        """Best-effort click — returns True if it succeeded."""
        try:
            return await self.helper.click(tag)
        except Exception:  # noqa: BLE001 — testable() (not testableClickable()) raises
            return False

    async def _navigate_to_hub(self) -> bool:
        """Open Network hub via standard nav; tolerate either path."""
        # Try the high-level navigate_to first (uses menu pattern); if the
        # menu doesn't list Network yet, fall back to direct hub-root probe.
        try:
            ok = await self.helper.navigate_to(NETWORK_SCREEN_NAME, timeout_ms=self.navigate_timeout_ms)
            if ok:
                return True
        except Exception:  # noqa: BLE001
            pass
        # Fallback: if the hub root is already visible we're done
        return await self.helper.is_element_visible(NETWORK_HUB)

    async def _back_to_hub(self) -> bool:
        """Best-effort back-nav to the Network hub between screen visits.

        The canonical "drop me at the hub" path is the EpistemicSidebar's
        Network row (helper.navigate_to("Network")) — the sidebar is always
        visible post-login, so a single click on `nav_epistemic_network`
        reliably routes back to the hub. We try a legacy back button first
        for screens that have one, then fall through to sidebar nav.
        """
        # Try the system back button (common testTag) then re-verify hub root.
        for back_tag in ("btn_back", "btn_top_back", "btn_nav_back"):
            try:
                if await self.helper.is_element_visible(back_tag):
                    await self._try_click(back_tag)
                    await asyncio.sleep(0.25)
                    break
            except Exception:  # noqa: BLE001
                continue
        # Re-verify hub root visible — if not, route through the sidebar
        # (the canonical path post-2.9.4).
        if await self.helper.is_element_visible(NETWORK_HUB):
            return True
        return await self._navigate_to_hub()

    # ─── Step: login ──────────────────────────────────────────────
    async def _step_login(self) -> bool:
        self._log("login")
        try:
            ok = await self.helper.login(self.login_username, self.login_password)
            self.report.login_success = bool(ok)
            return self.report.login_success
        except Exception as e:  # noqa: BLE001
            self.report.fatal_reason = f"login raised: {e}"
            return False

    # ─── Step: hub verification ──────────────────────────────────
    async def _step_hub(self) -> None:
        self._log("verify hub")
        result = HubCheckResult()
        if not await self._navigate_to_hub():
            result.status = WalkStatus.FAIL
            result.reason = "Network hub not reachable from menu"
            result.diagnostic = await self._capture_diagnostic()
            self.report.hub_check = result
            return

        missing = await self._missing(HUB_REQUIRED_TAGS)
        if missing:
            result.status = WalkStatus.FAIL
            result.reason = f"{len(missing)}/{len(HUB_REQUIRED_TAGS)} hub tags missing"
            result.missing_tags = missing
            result.diagnostic = await self._capture_diagnostic()
        else:
            result.status = WalkStatus.PASS
            result.reason = "all hub tags present"
        self.report.hub_check = result

    # ─── Step: per-screen walk ───────────────────────────────────
    async def _walk_screen(self, key: str, screen: FederationScreen) -> ScreenWalkResult:
        self._log(f"screen: {screen.name}")
        r = ScreenWalkResult(
            screen_key=key,
            screen_name=screen.name,
            nav_tile=screen.nav_tile,
            root_tag=screen.root,
        )

        # Ensure hub is showing (or recover)
        if not await self.helper.is_element_visible(NETWORK_HUB):
            if not await self._navigate_to_hub():
                r.status = WalkStatus.SKIP
                r.reason = "could not return to hub before walk"
                r.diagnostic = await self._capture_diagnostic()
                return r

        # Click the nav tile (must be present on the hub)
        if not await self.helper.is_element_visible(screen.nav_tile):
            r.status = WalkStatus.FAIL
            r.reason = f"nav tile missing on hub: {screen.nav_tile}"
            r.missing_tags = [screen.nav_tile]
            r.diagnostic = await self._capture_diagnostic()
            return r

        if not await self._try_click(screen.nav_tile):
            r.status = WalkStatus.FAIL
            r.reason = f"nav tile not clickable: {screen.nav_tile}"
            r.failed_targets = [screen.nav_tile]
            r.diagnostic = await self._capture_diagnostic()
            return r

        # Wait for root tag (3s)
        try:
            await self.helper.wait_for_element(screen.root, timeout=self.navigate_timeout_ms)
        except Exception:  # noqa: BLE001 — wait timed out
            r.status = WalkStatus.FAIL
            r.reason = f"root tag did not appear within {self.navigate_timeout_ms}ms"
            r.missing_tags = [screen.root]
            r.diagnostic = await self._capture_diagnostic()
            # Best-effort: try to recover hub
            await self._back_to_hub()
            return r

        # Verify text probes
        for probe in screen.text_probes:
            elem = await self.helper.get_element(probe)
            if elem is None:
                r.missing_tags.append(probe)
            else:
                r.text_probe_values[probe] = elem.text or ""

        # Click each clickable target
        for target in screen.clickable_targets:
            if not await self.helper.is_element_visible(target):
                r.missing_tags.append(target)
                continue
            if await self._try_click(target):
                r.clicked_targets.append(target)
                # Brief settle to let the UI react / dismiss any popovers
                await asyncio.sleep(0.1)
            else:
                r.failed_targets.append(target)

        # Refresh (one click) if defined
        if screen.refresh is not None:
            if not await self.helper.is_element_visible(screen.refresh):
                r.missing_tags.append(screen.refresh)
            elif await self._try_click(screen.refresh):
                r.refresh_clicked = True
            else:
                r.failed_targets.append(screen.refresh)

        # Verdict
        if r.missing_tags or r.failed_targets:
            r.status = WalkStatus.FAIL
            r.reason = f"{len(r.missing_tags)} missing, {len(r.failed_targets)} not clickable"
            r.diagnostic = await self._capture_diagnostic()
        else:
            r.status = WalkStatus.PASS
            r.reason = "all expected tags present and responsive"

        # Back to hub for the next screen
        await self._back_to_hub()
        return r

    async def _step_each_screen(self) -> None:
        for key, screen in SCREENS.items():
            # peer_detail is reached by clicking a peer row, not from hub.
            # Walk it only if we can find at least one peer_row_* tag.
            if key == "peer_detail":
                result = await self._walk_peer_detail()
            else:
                result = await self._walk_screen(key, screen)
            self.report.per_screen.append(result)

    async def _walk_peer_detail(self) -> ScreenWalkResult:
        """Peer-detail is reached via Peers list. Skip if no peers exist."""
        screen = SCREENS["peer_detail"]
        r = ScreenWalkResult(
            screen_key="peer_detail",
            screen_name=screen.name,
            nav_tile=screen.nav_tile,
            root_tag=screen.root,
        )
        # Navigate to Peers first
        if not await self.helper.is_element_visible(NETWORK_HUB):
            if not await self._navigate_to_hub():
                r.status = WalkStatus.SKIP
                r.reason = "could not return to hub for peer-detail walk"
                return r
        if not await self._try_click(screen.nav_tile):
            r.status = WalkStatus.FAIL
            r.reason = f"nav tile not clickable: {screen.nav_tile}"
            r.failed_targets = [screen.nav_tile]
            return r
        # Wait for the Peers root
        peers_screen = SCREENS["peers"]
        try:
            await self.helper.wait_for_element(peers_screen.root, timeout=self.navigate_timeout_ms)
        except Exception:  # noqa: BLE001
            r.status = WalkStatus.SKIP
            r.reason = "Peers screen did not load — peer-detail unreachable"
            await self._back_to_hub()
            return r

        # Look for any peer_row_* tag in the tree
        elements = await self.helper.get_elements()
        peer_rows = [e for e in elements if e.test_tag.startswith("peer_row_")]
        if not peer_rows:
            r.status = WalkStatus.SKIP
            r.reason = "no peer rows on fresh agent — peer-detail walk skipped (tolerated)"
            await self._back_to_hub()
            return r

        # Click the first peer row to deep-nav
        if not await self._try_click(peer_rows[0].test_tag):
            r.status = WalkStatus.FAIL
            r.reason = f"peer row not clickable: {peer_rows[0].test_tag}"
            r.failed_targets = [peer_rows[0].test_tag]
            await self._back_to_hub()
            return r

        try:
            await self.helper.wait_for_element(screen.root, timeout=self.navigate_timeout_ms)
        except Exception:  # noqa: BLE001
            r.status = WalkStatus.FAIL
            r.reason = f"peer-detail root did not appear: {screen.root}"
            r.missing_tags = [screen.root]
            r.diagnostic = await self._capture_diagnostic()
            await self._back_to_hub()
            return r

        # From here, mirror the standard screen walk
        for probe in screen.text_probes:
            elem = await self.helper.get_element(probe)
            if elem is None:
                r.missing_tags.append(probe)
            else:
                r.text_probe_values[probe] = elem.text or ""

        for target in screen.clickable_targets:
            if not await self.helper.is_element_visible(target):
                r.missing_tags.append(target)
                continue
            if await self._try_click(target):
                r.clicked_targets.append(target)
                await asyncio.sleep(0.1)
            else:
                r.failed_targets.append(target)

        if screen.refresh is not None:
            if not await self.helper.is_element_visible(screen.refresh):
                r.missing_tags.append(screen.refresh)
            elif await self._try_click(screen.refresh):
                r.refresh_clicked = True
            else:
                r.failed_targets.append(screen.refresh)

        if r.missing_tags or r.failed_targets:
            r.status = WalkStatus.FAIL
            r.reason = f"{len(r.missing_tags)} missing, {len(r.failed_targets)} not clickable"
            r.diagnostic = await self._capture_diagnostic()
        else:
            r.status = WalkStatus.PASS
            r.reason = "all expected tags present and responsive"

        await self._back_to_hub()
        return r

    # ─── Step: mode-change flow ──────────────────────────────────
    async def _step_mode_flow(self) -> None:
        self._log("mode flow")
        result = ModeFlowResult()

        if not await self.helper.is_element_visible(NETWORK_HUB):
            if not await self._navigate_to_hub():
                result.status = WalkStatus.SKIP
                result.reason = "hub not reachable for mode-flow"
                self.report.mode_check = result
                return

        # Required tags for this flow
        required = [BTN_MODE_PROXY, BTN_MODE_CLIENT, DIALOG_MODE_CONFIRM, BTN_MODE_CONFIRM, BTN_MODE_CANCEL]
        missing = await self._missing([BTN_MODE_PROXY, BTN_MODE_CLIENT])
        if missing:
            result.status = WalkStatus.FAIL
            result.reason = "mode-flow tile missing on hub"
            result.missing_tags = missing
            result.diagnostic = await self._capture_diagnostic()
            self.report.mode_check = result
            return

        # 1. PROXY → click should activate immediately (no confirm)
        if not await self._try_click(BTN_MODE_PROXY):
            result.status = WalkStatus.FAIL
            result.reason = f"could not click {BTN_MODE_PROXY}"
            result.diagnostic = await self._capture_diagnostic()
            self.report.mode_check = result
            return
        result.proxy_selected = True
        await asyncio.sleep(0.25)

        # 2. CLIENT → confirm dialog appears, then CANCEL
        if not await self._try_click(BTN_MODE_CLIENT):
            result.status = WalkStatus.FAIL
            result.reason = f"could not click {BTN_MODE_CLIENT}"
            result.diagnostic = await self._capture_diagnostic()
            self.report.mode_check = result
            return
        try:
            await self.helper.wait_for_element(DIALOG_MODE_CONFIRM, timeout=self.navigate_timeout_ms)
        except Exception:  # noqa: BLE001
            result.status = WalkStatus.FAIL
            result.reason = f"confirm dialog did not appear: {DIALOG_MODE_CONFIRM}"
            result.missing_tags = [DIALOG_MODE_CONFIRM]
            result.diagnostic = await self._capture_diagnostic()
            self.report.mode_check = result
            return
        # Cancel
        if not await self._try_click(BTN_MODE_CANCEL):
            result.status = WalkStatus.FAIL
            result.reason = f"could not click {BTN_MODE_CANCEL}"
            result.missing_tags = [BTN_MODE_CANCEL]
            result.diagnostic = await self._capture_diagnostic()
            self.report.mode_check = result
            return
        result.cancel_observed = True
        await asyncio.sleep(0.25)

        # 3. CLIENT again, confirm
        if not await self._try_click(BTN_MODE_CLIENT):
            result.status = WalkStatus.FAIL
            result.reason = "could not re-open CLIENT mode confirm"
            result.diagnostic = await self._capture_diagnostic()
            self.report.mode_check = result
            return
        try:
            await self.helper.wait_for_element(BTN_MODE_CONFIRM, timeout=self.navigate_timeout_ms)
        except Exception:  # noqa: BLE001
            result.status = WalkStatus.FAIL
            result.reason = f"confirm button did not appear: {BTN_MODE_CONFIRM}"
            result.missing_tags = [BTN_MODE_CONFIRM]
            result.diagnostic = await self._capture_diagnostic()
            self.report.mode_check = result
            return
        if not await self._try_click(BTN_MODE_CONFIRM):
            result.status = WalkStatus.FAIL
            result.reason = f"could not click {BTN_MODE_CONFIRM}"
            result.diagnostic = await self._capture_diagnostic()
            self.report.mode_check = result
            return
        result.client_confirmed = True
        await asyncio.sleep(0.25)

        # 4. Revert to PROXY (confirm again — same flow)
        if not await self._try_click(BTN_MODE_PROXY):
            result.status = WalkStatus.FAIL
            result.reason = f"could not click {BTN_MODE_PROXY} for revert"
            result.diagnostic = await self._capture_diagnostic()
            self.report.mode_check = result
            return
        # Confirm dialog may or may not appear for proxy revert depending on impl;
        # be tolerant — if a confirm appears, click it.
        if await self.helper.is_element_visible(BTN_MODE_CONFIRM):
            await self._try_click(BTN_MODE_CONFIRM)
        result.reverted_to_proxy = True

        # Missing-tag audit
        all_required_missing = await self._missing(required)
        if all_required_missing:
            result.missing_tags = all_required_missing
            result.status = WalkStatus.FAIL
            result.reason = f"missing required mode-flow tags: {all_required_missing}"
        else:
            result.status = WalkStatus.PASS
            result.reason = "proxy→client(cancel)→client(confirm)→proxy completed"
        self.report.mode_check = result

    # ─── Step: add-peer flow ─────────────────────────────────────
    async def _step_add_peer_flow(self) -> None:
        self._log("add-peer flow")
        result = AddPeerFlowResult()

        # Get to Peers
        if not await self.helper.is_element_visible(NETWORK_HUB):
            if not await self._navigate_to_hub():
                result.status = WalkStatus.SKIP
                result.reason = "hub not reachable for add-peer flow"
                self.report.add_peer_check = result
                return
        peers = SCREENS["peers"]
        if not await self._try_click(peers.nav_tile):
            result.status = WalkStatus.FAIL
            result.reason = f"peers tile not clickable: {peers.nav_tile}"
            result.missing_tags = [peers.nav_tile]
            self.report.add_peer_check = result
            return
        try:
            await self.helper.wait_for_element(peers.root, timeout=self.navigate_timeout_ms)
        except Exception:  # noqa: BLE001
            result.status = WalkStatus.FAIL
            result.reason = f"Peers screen did not load: {peers.root}"
            result.missing_tags = [peers.root]
            result.diagnostic = await self._capture_diagnostic()
            self.report.add_peer_check = result
            return

        # Open dialog
        if not await self.helper.is_element_visible(BTN_ADD_PEER):
            result.status = WalkStatus.FAIL
            result.reason = f"add-peer button missing: {BTN_ADD_PEER}"
            result.missing_tags = [BTN_ADD_PEER]
            result.diagnostic = await self._capture_diagnostic()
            self.report.add_peer_check = result
            await self._back_to_hub()
            return
        if not await self._try_click(BTN_ADD_PEER):
            result.status = WalkStatus.FAIL
            result.reason = f"add-peer button not clickable: {BTN_ADD_PEER}"
            result.diagnostic = await self._capture_diagnostic()
            self.report.add_peer_check = result
            await self._back_to_hub()
            return
        try:
            await self.helper.wait_for_element(DIALOG_ADD_PEER, timeout=self.navigate_timeout_ms)
            result.dialog_opened = True
        except Exception:  # noqa: BLE001
            result.status = WalkStatus.FAIL
            result.reason = f"add-peer dialog did not appear: {DIALOG_ADD_PEER}"
            result.missing_tags = [DIALOG_ADD_PEER]
            result.diagnostic = await self._capture_diagnostic()
            self.report.add_peer_check = result
            await self._back_to_hub()
            return

        # Input an invalid code, submit, expect error
        try:
            await self.helper.input_text(INPUT_ADD_PEER_CODE, INVALID_NODE_CODE)
            result.invalid_input_accepted = True
        except Exception as e:  # noqa: BLE001
            result.missing_tags.append(INPUT_ADD_PEER_CODE)
            result.reason = f"add-peer code input failed: {e}"
            # continue — we still want to try submit + cancel

        submitted = await self._try_click(BTN_ADD_PEER_SUBMIT)
        if not submitted:
            result.missing_tags.append(BTN_ADD_PEER_SUBMIT)

        # Look for error rendering: either explicit tag, or any text node mentioning "error" / "invalid"
        await asyncio.sleep(0.4)  # let the error render
        err_elem = None
        try:
            err_elem = await self.helper.get_element(TEXT_ADD_PEER_ERROR)
        except Exception:  # noqa: BLE001
            pass
        if err_elem is not None:
            result.error_rendered = True
        else:
            # Fallback heuristic: any visible element whose text mentions invalid / error
            try:
                elems = await self.helper.get_elements()
                for elem in elems:
                    txt = (elem.text or "").lower()
                    if "invalid" in txt or "error" in txt or "failed" in txt:
                        result.error_rendered = True
                        break
            except Exception:  # noqa: BLE001
                pass
            if not result.error_rendered:
                result.missing_tags.append(TEXT_ADD_PEER_ERROR)

        # Cancel
        if not await self.helper.is_element_visible(BTN_ADD_PEER_CANCEL):
            result.missing_tags.append(BTN_ADD_PEER_CANCEL)
        else:
            if await self._try_click(BTN_ADD_PEER_CANCEL):
                await asyncio.sleep(0.3)
                # Dialog should no longer be present
                if not await self.helper.is_element_visible(DIALOG_ADD_PEER):
                    result.dialog_closed = True

        # Verdict
        if result.missing_tags:
            result.status = WalkStatus.FAIL
            result.reason = f"missing tags in add-peer flow: {result.missing_tags}"
            if result.diagnostic is None:
                result.diagnostic = await self._capture_diagnostic()
        elif not (result.dialog_opened and result.error_rendered and result.dialog_closed):
            result.status = WalkStatus.FAIL
            result.reason = (
                f"flow incomplete (opened={result.dialog_opened}, "
                f"error_rendered={result.error_rendered}, closed={result.dialog_closed})"
            )
            result.diagnostic = await self._capture_diagnostic()
        else:
            result.status = WalkStatus.PASS
            result.reason = "invalid-code submit → error rendered → cancel closes dialog"

        self.report.add_peer_check = result
        await self._back_to_hub()

    # ─── Cascade SKIP helpers ─────────────────────────────────────
    def _cascade_skip(self, reason: str) -> None:
        """Mark all downstream steps as SKIP with a shared reason."""
        self.report.fatal_reason = reason
        self.report.hub_check.status = WalkStatus.SKIP
        self.report.hub_check.reason = reason
        for key, screen in SCREENS.items():
            self.report.per_screen.append(
                ScreenWalkResult(
                    screen_key=key,
                    screen_name=screen.name,
                    nav_tile=screen.nav_tile,
                    root_tag=screen.root,
                    status=WalkStatus.SKIP,
                    reason=reason,
                )
            )
        self.report.mode_check.status = WalkStatus.SKIP
        self.report.mode_check.reason = reason
        self.report.add_peer_check.status = WalkStatus.SKIP
        self.report.add_peer_check.reason = reason

    # ─── Public entry point ───────────────────────────────────────
    async def run(self) -> FederationWalkReport:
        """Execute the full walk and return the populated report."""
        self.report.started_at = datetime.now(timezone.utc)

        try:
            if not await self._step_login():
                self._cascade_skip(self.report.fatal_reason or "login failed")
                return self.report

            await self._step_hub()
            if self.report.hub_check.status != WalkStatus.PASS:
                # Hub failed — still attempt per-screen walks (they verify
                # their own roots) but record the cascade reason.
                # Note: per-screen results are not SKIP-cascaded here because
                # individual screen verification is independent of hub probes.
                pass

            await self._step_each_screen()
            await self._step_mode_flow()
            await self._step_add_peer_flow()
        finally:
            self.report.finished_at = datetime.now(timezone.utc)

        return self.report
