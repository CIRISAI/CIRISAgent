"""The Android shell never takes the claim PIN from a log.

DIRECT USER RULING: "the claim PIN is a file on disk, never the log." The node
writes its one-time PIN to ``<CIRIS_HOME>/claim_pin`` and the shared client reads
that file at claim time (``PythonRuntime.readLocalClaimPin``, CIRISClient#49).

``MainActivity.kt`` used to tail ``latest.log``, ``ciris-server.log`` and
``ciris_agent_*`` and feed every line through
``PythonRuntime.scanFileLineForOwnership``, which pulls a ``XXXX-XXXX`` PIN out
of the ownership banner. CIRISAgent#1277 and CIRISServer#770 take the value out
of every log, so that path would have left Android first-run claim with nothing.

These are source-level guards: they cannot prove the running app is right, but
they fail the moment a log-scraping PIN path is reintroduced. Each guard is also
run against an injected defect, so a green result is not a vacuous one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MAIN_ACTIVITY = ROOT / "apps/android/src/main/kotlin/ai/ciris/mobile/MainActivity.kt"

# The PIN shape the client's banner parser extracts (Crockford base32 XXXX-XXXX).
PIN_CHARCLASS = "[0-9A-HJKMNP-TV-Z]"

# Client entry points that parse a PIN out of a line of text.
LINE_PIN_PARSERS = ("scanFileLineForOwnership", "parseOwnershipBanner", "isClaimPinCaptured")

# The node/agent log files the old tail scraped.
LOG_FILE_NAMES = ("latest.log", "ciris-server.log", "ciris_agent_")


def _strip_comments(src: str) -> str:
    """Drop Kotlin block and line comments, so KDoc that names the old path is ignored."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", src)


def _log_pin_violations(src: str) -> list[str]:
    code = _strip_comments(src)
    found = []
    for name in LINE_PIN_PARSERS:
        if name in code:
            found.append(f"calls {name}")
    if PIN_CHARCLASS in code:
        found.append("applies the claim-PIN regex")
    for name in LOG_FILE_NAMES:
        if f'"{name}' in code:
            found.append(f"opens log file {name}")
    return found


def _forwarded_lines_unguarded(src: str) -> bool:
    """True if forwardLogLine can be reached by an ownership-banner line."""
    code = _strip_comments(src)
    idx = code.find("PythonRuntime.forwardLogLine(")
    if idx == -1:
        return False
    # The nearest enclosing `if (` before the call must exclude banner lines.
    guard = code.rfind("if (", 0, idx)
    return guard == -1 or "!isOwnershipBannerLine(line)" not in code[guard:idx]


@pytest.fixture(scope="module")
def source() -> str:
    if not MAIN_ACTIVITY.exists():
        pytest.skip("Android shell not present in this checkout")
    return MAIN_ACTIVITY.read_text(encoding="utf-8")


def test_no_pin_is_parsed_from_a_log(source: str) -> None:
    assert _log_pin_violations(source) == []


def test_ownership_banner_lines_are_not_forwarded_to_the_client_parser(source: str) -> None:
    assert not _forwarded_lines_unguarded(source)
    markers = re.search(r"OWNERSHIP_BANNER_MARKERS\s*=\s*listOf\(([^)]*)\)", source)
    assert markers, "OWNERSHIP_BANNER_MARKERS list not found"
    # Must cover every marker the client's parseOwnershipBanner treats as context.
    for word in ("CLAIM PIN", "OWNERSHIP", "UNCLAIMED"):
        assert f'"{word}"' in markers.group(1)


def test_claim_pin_file_is_resolved_under_ciris_home(source: str) -> None:
    code = _strip_comments(source)
    assert 'CLAIM_PIN_FILE = "claim_pin"' in code
    # Same CIRIS_HOME resolution the client's readLocalClaimPin uses.
    assert "EnvFileUpdater.getCirisHome()" in code
    assert "File(home, CLAIM_PIN_FILE)" in code


def test_shell_checks_presence_and_never_reads_the_pin_value(source: str) -> None:
    code = _strip_comments(source)
    assert "File(home, CLAIM_PIN_FILE).isFile" in code
    assert not re.search(r"CLAIM_PIN_FILE\)\s*\.\s*(readText|readLines|bufferedReader|inputStream)", code)


# --- the guards above must FAIL on the defect they exist to catch -------------

OLD_TAIL = """
    private suspend fun tailNodeLogsForOwnership() = withContext(Dispatchers.IO) {
        val candidates = logsDir.listFiles { f -> f.name == "latest.log" }
        f.bufferedReader().useLines { seq ->
            seq.forEach { line -> PythonRuntime.scanFileLineForOwnership(line) }
        }
    }
"""

INLINE_REGEX = 'val pin = Regex("[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}").find(line)'

UNGUARDED_FORWARD = """
                if (line.isNotBlank()) {
                    PythonRuntime.forwardLogLine(line)
                }
"""


def test_guard_catches_the_old_log_tail() -> None:
    found = _log_pin_violations(OLD_TAIL)
    assert "calls scanFileLineForOwnership" in found
    assert "opens log file latest.log" in found


def test_guard_catches_an_inline_pin_regex() -> None:
    assert _log_pin_violations(INLINE_REGEX) == ["applies the claim-PIN regex"]


def test_guard_ignores_comments_that_name_the_old_path() -> None:
    assert _log_pin_violations('/** used to tail "latest.log" via scanFileLineForOwnership */') == []


def test_guard_catches_an_unguarded_forward() -> None:
    assert _forwarded_lines_unguarded(UNGUARDED_FORWARD)
