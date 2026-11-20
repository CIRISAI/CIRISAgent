"""The ``context_manifest`` member of a trace's LLM_CALL event (FSD/TRACE_WIRE_FORMAT.md §5.10).

Each LLM call carries the per-call context manifest the prompt assembler built
(FSD/PROMPT_CONTEXT_PROVENANCE.md §8): which typed segments the call
contained, their trust after taint, their locale, and any guard violations. It
is content-free by construction (ids, digests, closed vocabulary, character
spans), and it rides inside the component ``data``, so the trace signature
covers it (§8): an aggregator cannot swap or edit it without breaking the
signature.

Always called ``context_manifest``. ``trace_manifest:v1`` is a different
object (the constitution's carrier for traces too large to send inline).

Levels:

* ``generic``: omitted. Generic carries no prompt hashes, and the manifest is
  mostly digests.
* ``detailed``: every verified sender's ``authn.subject_id`` is replaced by a
  per-agent keyed pseudonym (HMAC-SHA256 under a secret only this agent holds,
  first 16 hex). It is stable within one agent, cannot be reversed by
  dictionary (user ids are low-entropy: chat snowflakes, ``wa-user-42``), and
  does not link one person across agents. ``subject_id_form`` says which form
  shipped. ``authz.authorizer_id`` is a Wise Authority id and stays as it is.
* ``full_traces``: the subject id as verified (``subject_id_form: "raw"``).

If the pseudonym key cannot be read or created, the subject id is withheld
(``subject_id_form: "withheld"``), never sent raw at ``detailed``.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import threading
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

#: The member name on the LLM_CALL event's data.
CONTEXT_MANIFEST_FIELD = "context_manifest"

SUBJECT_ID_FORM_RAW = "raw"
SUBJECT_ID_FORM_HMAC = "hmac_sha256_16"
SUBJECT_ID_FORM_WITHHELD = "withheld"

#: The per-agent pseudonym key, in the agent's data dir (shared by every
#: occurrence of one agent, like its federation identity).
SUBJECT_KEY_FILENAME = "trace_subject_hmac.key"
_KEY_BYTES = 32


class SubjectPseudonymizer:
    """Keyed pseudonyms for verified sender ids, under one per-agent secret.

    The key is created once, atomically (``O_EXCL``, mode 0600), so concurrent
    occurrences of one agent converge on the same file and the same pseudonyms.
    """

    def __init__(self, key_path: Optional[Path] = None) -> None:
        self._key_path = key_path
        self._key: Optional[bytes] = None
        self._failed = False
        self._lock = threading.Lock()

    def _resolve_path(self) -> Path:
        if self._key_path is not None:
            return self._key_path
        from ciris_engine.logic.utils.path_resolution import get_data_dir

        return get_data_dir() / SUBJECT_KEY_FILENAME

    def _load_or_create(self, path: Path) -> bytes:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            key = path.read_bytes()
            if len(key) != _KEY_BYTES:
                raise ValueError(f"pseudonym key at {path.name} is {len(key)} bytes, expected {_KEY_BYTES}")
            return key
        key = secrets.token_bytes(_KEY_BYTES)
        with os.fdopen(fd, "wb") as handle:
            handle.write(key)
            handle.flush()
            os.fsync(handle.fileno())
        return key

    def key(self) -> Optional[bytes]:
        """The key, or None when it cannot be read or created (callers then withhold)."""
        with self._lock:
            if self._key is None and not self._failed:
                try:
                    self._key = self._load_or_create(self._resolve_path())
                except Exception as exc:  # noqa: BLE001 - the trace must not break; the id is withheld instead
                    self._failed = True
                    logger.warning("[CONTEXT_MANIFEST] pseudonym key unavailable (%s); subject ids withheld", type(exc).__name__)
            return self._key

    def pseudonym(self, subject_id: str) -> Optional[str]:
        key = self.key()
        if key is None:
            return None
        return hmac.new(key, subject_id.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def _as_dict(manifest: Any) -> Optional[Dict[str, Any]]:
    if manifest is None:
        return None
    if hasattr(manifest, "model_dump"):
        dumped = manifest.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else None
    if isinstance(manifest, dict):
        # The reasoning stream dumps events in python mode, so enum members may still be in it: a JSON round trip
        # leaves only plain JSON values (str-valued enums become their values) and is a copy as well.
        import json

        dumped = json.loads(json.dumps(manifest, default=str))
        return dumped if isinstance(dumped, dict) else None
    return None


def trace_context_manifest(
    manifest: Any, *, detailed: bool, full: bool, pseudonymizer: SubjectPseudonymizer
) -> Optional[Dict[str, Any]]:
    """The ``context_manifest`` member for an LLM_CALL at this trace level, or None to omit it.

    ``manifest`` is the event's ``PromptManifest`` (or its dump). None at
    ``generic`` or when the call ran outside the assembler.
    """
    if not detailed:
        return None
    data = _as_dict(manifest)
    if data is None:
        return None
    if full:
        data["subject_id_form"] = SUBJECT_ID_FORM_RAW
        return data
    form = SUBJECT_ID_FORM_HMAC
    for segment in data.get("segments") or []:
        authn = segment.get("authn") if isinstance(segment, dict) else None
        if not isinstance(authn, dict) or not isinstance(authn.get("subject_id"), str):
            continue
        pseudonym = pseudonymizer.pseudonym(authn["subject_id"])
        if pseudonym is None:
            authn.pop("subject_id", None)
            form = SUBJECT_ID_FORM_WITHHELD
        else:
            authn["subject_id"] = pseudonym
    data["subject_id_form"] = form
    return data


__all__ = [
    "CONTEXT_MANIFEST_FIELD",
    "SUBJECT_ID_FORM_HMAC",
    "SUBJECT_ID_FORM_RAW",
    "SUBJECT_ID_FORM_WITHHELD",
    "SUBJECT_KEY_FILENAME",
    "SubjectPseudonymizer",
    "trace_context_manifest",
]
