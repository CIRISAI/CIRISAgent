"""The client↔agent token-refresh handshake, defined once.

The CIRIS-hosted proxy is authenticated with the user's OAuth ID token, and
those expire in about an hour. Replacing one is a four-step conversation
across a process boundary, carried by two marker files in CIRIS_HOME:

    agent  401 from the proxy        -> writes `.token_refresh_needed`
    client polls that file           -> silently re-signs in
    client rewrites `.env`           -> with a token name the agent reads
    client writes `.config_reload`   -> agent reloads .env, swaps its key

Every value in that conversation — the two filenames, the directory they
live in, and the environment variables the token may arrive under — used to
be written out again at each site: two separate copies of
`_signal_token_refresh_needed`, three writers of `.config_reload`, three
Kotlin clients each with their own constants. That is how the desktop client
came to write `CIRIS_BILLING_OAUTH_TOKEN`, a name no Python code had ever
read: both halves were locally correct and the handshake was silently dead,
so a desktop user's agent 401'd every call from about an hour after setup
and never recovered.

One definition, so the two halves cannot drift again. The Kotlin side mirrors
these names in `EnvFileUpdater.kt`; that mirror is what the cross-language
test in `test_desktop_token_refresh_handshake.py` pins.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

#: The agent asks for a fresh token by creating this file.
TOKEN_REFRESH_REQUEST_FILE = ".token_refresh_needed"

#: The client answers by creating this one, after rewriting `.env`.
CONFIG_RELOAD_SIGNAL_FILE = ".config_reload"

#: Where the refreshed token is written.
ENV_FILE = ".env"

#: Every name a proxy token may arrive under. Android writes the Google name,
#: iOS the Apple one; desktop wrote CIRIS_BILLING_OAUTH_TOKEN before it was
#: corrected, and that name stays readable so a client and an agent on
#: different versions still complete the handshake.
PROXY_TOKEN_VARS: Tuple[str, ...] = (
    "CIRIS_BILLING_GOOGLE_ID_TOKEN",
    "CIRIS_BILLING_APPLE_ID_TOKEN",
    "CIRIS_BILLING_OAUTH_TOKEN",
)

#: One prefix for every step, so `grep TOKEN_HANDSHAKE` reads as one story
#: across both processes instead of four unrelated-looking lines.
LOG_PREFIX = "[TOKEN_HANDSHAKE]"


def handshake_home() -> Optional[Path]:
    """The directory both halves meet in.

    CIRIS_HOME when set, else the shared resolver — never a third opinion.
    """
    explicit = os.getenv("CIRIS_HOME")
    if explicit:
        return Path(explicit)
    try:
        from ciris_engine.logic.utils.path_resolution import get_ciris_home

        # Coerce: callers (and test doubles) hand back either a Path or a str,
        # and every use here is `home / filename`, which a str cannot do.
        return Path(get_ciris_home())
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("%s cannot resolve CIRIS_HOME: %s", LOG_PREFIX, exc)
        return None


def token_refresh_request_path() -> Optional[Path]:
    home = handshake_home()
    return home / TOKEN_REFRESH_REQUEST_FILE if home else None


def config_reload_signal_path() -> Optional[Path]:
    home = handshake_home()
    return home / CONFIG_RELOAD_SIGNAL_FILE if home else None


def env_path() -> Optional[Path]:
    home = handshake_home()
    return home / ENV_FILE if home else None


def request_token_refresh(reason: str) -> bool:
    """Ask the client for a fresh token. Returns whether the ask was written.

    Says WHERE it wrote and WHY, because the failure mode this exists for is a
    client that is not watching: the ask succeeds, nothing answers, and the
    only way to tell from the log is to see the path the agent chose and
    compare it with the one the client polls.
    """
    path = token_refresh_request_path()
    if path is None:
        logger.error("%s cannot request a refresh: no CIRIS_HOME (reason=%s)", LOG_PREFIX, reason)
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(time.time()))
        logger.info("%s asked the client for a fresh token: %s (reason=%s)", LOG_PREFIX, path, reason)
        return True
    except Exception as exc:
        logger.error("%s failed to write the refresh request at %s: %s", LOG_PREFIX, path, exc)
        return False


def jwt_expiry_epoch(token: str) -> Optional[float]:
    """The `exp` claim of a JWT, or None if this is not a readable JWT.

    UNVERIFIED ON PURPOSE. This is not an authorization decision — the provider
    still verifies the signature and rejects anything stale. It only orders
    several copies of our OWN token that different clients wrote under
    different names, and the only honest ordering between them is which lasts
    longer. Anything unparseable sorts last rather than raising.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        exp = claims.get("exp")
        return float(exp) if exp is not None else None
    except Exception:
        return None


def read_proxy_token(
    current: str = "", sources: Sequence[str] = PROXY_TOKEN_VARS
) -> Tuple[str, str]:
    """The freshest proxy token in the environment, and the name it came under.

    Returns ``("", "")`` when none is present.

    Not first-non-empty: a real `.env` carries more than one of these — the
    name written at setup, plus whatever the client last refreshed — and name
    order returns the setup-time token, which is precisely the expired one. So
    rank by expiry, and never re-select the value already in hand when a
    different copy exists, because "keep the credential that is currently
    401ing" is not a resolution of that tie.
    """
    present = [(var, os.environ.get(var, "")) for var in sources]
    present = [(var, tok) for var, tok in present if tok]
    if not present:
        logger.warning("%s no proxy token in the environment (looked at %s)", LOG_PREFIX, ", ".join(sources))
        return "", ""

    ranked = sorted(present, key=lambda vt: (jwt_expiry_epoch(vt[1]) or 0.0), reverse=True)
    if current and ranked[0][1] == current:
        alternative = next((vt for vt in ranked if vt[1] != current), None)
        if alternative is not None:
            logger.info(
                "%s %s still holds the value already in use; taking the differing copy from %s",
                LOG_PREFIX,
                ranked[0][0],
                alternative[0],
            )
            ranked = [alternative] + [vt for vt in ranked if vt is not alternative]

    var, token = ranked[0]
    if len(ranked) > 1:
        logger.info(
            "%s %d tokens present (%s) — chose %s by expiry",
            LOG_PREFIX,
            len(ranked),
            ", ".join(v for v, _ in ranked),
            var,
        )
    return token, var
