"""Central constants for CIRIS."""

from pathlib import Path
from typing import List

from ciris_engine.schemas.runtime.canonical_peer import CanonicalBootstrapPeer

# Version information
CIRIS_VERSION = "2.9.4-stable"
ACCORD_VERSION = "1.2-Beta"
CIRIS_VERSION_MAJOR = 2
CIRIS_VERSION_MINOR = 9
CIRIS_VERSION_PATCH = 4
CIRIS_VERSION_BUILD = 0
CIRIS_VERSION_STAGE = "stable"
CIRIS_CODENAME = "Context Engineering"  # Codename for this release

# Agent defaults
DEFAULT_TEMPLATE = "default"
DEFAULT_TEMPLATE_PATH = Path("ciris_templates")

# Model defaults
DEFAULT_OPENAI_MODEL_NAME = "gpt-4o-mini"

# Prompt defaults
DEFAULT_PROMPT_TEMPLATE = "default_prompt"

# System defaults
DEFAULT_NUM_ROUNDS = 10

# API defaults
# Security Note: 127.0.0.1 binds to localhost only (recommended for security)
# Use 0.0.0.0 to bind to all interfaces (only for trusted networks/production deployments)
# Configure via CIRIS_API_HOST environment variable
DEFAULT_API_HOST = "127.0.0.1"  # Secure default - localhost only
DEFAULT_API_PORT = 8080

# Timezone and datetime parsing constants
UTC_TIMEZONE_SUFFIX = "+00:00"

# AgentMode: minimum free disk required to run SERVER mode.
# SERVER nodes accept inbound traffic and must be able to absorb sustained
# write load (audit, TSDB consolidation, federation cache, secrets DB). The
# 256 GiB floor leaves headroom for ~12 months of sustained operation at
# the busiest tier we currently observe in production.
SERVER_MINIMUM_DISK_BYTES = 256 * 1024**3

# ---------------------------------------------------------------------------
# Canonical CIRIS federation bootstrap peers.
#
# The agent ships with knowledge of canonical CIRIS federation infrastructure
# (e.g. agents.ciris.ai's datum). On every boot, these peers are reseeded
# into local peer state with `canonical=True`. The user may flip their
# trust state (TRUSTED -> UNTRUSTED / BLOCKED) but cannot permanently
# delete them — they reappear on the next start regardless.
#
# This list is intentionally **empty** today. The framework is in place
# (see ciris_engine/logic/runtime/bootstrap_peers.py) but the canonical
# CIRIS federation addresses are not yet published. Until they are,
# agents will not seed any infrastructure peers — they will only learn
# peers organically via Edge ANNOUNCE events (CIRISEdge#46).
#
# The eventual source of truth is the CIRISRegistry federation-directory
# endpoint. `BootstrapPeerSeeder.fetch_from_registry()` will pull from
# there at boot and fall back to this list on network / parse failure.
# When the directory ships, the entries here remain as the offline
# fallback so air-gapped deployments still get the canonical peer set.
# ---------------------------------------------------------------------------
CIRIS_CANONICAL_BOOTSTRAP_PEERS: List[CanonicalBootstrapPeer] = []
