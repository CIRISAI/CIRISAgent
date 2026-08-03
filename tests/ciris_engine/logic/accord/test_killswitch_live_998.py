"""Kill-switch regression lock (#998).

The runtime control service used to keep its OWN authority list — a
``WAPublicKeyMap`` at ``_wa_key_map`` whose only writer, ``_configure_kill_switch``,
nothing ever called. ``_verify_wa_signature`` gated on that empty map, so every
WA-signed emergency shutdown was rejected regardless of signature validity,
while ``GET /v1/emergency/kill-switch/status`` reported ``enabled: true`` off a
hardcoded default.

That decoy is gone. Authorities now come from the accord verifier — ONE trust
root, two entry surfaces:

  * the stego-encoded ``AccordPayload`` extracted from ordinary message text
    (the real kill switch, and the one that was always healthy), and
  * the ``WASignedCommand`` the emergency API accepts.

These tests lock both surfaces to that single authority source. They are
deliberately end-to-end: sign -> steganographically encode -> extract from text
-> verify. A test that stops short of extraction would not have caught the
original defect, because the original defect was in the wiring, not the crypto.
"""

import ast
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Tuple, cast

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ciris_engine.logic.accord.extractor import extract_accord
from ciris_engine.logic.accord.verifier import AccordVerifier
from ciris_engine.schemas.accord import AccordCommandType
from ciris_engine.schemas.services.shutdown import EmergencyCommandType, WASignedCommand
from tools.security.accord_stego import create_stego_accord_message

# The steward's real ROOT key. Present on the dev host, absent in CI — the
# real-key tests SKIP rather than fail when it is missing, because they are the
# only evidence that the SHIPPED key set (seed/root_pub.json plus the hardcoded
# fallbacks) actually verifies the steward's signature.
STEWARD_KEY_PATH = Path.home() / ".ciris" / "wa_keys" / "root_wa.key"
STEWARD_META_PATH = Path.home() / ".ciris" / "wa_keys" / "root_wa_metadata.json"
DEFAULT_STEWARD_WA_ID = "wa-2025-06-14-ROOT00"

CONTROL_SERVICE_PATH = (
    Path(__file__).resolve().parents[4]
    / "ciris_engine"
    / "logic"
    / "services"
    / "runtime"
    / "control_service"
    / "service.py"
)


def _raw_public_key(private_key: Ed25519PrivateKey) -> bytes:
    """Raw 32-byte Ed25519 public key for a private key."""
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _raw_private_key(private_key: Ed25519PrivateKey) -> bytes:
    """Raw 32-byte Ed25519 private key bytes."""
    return private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _load_steward_key() -> Optional[Tuple[Ed25519PrivateKey, str]]:
    """Load the steward's real ROOT key, or None when it is not on this host."""
    if not STEWARD_KEY_PATH.exists():
        return None

    raw = STEWARD_KEY_PATH.read_bytes()
    if len(raw) != 32:
        return None

    wa_id = DEFAULT_STEWARD_WA_ID
    if STEWARD_META_PATH.exists():
        try:
            wa_id = str(json.loads(STEWARD_META_PATH.read_text()).get("wa_id") or DEFAULT_STEWARD_WA_ID)
        except (ValueError, OSError):  # pragma: no cover - malformed metadata on host
            wa_id = DEFAULT_STEWARD_WA_ID

    return Ed25519PrivateKey.from_private_bytes(raw), wa_id


def _sign_wa_command(private_key: Ed25519PrivateKey, wa_id: str) -> WASignedCommand:
    """Build a WASignedCommand signed in the exact canonical form the service verifies.

    The canonical string is rebuilt from the CONSTRUCTED model, with the same
    f-string expressions the service uses, so pydantic coercion and enum
    rendering cannot silently diverge between signer and verifier.
    """
    command = WASignedCommand(
        command_id="killswitch-regression-998",
        command_type=EmergencyCommandType.SHUTDOWN_NOW,
        wa_id=wa_id,
        wa_public_key=_raw_public_key(private_key).hex(),
        issued_at=datetime.now(timezone.utc),
        reason="#998 kill-switch regression test",
        signature="00",
    )
    signed_data = "|".join(
        [
            f"command_id:{command.command_id}",
            f"command_type:{command.command_type}",
            f"wa_id:{command.wa_id}",
            f"issued_at:{command.issued_at.isoformat()}",
            f"reason:{command.reason}",
        ]
    )
    if command.target_agent_id:  # pragma: no cover - not set by this test
        signed_data += f"|target_agent_id:{command.target_agent_id}"

    signature = private_key.sign(signed_data.encode("utf-8"))
    return command.model_copy(update={"signature": signature.hex()})


