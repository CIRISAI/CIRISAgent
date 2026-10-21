"""#977 — signed compose dumps: sign_object/verify_object adoption (0.5.154).

Two layers, deliberately:

- Unit layer (substrate doubled at the module seam): the CLI glue's posture —
  sign failures abort the dump run rather than emitting silently-unsigned
  output; verification refuses on missing/False/unperformable/relabelled; the
  gate surfaces ``[sig]`` failures and fails the run.
- Real-substrate layer (subprocess — engine + edge + federation delivery are
  process singletons, and 0.5.154's detached-object verbs refuse without the
  live delivery runtime): the label-tamper property against the REAL
  ``verify_object``. The label rides INSIDE the signed manifest, so editing it
  in the signature JSON must flip verification to False — that is what stops a
  dump signed under one arm being relabelled into another.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import List, Optional

import ciris_server
import pytest

from ciris_engine.logic.utils.compose_dump import sign_dump, verify_dump_signature
from ciris_engine.logic.utils.research_overrides import compute_residue_digest

ARM = "h3ere-hidden"


@pytest.fixture
def dump_file(tmp_path: Path) -> Path:
    dump = tmp_path / "arm.jsonl"
    dump.write_text('{"arm": "h3ere-hidden"}\n', encoding="utf-8")
    return dump


# ---------------------------------------------------------------------------
# Unit layer — the glue's posture, substrate doubled at the module seam
# ---------------------------------------------------------------------------


def test_sign_dump_seals_the_arm_as_the_label(dump_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[tuple] = []

    def fake_sign_object(path: str, label: str = "") -> str:
        calls.append((path, label))
        return json.dumps({"manifest": {"label": label}, "scrub_signature_classical": "sig"})

    monkeypatch.setattr(ciris_server, "sign_object", fake_sign_object)
    sig_path = sign_dump(str(dump_file), ARM)

    assert calls == [(str(dump_file), ARM)], "label must be the arm — that is what the envelope seals"
    assert sig_path == str(dump_file) + ".sig.json"
    assert json.loads(Path(sig_path).read_text(encoding="utf-8"))["manifest"]["label"] == ARM


def test_sign_dump_fails_loudly_when_the_substrate_refuses(
    dump_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dump run asked to sign must never quietly emit unsigned output."""

    def refusing_sign_object(path: str, label: str = "") -> str:
        raise RuntimeError("sign_object: federation delivery not started")

    monkeypatch.setattr(ciris_server, "sign_object", refusing_sign_object)
    with pytest.raises(SystemExit, match="sign FAILED"):
        sign_dump(str(dump_file), ARM)
    assert not Path(str(dump_file) + ".sig.json").exists()


def _write_sig(dump_file: Path, label: str) -> Path:
    sig = dump_file.with_name(dump_file.name + ".sig.json")
    sig.write_text(json.dumps({"manifest": {"label": label}, "scrub_signature_classical": "sig"}), encoding="utf-8")
    return sig


def test_verify_refuses_a_missing_signature(dump_file: Path) -> None:
    problem = verify_dump_signature(str(dump_file), ARM)
    assert problem is not None and "missing detached signature" in problem


