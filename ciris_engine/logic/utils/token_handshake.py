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
from typing import List, Optional, Sequence, Set, Tuple

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


#: How to break a tie when NO candidate carries a readable expiry. Order is
#: meaning, not taste: a token handed back by a caller's callback was fetched
#: on purpose just now; CIRIS_BILLING_OAUTH_TOKEN is only ever written by a
#: desktop client that has just refreshed (setup writes the Google name, and
#: the corrected client deletes this one), so its presence implies it is the
#: newer of the two.
_OPAQUE_TIE_ORDER = ("callback", "CIRIS_BILLING_OAUTH_TOKEN", "CIRIS_BILLING_GOOGLE_ID_TOKEN", "CIRIS_BILLING_APPLE_ID_TOKEN")


def rank_candidates(candidates: Sequence[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Order (name, token) pairs best-first. One definition of "best".

    EXPIRY STATUS IS A TIER, NOT A NUMBER. Ranking on the raw `exp` alone put
    an EXPIRED JWT above every opaque token, because an expired token still
    carries a large positive epoch while a token whose format has no `exp` at
    all scores zero. So a credential we can prove is dead outranked one that
    might be alive — including the opaque forms a refresh callback legitimately
    returns, which meant the callback could hand back a good token and be
    ignored in favour of the expired value we were already being refused for.

    The three tiers, best first:

      2. live      — a JWT whose `exp` is still in the future; among these the
                     later expiry is the newer issue
      1. unknown   — no readable `exp`; among these :data:`_OPAQUE_TIE_ORDER`
                     decides, which is where the legacy-desktop compatibility
                     case is resolved
      0. expired   — a JWT we can prove is dead; kept as a last resort rather
                     than discarded, because sending a stale token and getting
                     a clean 401 beats sending nothing at all

    Nothing here reads what is currently installed: the order is a property of
    the candidates, so repeated calls cannot oscillate.
    """
    now = time.time()

    def key(vt: Tuple[str, str]) -> Tuple[int, float, int]:
        var, token = vt
        tie = -(_OPAQUE_TIE_ORDER.index(var) if var in _OPAQUE_TIE_ORDER else len(_OPAQUE_TIE_ORDER))
        expiry = jwt_expiry_epoch(token)
        if expiry is None:
            return (1, 0.0, tie)
        return (2 if expiry > now else 0, expiry, tie)

    return sorted(candidates, key=key, reverse=True)


def read_proxy_token(
    current: str = "",
    callback_token: str = "",
    sources: Sequence[str] = PROXY_TOKEN_VARS,
) -> Tuple[str, str]:
    """The freshest proxy token available, and the name it came under.

    Returns ``("", "")`` when there is none.

    THE ANSWER DEPENDS ONLY ON THE CANDIDATES, NEVER ON WHAT IS CURRENTLY
    INSTALLED. An earlier version broke the tie by preferring "any copy that
    differs from the one in hand", which made the opaque-token case flip on
    every single request: holding A it returned B, then holding B the stable
    sort put A first again and it returned A, for ever. A selector that answers
    differently depending on who is asking is not a selector. `current` is now
    read only to describe the outcome in the log.

    Ranking: readable ``exp`` first (a JWT that lasts longer is the newer
    issue), then :data:`_OPAQUE_TIE_ORDER` for candidates whose expiry cannot
    be read at all.

    `callback_token` participates as an ordinary candidate. It used to be
    consulted first and unconditionally, which let a stale value overwrite a
    fresh one; then it was skipped entirely whenever the environment held
    anything, which silently disabled callers who fetch credentials from
    secure storage. It is neither privileged nor ignored — it is ranked.
    """
    # Build the candidate set, DEDUPED BY VALUE. A callback that hands back a
    # token already sitting in the environment has told us nothing new — it is
    # echoing, not sourcing — so it keeps the environment's label and does not
    # get the "fetched on purpose just now" precedence that belongs to a
    # callback which produced something the environment does not have. Without
    # this, the legacy first-non-empty callback would re-win every tie with the
    # very stale value we are trying to move off.
    present: List[Tuple[str, str]] = []
    seen: Set[str] = set()
    for var in sources:
        token = os.environ.get(var, "")
        if token and token not in seen:
            present.append((var, token))
            seen.add(token)
    if callback_token and callback_token not in seen:
        present.append(("callback", callback_token))
    if not present:
        logger.warning(
            "%s no proxy token available (looked at %s%s)",
            LOG_PREFIX,
            ", ".join(sources),
            " and the refresh callback" if callback_token == "" else "",
        )
        return "", ""

    ranked = rank_candidates(present)
    var, token = ranked[0]

    if len(ranked) > 1:
        logger.info(
            "%s %d tokens present (%s) — chose %s",
            LOG_PREFIX,
            len(ranked),
            ", ".join(v for v, _ in ranked),
            var,
        )
    if current and token != current:
        logger.info("%s selected token differs from the one in use — swapping to %s", LOG_PREFIX, var)
    return token, var


def has_proxy_token() -> bool:
    """Whether ANY proxy token is available.

    The presence checks that gate hosted-proxy features asked only about the
    Google name, so a client that refreshed under a different one looked to
    them like a user who had never signed in — the capability was withdrawn
    while a perfectly good token sat in the environment.
    """
    return any(os.environ.get(var) for var in PROXY_TOKEN_VARS)