class TestStegoDrillGeneratedKey:
    """The stego path, end to end, with a key generated here so CI can run it."""

    def test_drill_extracts_and_verifies(self) -> None:
        """A DRILL signed by a trusted authority survives stego encode -> extract -> verify."""
        private_key = Ed25519PrivateKey.generate()
        wa_id = "wa-test-drill-998"

        text = create_stego_accord_message(
            command=AccordCommandType.DRILL,
            wa_id=wa_id,
            private_key_bytes=_raw_private_key(private_key),
        )

        # The carrier must look like ordinary prose — extraction IS perception.
        assert text and "DRILL" not in text

        extraction = extract_accord(text, channel="test-killswitch-998")
        assert extraction.found, "stego DRILL was not extracted from the carrier text"
        assert extraction.message is not None
        assert extraction.message.payload.command == AccordCommandType.DRILL

        # auto_load_seed=False: this verifier trusts only the generated key, so
        # a pass cannot be borrowed from the shipped authority set.
        verifier = AccordVerifier(auto_load_seed=False)
        assert verifier.add_authority(wa_id, _raw_public_key(private_key), "ROOT")

        result = verifier.verify(extraction.message)
        assert result.valid, result.rejection_reason
        assert result.command == AccordCommandType.DRILL
        assert result.wa_id == wa_id
        assert result.wa_role == "ROOT"

    def test_untrusted_signer_is_rejected(self) -> None:
        """Negative control: a DRILL from an unknown key must not verify."""
        signer = Ed25519PrivateKey.generate()
        text = create_stego_accord_message(
            command=AccordCommandType.DRILL,
            wa_id="wa-test-intruder-998",
            private_key_bytes=_raw_private_key(signer),
        )

        extraction = extract_accord(text, channel="test-killswitch-998")
        assert extraction.found
        assert extraction.message is not None

        verifier = AccordVerifier(auto_load_seed=False)
        result = verifier.verify(extraction.message)
        assert not result.valid
        assert result.rejection_reason


class TestStegoDrillStewardKey:
    """The same path against the REAL steward key — the only proof the shipped key set works."""

    def test_real_drill_verifies_against_shipped_authorities(self) -> None:
        loaded = _load_steward_key()
        if loaded is None:
            pytest.skip(f"steward ROOT key not present at {STEWARD_KEY_PATH} (expected on the dev host only)")
        private_key, wa_id = loaded

        text = create_stego_accord_message(
            command=AccordCommandType.DRILL,
            wa_id=wa_id,
            private_key_bytes=_raw_private_key(private_key),
        )

        extraction = extract_accord(text, channel="test-killswitch-998")
        assert extraction.found
        assert extraction.message is not None

        # Default authority set: seed/root_pub.json plus hardcoded fallbacks.
        verifier = AccordVerifier()
        result = verifier.verify(extraction.message)

        assert (
            result.valid
        ), f"the shipped authority set does not verify the steward key for {wa_id}: {result.rejection_reason}"
        assert result.command == AccordCommandType.DRILL
        assert result.wa_id == wa_id

        # The shipped set holds the steward's actual public key, not a stale one.
        assert verifier.public_key_for(wa_id) == _raw_public_key(private_key)

    def test_real_wa_signed_command_verifies_on_the_emergency_surface(self) -> None:
        """The OTHER entry surface resolves its key from the same trust root.

        This is the assertion the original defect would have failed: the old
        ``_wa_key_map`` was empty, so this returned False for a valid signature.
        """
        loaded = _load_steward_key()
        if loaded is None:
            pytest.skip(f"steward ROOT key not present at {STEWARD_KEY_PATH} (expected on the dev host only)")
        private_key, wa_id = loaded

        from ciris_engine.logic.services.runtime.control_service.service import RuntimeControlService

        command = _sign_wa_command(private_key, wa_id)

        # _verify_wa_signature touches no instance state; call it unbound so the
        # test does not depend on the service's full dependency graph.
        verified = RuntimeControlService._verify_wa_signature(cast(Any, object()), command)
        assert verified is True

        # Negative control: an untrusted signer is refused by the same path.
        intruder = Ed25519PrivateKey.generate()
        intruder_command = _sign_wa_command(intruder, "wa-test-intruder-998")
        assert RuntimeControlService._verify_wa_signature(cast(Any, object()), intruder_command) is False


