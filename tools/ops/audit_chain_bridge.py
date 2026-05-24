#!/usr/bin/env python3
"""Compatibility shim — audit_chain_bridge moved to ciris_engine in 2.9.0.

The implementation lives at ``ciris_engine.logic.audit.chain_bridge`` so the
A0b upgrade path is reachable from Chaquopy on Android (where ``tools/`` is
not in the bundled ``extractPackages`` list — CIRISAgent#780). This shim
keeps ``python -m tools.ops.audit_chain_bridge`` working for ops / dev
invocations.
"""
from __future__ import annotations

from ciris_engine.logic.audit.chain_bridge import (  # noqa: F401  (re-export)
    BridgeResult,
    main,
    run,
)


if __name__ == "__main__":
    main()
