"""The battery's delivery verdict comes from the canonical's receipt.

Run 43364853207 printed "Delivery: UNKNOWN" while the canonical held 40 of the
run's trace rows. The probe's window outlasts a battery run, and its
producer-side counters do not measure trace carriage. The receiver's signed
receipt does, so it decides whenever a canonical answered.
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from rich.console import Console

from tools.qa_runner.modules import safety_battery as sb


def _battery(tmp_path: Path, client: Any = None) -> sb.SafetyBatteryTests:
    return sb.SafetyBatteryTests(
        client=client,
        console=Console(file=io.StringIO()),
        lang="en",
        domain="mental_health",
        results_dir=tmp_path / "out",
    )


def _summary(tmp_path: Path, monkeypatch, probe_lines: List[str], receipt: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    import json

    root = tmp_path / "repo"
    (root / "logs" / "sqlite").mkdir(parents=True)
    (root / "logs" / "sqlite" / "latest.log").write_text("\n".join(probe_lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(sb, "REPO_ROOT", root)
    b = _battery(tmp_path)
    b._results_dir.mkdir(parents=True)
    b._delivery_receipt = receipt
    results = root / "results.jsonl"
    results.write_text("", encoding="utf-8")
    b._write_summary({"battery_id": "x", "battery_version": "1", "cell": {}}, results)
    return json.loads((b._results_dir / "summary.json").read_text(encoding="utf-8"))["delivery"]


ROOTED = "x [DELIVERY-PROBE] canonical c ROOTED after ~10s"


def test_the_receipt_confirms_what_the_probe_could_not(tmp_path, monkeypatch) -> None:
    d = _summary(tmp_path, monkeypatch, [ROOTED], {"held": True, "shipped_any": True})
    assert d["shipped"] is True
    assert d["shipped_from"] == "canonical delivery receipt"


def test_newest_still_in_flight_but_earlier_traces_held_is_delivery(tmp_path, monkeypatch) -> None:
    d = _summary(tmp_path, monkeypatch, [ROOTED], {"held": False, "shipped_any": True})
    assert d["shipped"] is True


def test_a_canonical_that_holds_nothing_is_not_shipped(tmp_path, monkeypatch) -> None:
    d = _summary(tmp_path, monkeypatch, [ROOTED], {"held": False, "shipped_any": False})
    assert d["shipped"] is False


def test_no_answer_and_no_probe_verdict_stays_unknown(tmp_path, monkeypatch) -> None:
    d = _summary(tmp_path, monkeypatch, [ROOTED], {"held": None, "shipped_any": None})
    assert d["shipped"] is None


def test_no_answer_keeps_the_probe_verdict(tmp_path, monkeypatch) -> None:
    lines = [ROOTED, "x [DELIVERY-PROBE] canonical c SHIP CONFIRMED — envelopes_sent_total=3 at ~90s post-root"]
    d = _summary(tmp_path, monkeypatch, lines, None)
    assert d["shipped"] is True
    assert d["shipped_from"] == "agent [DELIVERY-PROBE] verdict"


class _Resp:
    def __init__(self, status: int, body: Dict[str, Any]) -> None:
        self.status_code = status
        self._body = body
        self.text = str(body)

    def json(self) -> Dict[str, Any]:
        return self._body


def _read(tmp_path: Path, monkeypatch, resp: _Resp) -> Dict[str, Any]:
    import httpx

    class _Client:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a) -> None:
            return None

        async def get(self, url: str, headers: Dict[str, str]) -> _Resp:
            assert url.endswith("/v1/system/runtime/delivery-receipt")
            return resp

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    transport = type("T", (), {"base_url": "http://x", "api_key": "tok"})()
    client = type("C", (), {"_transport": transport})()
    return asyncio.run(_battery(tmp_path, client)._read_delivery_receipt())


def test_receipt_reader_takes_shipped_any_from_the_canonical_rows(tmp_path, monkeypatch) -> None:
    body = {
        "data": {
            "held_by_every_answering_canonical": False,
            "canonicals": [{"key_id": "c", "shipped_any": True}],
            "raw_json": "{}",
        }
    }
    out = _read(tmp_path, monkeypatch, _Resp(200, body))
    assert out["held"] is False and out["shipped_any"] is True
    assert "raw_json" not in out["data"]


def test_receipt_reader_records_a_refusal_as_unknown(tmp_path, monkeypatch) -> None:
    out = _read(tmp_path, monkeypatch, _Resp(503, {"detail": "unavailable"}))
    assert out["held"] is None and out["shipped_any"] is None and out["status_code"] == 503