class TestPublicKeyResolution:
    """AccordVerifier.public_key_for is the single authority lookup both surfaces use."""

    def test_resolves_known_authority(self) -> None:
        verifier = AccordVerifier(auto_load_seed=False)
        private_key = Ed25519PrivateKey.generate()
        assert verifier.add_authority("wa-test-known-998", _raw_public_key(private_key), "ROOT")

        resolved = verifier.public_key_for("wa-test-known-998")
        assert resolved == _raw_public_key(private_key)
        assert resolved is not None and len(resolved) == 32

    def test_returns_none_for_unknown_authority(self) -> None:
        verifier = AccordVerifier(auto_load_seed=False)
        assert verifier.public_key_for("wa-test-nobody-998") is None

    def test_shipped_authority_set_is_not_empty(self) -> None:
        """An empty authority set is a kill switch that cannot fire."""
        verifier = AccordVerifier()
        assert verifier.authority_count >= 1
        assert verifier.public_key_for(DEFAULT_STEWARD_WA_ID) is not None
        assert verifier.public_key_for("wa-test-nobody-998") is None


class TestControlServiceHasNoPrivateAuthorityList:
    """The decoy must not come back: no second authority list in the control service."""

    @staticmethod
    def _module_ast() -> ast.Module:
        assert CONTROL_SERVICE_PATH.exists(), f"control service not found at {CONTROL_SERVICE_PATH}"
        return ast.parse(CONTROL_SERVICE_PATH.read_text(encoding="utf-8"))

    def test_no_wa_key_map_attribute_in_code(self) -> None:
        """AST, not grep: the historical comment naming `_wa_key_map` is allowed to stay."""
        tree = self._module_ast()
        offenders = [
            node.lineno for node in ast.walk(tree) if isinstance(node, ast.Attribute) and node.attr == "_wa_key_map"
        ]
        assert not offenders, f"_wa_key_map is referenced in code at line(s) {offenders}"

    def test_no_wa_public_key_map_symbol_in_code(self) -> None:
        tree = self._module_ast()
        offenders: list[int] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "WAPublicKeyMap":
                offenders.append(node.lineno)
            elif isinstance(node, ast.Attribute) and node.attr == "WAPublicKeyMap":
                offenders.append(node.lineno)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if any(alias.name == "WAPublicKeyMap" or alias.asname == "WAPublicKeyMap" for alias in node.names):
                    offenders.append(node.lineno)
        assert not offenders, f"WAPublicKeyMap is referenced in code at line(s) {offenders}"

    def test_no_configure_kill_switch_method(self) -> None:
        tree = self._module_ast()
        names = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        assert "_configure_kill_switch" not in names

    def test_verify_wa_signature_resolves_through_accord_verifier(self) -> None:
        """Positive control — the method must still resolve keys, from the accord verifier."""
        tree = self._module_ast()
        target = next(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_verify_wa_signature"
            ),
            None,
        )
        assert target is not None, "_verify_wa_signature is missing from the control service"

        body = ast.dump(target)
        assert "AccordVerifier" in body, "_verify_wa_signature no longer resolves keys via AccordVerifier"
        assert "public_key_for" in body, "_verify_wa_signature no longer calls public_key_for"
