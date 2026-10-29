"""The owner's log download: the agent's and the node's logs, redacted, as one zip.

Eric could not get logs off his own phone: the Logs screen had no download and
the client's debug bundle held only its Kotlin buffer. These tests hold the
route that hands over the files, and the redaction that keeps secrets out.
"""

from __future__ import annotations

import io
import os
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.dependencies.auth import get_auth_context
from ciris_engine.logic.adapters.api.routes import telemetry_logs_download as dl
from ciris_engine.logic.adapters.api.routes.telemetry import router
from ciris_engine.schemas.api.auth import AuthContext, UserRole


def _zip(data: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(data))


@pytest.fixture
def logs(tmp_path: Path) -> Path:
    d = tmp_path / "logs"
    d.mkdir()
    (d / "ciris_agent_20261026_104000.log").write_text("2026-10-26 10:40:00.000 - a - INFO - agent up\n")
    (d / "incidents_latest.log").write_text("2026-10-26 10:41:00.000 - a - WARNING - an incident\n")
    (d / "ciris-server.log.2026-10-26").write_text("2026-10-26T10:40:01Z  INFO ciris_server: node up\n")
    (d / "not_a_log.txt").write_text("ignore me\n")
    return d


# ── redaction ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "line, secret",
    [
        ("Authorization: Bearer sess:wa-root-abc.def123", "sess:wa-root-abc.def123"),
        ("tokenPreview=sess:wa-qGyw0123456789", "wa-qGyw0123456789"),
        ("key sk-or-v1-0123456789abcdef0123456789", "0123456789abcdef0123456789"),
        ("groq gsk_ABCDEFGHIJKLMNOPQRSTUV", "ABCDEFGHIJKLMNOPQRSTUV"),
        ('{"api_key": "abcd1234efgh"}', "abcd1234efgh"),
        ("password=hunter2&next=1", "hunter2"),
        ("client_secret: s3cr3tvalue", "s3cr3tvalue"),
    ],
)
def test_secrets_are_redacted(line: str, secret: str) -> None:
    out = dl.redact(line)
    assert secret not in out and "[REDACTED]" in out


def test_ordinary_lines_pass_through_unchanged() -> None:
    line = "2026-10-26 10:40:00.000 - consent - INFO - Default TEMPORARY consent on first interaction user=wa-root-x\n"
    assert dl.redact(line) == line


# ── the bundle ──────────────────────────────────────────────────────────────


def test_agent_and_node_logs_both_ship_and_non_logs_do_not(logs: Path) -> None:
    b = dl.build_log_bundle(logs, versions={"agent version": "2.17.0-stable"})
    names = set(_zip(b.data).namelist())
    assert {"ciris_agent_20261026_104000.log", "incidents_latest.log", "ciris-server.log.2026-10-26"} <= names
    assert "not_a_log.txt" not in names
    manifest = _zip(b.data).read("MANIFEST.txt").decode()
    assert "agent version: 2.17.0-stable" in manifest and "ciris-server.log.2026-10-26" in manifest


def test_secrets_never_leave_the_process(logs: Path) -> None:
    (logs / "latest.log").write_text("x Authorization: Bearer sess:wa-root-SECRET123\n")
    b = dl.build_log_bundle(logs)
    assert b"SECRET123" not in b"".join(_zip(b.data).read(n) for n in _zip(b.data).namelist())


def test_a_long_log_is_tailed_from_a_line_boundary(logs: Path) -> None:
    big = logs / "ciris_agent_big.log"
    big.write_text("".join(f"line {i:06d}\n" for i in range(20000)))
    b = dl.build_log_bundle(logs, tail_kib=1)
    body = _zip(b.data).read("ciris_agent_big.log").decode()
    assert body.startswith("line ") and body.endswith("line 019999\n")
    assert len(body) <= 1024
    assert "last" in _zip(b.data).read("MANIFEST.txt").decode()


def test_latest_log_linked_to_the_session_log_ships_once(logs: Path) -> None:
    os.symlink(logs / "ciris_agent_20261026_104000.log", logs / "latest.log")
    names = _zip(dl.build_log_bundle(logs).data).namelist()
    assert sum(n in ("latest.log", "ciris_agent_20261026_104000.log") for n in names) == 1


def test_old_files_are_left_out(logs: Path) -> None:
    old = logs / "ciris_agent_20260901_000000.log"
    old.write_text("old\n")
    stale = time.time() - dl.MAX_AGE_SECONDS - 60
    os.utime(old, (stale, stale))
    assert old.name not in _zip(dl.build_log_bundle(logs).data).namelist()


def test_the_bundle_cap_is_named_in_the_manifest(logs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dl, "MAX_TOTAL_BYTES", dl.MIN_FILE_ROOM + 100)
    b = dl.build_log_bundle(logs)
    # Once less than MIN_FILE_ROOM is left, the rest are named, not shipped as scraps.
    assert 0 < len(b.files) < 3
    assert b.skipped and "cap" in _zip(b.data).read("MANIFEST.txt").decode()


def test_a_missing_logs_dir_is_an_empty_bundle_not_an_error(tmp_path: Path) -> None:
    b = dl.build_log_bundle(tmp_path / "nope")
    assert "(none" in _zip(b.data).read("MANIFEST.txt").decode()


# ── the route ───────────────────────────────────────────────────────────────


def _client(role: UserRole, logs: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("ciris_engine.logic.utils.path_resolution.get_logs_dir", lambda: logs)
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        user_id="wa-root-test", role=role, permissions=set(), authenticated_at=datetime.now(timezone.utc)
    )
    return TestClient(app)


def test_the_owner_downloads_a_zip(logs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    r = _client(UserRole.ADMIN, logs, monkeypatch).get("/v1/telemetry/logs/download")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert r.headers["content-disposition"].startswith('attachment; filename="ciris-logs-')
    assert "ciris-server.log.2026-10-26" in _zip(r.content).namelist()


def test_an_observer_is_refused(logs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The negative: raw files are the owner's; /logs stays the observer's view."""
    r = _client(UserRole.OBSERVER, logs, monkeypatch).get("/v1/telemetry/logs/download")
    assert r.status_code == 403
