"""The accord_halt QA module never writes a latch outside its throwaway home (CIRISAgent#1231)."""

import json
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from tools.qa_runner.config import QAModule
from tools.qa_runner.modules import accord_halt_tests as qa
from tools.qa_runner.modules._module_metadata import get_metadata


def test_latch_path_must_be_inside_the_throwaway_home(tmp_path):
    home = tmp_path / "ciris-qa-accord-halt-x"
    home.mkdir()
    assert qa.throwaway_latch_path(str(home / "HUMANITY_ACCORD_HALT"), str(home)) == (home / "HUMANITY_ACCORD_HALT")


@pytest.mark.parametrize(
    "reported, home",
    [
        ("/home/someone/ciris/HUMANITY_ACCORD_HALT", "/tmp/ciris-qa-accord-halt-x"),  # a different home
        ("/tmp/ciris-qa-accord-halt-x/sub/HUMANITY_ACCORD_HALT", "/tmp/ciris-qa-accord-halt-x"),  # not directly in it
        ("/tmp/ciris-qa-accord-halt-x/other_file", "/tmp/ciris-qa-accord-halt-x"),  # not the latch
        ("/tmp/ciris-qa-accord-halt-x/HUMANITY_ACCORD_HALT", None),  # the runner made no throwaway home
        ("", "/tmp/ciris-qa-accord-halt-x"),
    ],
)
def test_anything_else_is_refused(reported, home):
    assert qa.throwaway_latch_path(reported, home) is None


def test_latch_record_is_a_node_halt_record():
    record = qa.latch_record(datetime(2026, 10, 14, tzinfo=timezone.utc), fuse_secs=60)
    assert set(record) >= {"invocation_kind", "invocation_id", "valid_signers", "quorum_threshold", "latched_at"}
    assert record["invocation_kind"] == "constitutional"
    assert record["received_at"] == record["latched_at"] and record["fuse_secs"] == 60
    json.dumps(record)


@pytest.mark.asyncio
@pytest.mark.parametrize("version", [None, "0.5.225", "0.5.224"])
async def test_servers_below_0_5_226_skip_without_writing(monkeypatch, version):
    monkeypatch.setattr(qa, "installed_server_version", lambda: version)
    module = qa.AccordHaltTests(Mock(_transport=Mock(base_url="http://localhost:1", api_key="t")), Mock())
    results = await module.run()
    assert [r["status"] for r in results] == ["⏭️ SKIP"]
    assert "0.5.226" in results[0]["error"]


def test_module_is_registered_but_not_in_the_all_sequences():
    from tools.qa_runner.config import ALL_1_MODULE_SEQUENCE, ALL_2_MODULE_SEQUENCE, ALL_MODULE_SEQUENCE

    assert QAModule("accord_halt") is QAModule.ACCORD_HALT
    assert get_metadata(QAModule.ACCORD_HALT) is not None
    for sequence in (ALL_MODULE_SEQUENCE, ALL_1_MODULE_SEQUENCE, ALL_2_MODULE_SEQUENCE):
        assert QAModule.ACCORD_HALT not in sequence