def test_verify_refuses_a_false_verify(dump_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_sig(dump_file, ARM)
    monkeypatch.setattr(ciris_server, "verify_object", lambda path, sig_json: False)
    problem = verify_dump_signature(str(dump_file), ARM)
    assert problem is not None and "does not verify" in problem


def test_verify_refuses_an_unperformable_check(dump_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """'Could not look' must not read as 'verified'."""
    _write_sig(dump_file, ARM)

    def raising_verify(path: str, sig_json: str) -> bool:
        raise RuntimeError("verify_object: federation delivery not started")

    monkeypatch.setattr(ciris_server, "verify_object", raising_verify)
    problem = verify_dump_signature(str(dump_file), ARM)
    assert problem is not None and "could not be PERFORMED" in problem


def test_verify_refuses_a_relabelled_arm_even_with_a_valid_signature(
    dump_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A signature that verifies but seals a DIFFERENT arm is a dump being
    presented as something it was not signed as."""
    _write_sig(dump_file, "h3ere-visible")
    monkeypatch.setattr(ciris_server, "verify_object", lambda path, sig_json: True)
    problem = verify_dump_signature(str(dump_file), ARM)
    assert problem is not None and "sealed label" in problem


def test_verify_passes_only_on_true_with_the_matching_label(
    dump_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_sig(dump_file, ARM)
    monkeypatch.setattr(ciris_server, "verify_object", lambda path, sig_json: True)
    assert verify_dump_signature(str(dump_file), ARM) is None


def test_gate_verify_sig_fails_the_run_and_names_the_dump(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """run_gate(verify_sig=True) turns an unverifiable signature into a named
    [sig] failure and a non-zero exit; without the flag the same dumps pass."""
    from ciris_engine.logic.utils.compose_dump import residue_fragments, run_gate
    from ciris_engine.schemas.dma.compose import ComposeDumpMeta

    meta = ComposeDumpMeta(
        arm=ARM,
        manifest=None,
        locales=[],
        steps=[],
        residue_digest=compute_residue_digest(),
        fragment_count=len(residue_fragments()),
    )
    dump_a = tmp_path / "a.jsonl"
    dump_b = tmp_path / "b.jsonl"
    for dump in (dump_a, dump_b):
        dump.write_text(meta.model_dump_json() + "\n", encoding="utf-8")
    regime = tmp_path / "regime.yaml"
    regime.write_text(
        'regime_id: sig-selfcheck\nblocks: {}\npins:\n  residue_digest: "live"\n',
        encoding="utf-8",
    )

    assert run_gate(str(dump_a), str(dump_b), str(regime)) == 0

    _write_sig(dump_a, ARM)  # dump-a signed, dump-b not
    monkeypatch.setattr(ciris_server, "verify_object", lambda path, sig_json: True)
    assert run_gate(str(dump_a), str(dump_b), str(regime), verify_sig=True) == 1
    out = capsys.readouterr().out
    assert "[sig] dump-b" in out and "missing detached signature" in out
    assert "[sig] dump-a" not in out


# ---------------------------------------------------------------------------
# Real-substrate layer — the label-tamper property against the REAL verify
# ---------------------------------------------------------------------------

_SIGN_PROBE = textwrap.dedent(
    """
    import json, os, sys, tempfile
    import ciris_server as cs
    from ciris_engine.logic.utils.compose_dump import sign_dump, verify_dump_signature

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "sign.db")
    for suffix in (".seed", ".pqc"):
        with open(db + suffix, "wb") as fh:
            fh.write(os.urandom(32))
    engine = cs.Engine(
        f"sqlite:///{db}",
        "sign-key",
        local_key_id="sign-key",
        local_key_path=db + ".seed",
        local_pqc_key_id="sign-key-pqc",
        local_pqc_key_path=db + ".pqc",
    )
    # verify_object checks against the signer's REGISTERED pubkeys — the same
    # edge-init self-registration the rest of the fabric depends on.
    engine.register_self_federation_key("agent", "sign-key", None, None, None)
    # Keep the handle alive — dropping it un-registers the process-global edge.
    edge = cs.init_edge_runtime(
        engine,
        os.path.join(tmp, "edge_identity.rid"),
        listen_addr="127.0.0.1:0",
        enable_transport=True,
    )
    cs.start_federation_delivery()

    dump = os.path.join(tmp, "arm.jsonl")
    with open(dump, "w", encoding="utf-8") as fh:
        fh.write('{"arm": "h3ere-hidden"}\\n')

    sig_path = sign_dump(dump, "h3ere-hidden")
    result = {}
    result["clean"] = verify_dump_signature(dump, "h3ere-hidden")

    original_sig = open(sig_path, encoding="utf-8").read()
    doc = json.loads(original_sig)
    assert doc["manifest"]["label"] == "h3ere-hidden"

    # THE tamper: relabel the arm inside the signature document.
    doc["manifest"]["label"] = "h3ere-visible"
    with open(sig_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc))
    result["raw_verify_after_label_tamper"] = cs.verify_object(dump, json.dumps(doc))
    result["tampered_label"] = verify_dump_signature(dump, "h3ere-visible")

    # Restore the valid signature, then present the dump as a different arm.
    with open(sig_path, "w", encoding="utf-8") as fh:
        fh.write(original_sig)
    result["relabelled_claim"] = verify_dump_signature(dump, "h3ere-visible")

    # And tamper the dump bytes under the valid signature.
    with open(dump, "a", encoding="utf-8") as fh:
        fh.write("x")
    result["tampered_bytes"] = verify_dump_signature(dump, "h3ere-hidden")

    print("RESULT:" + json.dumps(result))
    """
)


@pytest.mark.timeout(240)
def test_label_is_sealed_inside_the_real_envelope() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", _SIGN_PROBE],
        capture_output=True,
        text=True,
        timeout=220,
        cwd=str(Path(__file__).resolve().parents[4]),
    )
    assert completed.returncode == 0, (
        f"sign probe subprocess failed\nstdout: {completed.stdout}\nstderr: {completed.stderr}"
    )
    payload = next(
        (line[len("RESULT:") :] for line in completed.stdout.splitlines() if line.startswith("RESULT:")),
        None,
    )
    assert payload is not None, f"no RESULT line in probe output: {completed.stdout}"
    result = json.loads(payload)

    assert result["clean"] is None, f"a freshly signed dump must verify: {result['clean']}"
    # The property #977 exists for: editing the label inside the signature JSON
    # flips the REAL verify_object to False — the label is sealed, not metadata.
    assert result["raw_verify_after_label_tamper"] is False
    assert result["tampered_label"] is not None and "does not verify" in result["tampered_label"]
    # A valid signature presented under a different arm claim is refused too.
    assert result["relabelled_claim"] is not None and "sealed label" in result["relabelled_claim"]
    # And the signature covers the bytes.
    assert result["tampered_bytes"] is not None and "does not verify" in result["tampered_bytes"]
