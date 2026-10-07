"""The backend memory sampler reads the right process and the right number.

Report-only, so the risk is a silent wrong answer: sampling the launcher
instead of the backend, or reading PSS as RSS. These pin both.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("sbm", ROOT / "tools/dev/sample_backend_memory.py")
assert _spec and _spec.loader
sbm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sbm)

NEW_ANDROID = """Applications Memory Usage (in Kilobytes):
** MEMINFO in pid 4321 [ai.ciris.mobile.debug] **
                   Pss  Private  Private  SwapPss      Rss     Heap
                 Total    Dirty    Clean    Dirty    Total     Size
                ------   ------   ------   ------   ------   ------
        TOTAL   612345   500000    40000        0   734003        0
 App Summary
           TOTAL PSS:   612345            TOTAL RSS:   734003       TOTAL SWAP PSS:        0
"""

OLD_ANDROID = """** MEMINFO in pid 4321 [ai.ciris.mobile.debug] **
                 Pss  Private  Private  Swapped     Heap
               Total    Dirty    Clean    Dirty     Size
              ------   ------   ------   ------   ------
       TOTAL   409600   300000    20000        0        0
"""


def test_new_android_reports_rss_and_pss_separately():
    rss, pss = sbm.parse_dumpsys_meminfo(NEW_ANDROID)
    assert rss == round(734003 / 1024, 1)
    assert pss == round(612345 / 1024, 1)


def test_old_android_falls_back_to_the_table_total_as_pss_only():
    rss, pss = sbm.parse_dumpsys_meminfo(OLD_ANDROID)
    assert rss is None
    assert pss == 400.0


def test_no_meminfo_is_unavailable_not_zero():
    assert sbm.parse_dumpsys_meminfo("No process found for: ai.ciris.mobile.debug\n") == (None, None)


@pytest.mark.parametrize(
    "cmdline,target,expected",
    [
        (["/usr/bin/python3", "/opt/ciris/main.py", "--adapter", "api", "--port", "8080"], "desktop", True),
        (["C:\\py\\python.exe", "C:\\ciris\\main.py", "--adapter", "api"], "desktop", True),
        # The launcher is not the backend: it holds no node.
        (["/usr/bin/python3", "/usr/local/bin/ciris-agent"], "desktop", False),
        (["/usr/bin/python3", "main.py", "--adapter", "discord"], "desktop", False),
        (["/usr/bin/python3", "not_main.py", "--adapter", "api"], "desktop", False),
        (
            [
                "/Users/r/Library/Developer/CoreSimulator/Devices/X/data/Containers/Bundle/Application/Y/iosApp.app/iosApp"
            ],
            "ios",
            True,
        ),
        (["/usr/bin/python3", "main.py", "--adapter", "api"], "ios", False),
    ],
)
def test_backend_process_selection(cmdline, target, expected):
    assert sbm.is_backend_cmdline(cmdline, target) is expected


def test_samples_a_real_backend_shaped_process_and_never_fails(tmp_path):
    """End to end against a live process whose cmdline looks like the backend."""
    fake = tmp_path / "main.py"
    fake.write_text(
        "import time\nblob = bytearray(64 * 1024 * 1024)\nfor i in range(0, len(blob), 4096): blob[i] = 1\ntime.sleep(60)\n"
    )
    proc = subprocess.Popen([sys.executable, str(fake), "--adapter", "api"])
    try:
        time.sleep(1.5)
        out = tmp_path / "memory.json"
        assert sbm.main(["--platform", "linux", "--target", "desktop", "--idle-secs", "0", "--out", str(out)]) == 0
        report = json.loads(out.read_text())
        for phase in ("after_activity", "resting"):
            sample = report[phase]
            # Another real backend on this host may also match; the 64 MB touched
            # here is a floor either way.
            assert sample["rss_mb"] is not None and sample["rss_mb"] >= 60, sample
    finally:
        proc.kill()
        proc.wait()


def test_no_backend_writes_null_with_a_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(sbm, "is_backend_cmdline", lambda cmdline, target: False)
    out = tmp_path / "memory.json"
    assert sbm.main(["--platform", "linux", "--target", "desktop", "--idle-secs", "0", "--out", str(out)]) == 0
    sample = json.loads(out.read_text())["resting"]
    assert sample["rss_mb"] is None
    assert "no desktop backend process found" in sample["reason"]
