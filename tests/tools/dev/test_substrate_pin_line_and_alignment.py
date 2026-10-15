"""The substrate pin line is rewritten intact, and its absence fails the alignment check (#1262).

The 0.5.226 re-pin shipped a requirements.txt whose ciris-server line had lost
its `ciris-server==0.5.226  #` prefix. pip refused the whole file
("Expected matching RIGHT_PARENTHESIS"), every five-platform leg failed to
build, and check_version_alignment.py still reported green, because it
returned early when it found no pin.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from tools.update_substrate_libs import pin_requirement_line

ROOT = Path(__file__).resolve().parents[3]

OLD = (
    "pkg-a>=1.0\n"
    "ciris-server==0.5.223  # 0.5.223 (2026-10-07, tag v0.5.223): replaces 0.5.222 (heap fix). Previously: 0.5.222 x\n"
    "ciris-client==0.5.228  # floor\n"
)


def _alignment():
    spec = importlib.util.spec_from_file_location(
        "check_version_alignment", ROOT / "tools/dev/check_version_alignment.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_a_digit_leading_version_keeps_the_prefix_and_the_history():
    out = pin_requirement_line(OLD, "ciris-server", "0.5.226", "(2026-10-14): one reader (#763); tee first (#767).")
    line = next(l for l in out.splitlines() if "ciris-server" in l)
    assert line.startswith("ciris-server==0.5.226  # 0.5.226 (2026-10-14): one reader (#763); tee first (#767). ")
    assert line.endswith(
        "Previously: 0.5.223 (2026-10-07, tag v0.5.223): replaces 0.5.222 (heap fix). Previously: 0.5.222 x"
    )
    # Everything else is untouched.
    assert out.splitlines()[0] == "pkg-a>=1.0" and out.splitlines()[2] == "ciris-client==0.5.228  # floor"
    assert _alignment()._unparseable_requirement_lines(out) == []


@pytest.mark.parametrize(
    "text, version",
    [
        ("pkg-a>=1.0\n", "0.5.226"),  # no pin to rewrite
        (OLD + "ciris-server==0.5.1\n", "0.5.226"),  # two pins
        (OLD, "v0.5.226"),  # not X.Y.Z
        (OLD, "10.5.226 # sneaky"),
    ],
)
def test_refuses_what_it_cannot_rewrite_exactly(text, version):
    with pytest.raises(ValueError):
        pin_requirement_line(text, "ciris-server", version, "note")


def _check(monkeypatch, tmp_path, requirements: str):
    module = _alignment()
    (tmp_path / "requirements.txt").write_text(requirements)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    return module._check_substrate_client_version()


def test_alignment_fails_when_the_server_pin_is_missing(monkeypatch, tmp_path):
    errors = _check(monkeypatch, tmp_path, "pkg-a>=1.0\nciris-client==0.5.228\n")
    assert any("no parseable `ciris-server==X.Y.Z` pin" in e for e in errors)


def test_alignment_fails_on_the_mangled_line_that_shipped(monkeypatch, tmp_path):
    """The exact shape of the #1262 breakage: the note survived, the `name==version  #` did not."""
    mangled = "pkg-a>=1.0\n0.5.223 (2026-10-07, tag v0.5.223): replaces 0.5.222\nciris-client==0.5.228\n"
    errors = _check(monkeypatch, tmp_path, mangled)
    assert any("line 2 is not a valid requirement" in e for e in errors)
    assert any("no parseable `ciris-server==X.Y.Z` pin" in e for e in errors)


def test_alignment_passes_a_well_formed_file(monkeypatch, tmp_path):
    assert _check(monkeypatch, tmp_path, OLD) == []


def test_the_repo_requirements_file_is_well_formed():
    module = _alignment()
    text = (ROOT / "requirements.txt").read_text()
    assert module._unparseable_requirement_lines(text) == []
    assert "\nciris-server==" in "\n" + text
