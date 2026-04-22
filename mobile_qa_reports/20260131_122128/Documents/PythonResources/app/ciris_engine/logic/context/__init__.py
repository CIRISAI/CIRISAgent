from .batch_context import build_system_snapshot_with_batch as build_system_snapshot
from .builder import ContextBuilder
from .secrets_snapshot import build_secrets_snapshot

# CONSOLIDATED: All snapshot building now uses the unified batch approach
# - build_system_snapshot_with_batch handles both batch and single-thought processing
# - Legacy system_snapshot.py::build_system_snapshot is no longer used
# - ContextBuilder.build_system_snapshot() uses the unified batch approach

__all__ = ["ContextBuilder", "build_system_snapshot", "build_secrets_snapshot"]
