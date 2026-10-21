#!/usr/bin/env python3
"""Fail if the OAuth sign-in button emits a redirect_uri no provider can accept.

WHY NOT A REAL GOOGLE SIGN-IN. That needs interactive consent and account
credentials, neither of which belongs in CI. And it would test the wrong thing:
what broke hosted login was never the consent screen. It was the `redirect_uri`
the agent SENDS, which is fully determined before any browser is involved and
therefore fully checkable here.

The two failure modes this exists to catch, both observed in production:

  * LOOPBACK LEAK. `auth.oauth_callback_base_url` could not be written (the node
    403s until it is claimed), so the base silently fell back to
    `http://127.0.0.1:4243`. A hosted agent then sent a loopback redirect_uri to
    a Web-type credential, which can never accept one. The agent logged success
    throughout.

  * DROPPED AGENT SEGMENT. The node derives
    `{base}/v1/auth/oauth/{provider}/callback`, while the deployment registers
    `{base}/v1/auth/oauth/{agent_id}/{provider}/callback` — nginx strips the
    agent id before forwarding, which is how one client id serves every agent.
    The port dropped that segment (CIRISServer#421), so every hosted login got
    `redirect_uri_mismatch`.

Both are visible in the `Location` header of the authorize redirect, so this
issues the same request the sign-in button does and inspects what comes back.
It deliberately does NOT follow the redirect — that would reach Google.

Scope note: on a DESKTOP install a loopback redirect is CORRECT (RFC 8252 —
a native app is a public client and registers a loopback URI), so loopback is
only an error when a public base is configured. Asserting otherwise would turn
a working desktop login into a red build.
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.parse


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent-port", type=int, default=8080)
    ap.add_argument("--provider", default="google")
    ap.add_argument(
        "--expect-base",
        default=os.environ.get("OAUTH_CALLBACK_BASE_URL", ""),
        help="public origin the deployment provisions; empty means desktop/loopback is fine",
    )
    ap.add_argument("--expect-agent-id", default=os.environ.get("CIRIS_AGENT_ID", ""))
    args = ap.parse_args()

    try:
        import requests
    except ImportError:
        print("::error::requests not installed")
        return 1

    url = f"http://127.0.0.1:{args.agent_port}/v1/auth/oauth/{args.provider}/login"
    try:
        # allow_redirects=False on purpose: we want the Location, not Google.
        resp = requests.get(url, allow_redirects=False, timeout=15)
    except Exception as exc:
        print(f"::error::could not reach the login route ({type(exc).__name__})")
        return 1

    if resp.status_code not in (301, 302, 303, 307, 308):
        print(f"::error::{url} returned {resp.status_code}, expected a redirect to the provider")
        return 1

    location = resp.headers.get("location", "")
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
    redirect_uri = (qs.get("redirect_uri") or [""])[0]
    if not redirect_uri:
        print("::error::authorize redirect carried no redirect_uri")
        return 1

    print(f"  redirect_uri = {redirect_uri}")
    parsed = urllib.parse.urlparse(redirect_uri)
    is_loopback = parsed.hostname in ("127.0.0.1", "localhost", "::1")
    failures: list[str] = []

    if args.expect_base:
        # A public base is configured, so this is a HOSTED agent.
        want_origin = urllib.parse.urlparse(args.expect_base)
        if is_loopback:
            failures.append(
                f"loopback redirect_uri on a hosted agent (base is {args.expect_base}) — the "
                "callback base never reached the node; a Web credential cannot accept loopback"
            )
        elif (parsed.scheme, parsed.netloc) != (want_origin.scheme, want_origin.netloc):
            failures.append(f"origin is {parsed.scheme}://{parsed.netloc}, expected {args.expect_base}")

        if args.expect_agent_id and f"/{args.expect_agent_id}/" not in parsed.path:
            failures.append(
                f"path {parsed.path!r} has no /{args.expect_agent_id}/ segment — deployments "
                "register {base}/v1/auth/oauth/{agent_id}/{provider}/callback (CIRISServer#421)"
            )
    elif not is_loopback:
        # No public base configured => desktop install; loopback is the correct
        # answer and anything else means we are sending a URL nobody registered.
        failures.append(f"desktop install emitted a non-loopback redirect_uri ({redirect_uri})")

    if failures:
        print("::error::the OAuth sign-in button emits a redirect_uri no provider will accept")
        for f in failures:
            print(f"  {f}")
        return 1

    print("  redirect_uri is well-formed for this deployment shape")
    return 0


if __name__ == "__main__":
    sys.exit(main())
