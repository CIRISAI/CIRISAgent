"""Carry the deployment's OAuth provider config across to the node.

WHY THIS EXISTS. Hosted Google sign-in broke in 2.9.14, and not because
anything was missing — because a migration was skipped.

Before the fold, `routes/auth.py` WAS the OAuth implementation. It read the
deployment's provider credentials from a JSON file:

    /home/ciris/shared/oauth/oauth.json     (managed mode, shared volume)
    ~/.ciris/oauth.json                     (standalone fallback)

and built the callback itself from `OAUTH_CALLBACK_BASE_URL`. 2.9.14 deleted
that router and proxied `/v1/auth/*` to the node — which keeps providers in its
OWN store. Nothing carried the file's contents across, so on hosted agents the
node has no Google provider and falls back to its default callback base,
`http://127.0.0.1:4243`. Users were sent to a loopback URL Google rejects.

So the credentials were never lost. The reader was.

TWO WRITES, NOT ONE. The node DERIVES the callback:

    oauth_callback_url(base, provider) -> {base}/v1/auth/oauth/{provider}/callback

so `redirect_uri` is NOT a provider field. `configure_provider`'s payload struct
does not declare it and does not deny unknown fields, so posting one is silently
dropped and the call still answers `200 {"configured":"google"}` — success that
changes nothing. The base lives in a separate config key instead.

AUTHORITY DIFFERS BETWEEN THEM, which is why they fail differently:

  * `POST /v1/auth/oauth/providers` — no auth extractor, no middleware.
  * `PUT  /v1/config/{key}`         — requires an owner session; an unowned node
                                      answers 403 "no responsible party".

So on an unclaimed node the provider registers and the base does not. That is
reported, not retried: a boot-loop of 403s would bury it.

Best-effort throughout. A desktop install has no oauth.json and needs none —
absence is the normal case, not a failure.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

#: Where the deployment provisions provider credentials. Managed mode first,
#: exactly as the deleted router looked for them — production already has this
#: file, which is the whole reason this fix is small.
_SHARED_OAUTH_CONFIG = Path("/home/ciris/shared/oauth/oauth.json")
_LOCAL_OAUTH_CONFIG = Path.home() / ".ciris" / "oauth.json"

#: The node config key holding the public origin the callback is built from.
#: A CEG config key, not an env var — the node takes essentially no env vars.
_CALLBACK_BASE_KEY = "auth.oauth_callback_base_url"

#: The node's default when the key is unset. Seeing this in production IS the bug.
_LOOPBACK_DEFAULT = "http://127.0.0.1:4243"

_TIMEOUT = 10


def _read_provider_config() -> Optional[Dict[str, Any]]:
    """`{provider: {client_id, client_secret, ...}}`, or None if unprovisioned."""
    for path, source in ((_SHARED_OAUTH_CONFIG, "shared volume"), (_LOCAL_OAUTH_CONFIG, "local")):
        try:
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            # Log WHICH SOURCE, never the path or the contents.
            #
            # My first version logged `path`, reasoning that a location is not a
            # secret. CodeQL disagreed and it was right to: this file holds
            # client secrets, so everything derived from it is tainted, and a
            # log line does not get to decide that a credential file's location
            # is the harmless part. `source` is a literal chosen by which branch
            # we are in — it carries nothing from the file — and it answers the
            # only question an operator has here: managed or standalone.
            logger.warning("[OAUTH_SYNC] could not read the %s provider config: %s", source, type(e).__name__)
            continue
        if isinstance(data, dict) and data:
            logger.info("[OAUTH_SYNC] provider config found (%s, %d provider(s))", source, len(data))
            return data
    return None


def _call(method: str, url: str, body: Optional[Dict[str, Any]] = None) -> tuple[int, str]:
    req = urllib.request.Request(url, method=method)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=_TIMEOUT) as r:
            return r.status, r.read(400).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(400).decode("utf-8", errors="replace")
    except Exception as e:  # pragma: no cover - node unreachable
        return 0, f"{type(e).__name__}: {e}"


def _hosted_callback_url(provider: str) -> Optional[str]:
    """The callback URL this deployment has registered with the provider.

    Rebuilds, byte for byte, what the pre-fold router sent and what the identity
    provider's console therefore has on file:

        {OAUTH_CALLBACK_BASE_URL}/v1/auth/oauth/{CIRIS_AGENT_ID}/{provider}/callback

    BUILT FROM THIS AGENT'S OWN ENV, never forwarded from `oauth.json`. That
    file's `callback_url` names whichever agent it was provisioned for — on the
    scout hosts it reads `.../datum/google/callback` — because one Google client
    serves the whole fleet with many redirect URIs registered against it. Copying
    that field would make every agent claim to be datum.

    WHY THE AGENT-ID SEGMENT IS THERE AND WHY IT NEVER REACHES US. nginx routes
    the public path and STRIPS the segment before forwarding:

        location ~ ^/v1/auth/oauth/scout-remote-test-dahrb9/(.+)/callback$ {
            proxy_pass http://agent_.../v1/auth/oauth/$1/callback...;
        }

    so the agent id lives in the PUBLIC url for routing and console registration
    and is never seen by the app. That is exactly what the auth fold lost: the
    node derived `{base}/v1/auth/oauth/{provider}/callback`, a URL nginx does not
    route and no console has, and every hosted login got redirect_uri_mismatch.

    Returns None on a desktop install (no base configured), where the node's
    loopback default is correct per RFC 8252 — a native app is a public client
    and registers a loopback URI. Sending a public URL there would break the one
    platform that still worked.
    """
    base = (os.environ.get("OAUTH_CALLBACK_BASE_URL") or "").strip().rstrip("/")
    agent_id = (os.environ.get("CIRIS_AGENT_ID") or "").strip()
    if not base or not agent_id:
        return None
    return f"{base}/v1/auth/oauth/{agent_id}/{provider}/callback"


def _sync_callback_base(node_url: str) -> None:
    """Point the node's derived callback at the deployment's public origin.

    `OAUTH_CALLBACK_BASE_URL` is the SAME variable the deleted router read, so a
    host that was working before this regression already has it set. Nothing new
    to provision.
    """
    desired = (os.environ.get("OAUTH_CALLBACK_BASE_URL") or "").strip().rstrip("/")
    if not desired:
        # Local/desktop: the loopback default is correct there.
        return

    key_url = f"{node_url}/v1/config/{_CALLBACK_BASE_KEY}"
    status, body = _call("GET", key_url)
    if status == 200 and desired in body:
        logger.info("[OAUTH_SYNC] callback base already %s", desired)
        return

    status, body = _call("PUT", key_url, {"value": desired})
    if status == 200:
        logger.info("[OAUTH_SYNC] callback base set to %s", desired)
    elif status == 403:
        # Reported once, not retried. The write needs an owner session; an
        # unclaimed node cannot have one yet, and a boot-loop of 403s would
        # bury the one line that says what to do.
        logger.warning(
            "[OAUTH_SYNC] cannot set %s — the node refused with 403 (no owner "
            "binding yet). Google sign-in will use the node's default %s and "
            "Google will reject it. Set the key once the node is claimed, or "
            "claim the node.",
            _CALLBACK_BASE_KEY,
            _LOOPBACK_DEFAULT,
        )
    else:
        logger.warning("[OAUTH_SYNC] setting %s returned %s", _CALLBACK_BASE_KEY, status)


def sync_oauth_providers_to_node(node_url: str = "http://127.0.0.1:4243") -> None:
    """Register the deployment's providers with the node, and aim the callback.

    Idempotent: `configure_provider` upserts, so running this every boot is a
    no-op once the values match. Never raises — OAuth being unconfigured must
    not stop an agent from starting, which is the state every desktop install
    is in.
    """
    providers = _read_provider_config()
    if not providers:
        logger.debug("[OAUTH_SYNC] no provider config on this host — nothing to sync")
        return

    for name, cfg in providers.items():
        if not isinstance(cfg, dict):
            continue
        client_id = cfg.get("client_id")
        client_secret = cfg.get("client_secret")
        if not client_id or not client_secret:
            logger.warning("[OAUTH_SYNC] provider %r has no client_id/client_secret — skipped", name)
            continue

        # `callback_url` is accepted from ciris-server 0.5.176 (CIRISServer#421)
        # and returned VERBATIM as the redirect_uri, so the node no longer has to
        # derive a URL it cannot get right — it has no agent id to derive one
        # from. Sending it removes the guess instead of improving it.
        #
        # Older substrates ignore unknown fields and still answer 200, so this is
        # safe to send unconditionally; on those the callback falls back to the
        # derived form exactly as before.
        payload: Dict[str, Any] = {
            "provider": name,
            "client_id": client_id,
            "client_secret": client_secret,
            "metadata": {},
        }
        callback_url = _hosted_callback_url(name)
        if callback_url:
            payload["callback_url"] = callback_url

        status, body = _call("POST", f"{node_url}/v1/auth/oauth/providers", payload)
        if status == 200:
            if callback_url:
                logger.info("[OAUTH_SYNC] provider %r registered; callback %s", name, callback_url)
            else:
                logger.info(
                    "[OAUTH_SYNC] provider %r registered; no OAUTH_CALLBACK_BASE_URL/CIRIS_AGENT_ID, "
                    "so the node keeps its loopback default (correct for a desktop install)",
                    name,
                )
        else:
            # Never log the body on failure: the request carried a client secret
            # and an error echo could include it.
            logger.warning("[OAUTH_SYNC] registering provider %r returned %s", name, status)

    _sync_callback_base(node_url)
