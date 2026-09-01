"""Detect and repair installs bricked by the pre-2.9.47 identity split.

WHAT WENT WRONG IN THE FIELD (2026-09-01, agent 2.9.44 / server 0.5.196).

Two defects, both created silently during a successful first run, both fatal
afterwards:

  * THE NODE WAS BOOTED ON THE AGENT'S KEY. `node_fold` passed the federation
    (actor) alias where CC 3.4.7.3 Clause A requires a node key. The substrate
    minted its own node key and could not move the owner-binding onto it. Setup
    then wrote a consent row naming that node key, and every boot afterwards died
    re-authoring it — the row names the node, the engine signs as the actor, and
    a consent grant is self-attested (CEG §5.6.8.15):

        node fold failed to start (node-fails ⇒ agent-fails)
        [FAIL] CIRIS Agent Initialization Failed (8.5s)

  * SETUP MINTED A SECOND CLAIM on a provider identity the fabric already owned,
    leaving two live holders. The substrate then correctly refused every sign-in
    (`auth.oauth.store_unavailable`), and an OAuth user has no password to fall
    back to.

Both are fixed at the root in 2.9.47. This module exists for the installs
already carrying the damage: the state is written to disk, so upgrading the code
does not clear it. A user who hit this cannot start the app to be told anything.

WHY WIPING IS THE RIGHT REPAIR HERE, AND ONLY HERE. The damaged state is the
identity material and the CEG rows keyed to it — precisely the things that
cannot be re-authored, which is what "bricked" means. There is no partial repair
that leaves the identity intact, because the identity IS the fault. The home is
ARCHIVED rather than deleted, so nothing is destroyed and the evidence survives
for diagnosis.

The gate is deliberately narrow. Repair runs only when ALL of:

  1. a known-fatal signature is actually observed — not predicted, not inferred
  2. the install predates 2.9.47 (no marker, or a marker <= 2.9.46)
  3. the operator has not opted out (CIRIS_NO_AUTO_REPAIR)

A healthy install never meets (1). An install created by a fixed build never
meets (2) — so this cannot loop, and cannot fire twice on the same home.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Optional, Tuple, Union

logger = logging.getLogger(__name__)

#: Written into CIRIS_HOME once a build with the fix boots successfully. Its
#: ABSENCE is meaningful: every build that could brick an install predates it.
INSTALL_MARKER = "install.json"

#: Last release that could produce the damage. An install stamped at or below
#: this — or not stamped at all — is eligible.
LAST_BRICKING_VERSION = (2, 9, 46)

#: Substrings of the two fatal outcomes. Matched against the exception text the
#: boot actually raised, so repair follows evidence rather than a guess.
FATAL_SIGNATURES = (
    "re-author consent",
    "consent grant is self-attested",
    "node fold failed to start",
)


def _parse_version(raw: str) -> Optional[Tuple[int, ...]]:
    """`2.9.44-stable` -> (2, 9, 44). None when it is not a version at all."""
    core = raw.strip().split("-")[0].split("+")[0]
    parts = core.split(".")
    if len(parts) < 3:
        return None
    try:
        return tuple(int(p) for p in parts[:3])
    except ValueError:
        return None


def record_install_version(home: Path, version: str) -> None:
    """Stamp the home as created (or repaired) by this build.

    Called after a boot gets far enough to prove the identity is sound. Stamping
    earlier would mark a home that is about to brick as already fixed.
    """
    try:
        home.mkdir(parents=True, exist_ok=True)
        (home / INSTALL_MARKER).write_text(
            json.dumps({"version": version, "stamped_at": time.time()}, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        # Never fatal: the marker is an optimisation for the repair gate, and a
        # home we cannot write to has larger problems that will surface on their
        # own terms rather than here.
        logger.warning("could not stamp install marker in %s: %s", home, exc)


def install_predates_fix(home: Path) -> bool:
    """True when this home was created by a build that could brick it.

    An ABSENT marker counts as eligible, and that is the common case: no build
    before 2.9.47 wrote one, and those are exactly the builds at issue.
    """
    marker = home / INSTALL_MARKER
    if not marker.exists():
        return True
    try:
        stamped = json.loads(marker.read_text(encoding="utf-8")).get("version", "")
    except (OSError, json.JSONDecodeError, AttributeError):
        return True
    parsed = _parse_version(str(stamped))
    if parsed is None:
        return True
    return parsed <= LAST_BRICKING_VERSION


def is_fatal_identity_failure(error: Union[BaseException, str]) -> bool:
    """Does this failure match the damage we know how to repair?

    Narrow on purpose. A boot can fail for a hundred reasons and almost none of
    them are repaired by wiping the home; treating an unrecognised failure as
    this one would destroy a working install to fix something else.
    """
    text = str(error)
    return any(sig in text for sig in FATAL_SIGNATURES)


def repair(home: Path, reason: str, version: str) -> Optional[Path]:
    """Archive the damaged home so the next boot starts clean. Returns the archive.

    ARCHIVE, NOT DELETE. The identity material is unusable but it is also the
    only record of what happened, and a user who has just been told "your install
    was reset" deserves for that to be reversible by someone who knows how.
    """
    if os.environ.get("CIRIS_NO_AUTO_REPAIR"):
        logger.error(
            "BRICKED INSTALL DETECTED but CIRIS_NO_AUTO_REPAIR is set — not repairing.\n"
            "  reason: %s\n"
            "  This install cannot start until %s is moved aside.",
            reason,
            home,
        )
        return None

    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    archive = home.parent / f"{home.name}.bricked-{stamp}"
    logger.error(
        "BRICKED INSTALL DETECTED — repairing by starting fresh.\n"
        "  reason:  %s\n"
        "  This install carries identity state that cannot be repaired in place:\n"
        "  the node was registered under the agent's key, so the consent rows it\n"
        "  wrote name a key this engine cannot sign as. Fixed at the root in\n"
        "  2.9.47; existing homes have to be re-created.\n"
        "  Your old home is being MOVED, not deleted:\n"
        "    %s  ->  %s\n"
        "  You will be asked to complete setup again on the next start.",
        reason,
        home,
        archive,
    )
    try:
        shutil.move(str(home), str(archive))
    except OSError as exc:
        logger.error("repair FAILED — could not move %s aside: %s", home, exc)
        return None

    try:
        home.mkdir(parents=True, exist_ok=True)
        record_install_version(home, version)
    except OSError as exc:
        logger.error("repair moved the old home but could not create a new one: %s", exc)
        return archive
    logger.error("repair complete — %s is fresh; the archive is at %s", home, archive)
    return archive


def repair_if_bricked(home: Path, error: BaseException, version: str) -> Optional[Path]:
    """The whole gate: evidence, then eligibility, then act.

    Returns the archive path when a repair happened, else None — so the caller
    can decide whether to tell the user to restart or to re-raise.
    """
    if not is_fatal_identity_failure(error):
        return None
    if not install_predates_fix(home):
        logger.error(
            "This failure matches the pre-2.9.47 identity split, but %s was created "
            "by a build that has the fix — so this is a DIFFERENT fault and wiping "
            "would destroy a sound install without curing it. Not repairing.",
            home,
        )
        return None
    return repair(home, str(error)[:400], version)
