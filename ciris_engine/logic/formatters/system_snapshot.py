from ciris_engine.schemas.runtime.system_context import ContinuitySummary, SystemSnapshot

from .identity import format_agent_identity


def format_continuity_summary(continuity: ContinuitySummary) -> str:
    """Format continuity awareness metrics for LLM context.

    Parameters
    ----------
    continuity : ContinuitySummary
        Continuity awareness data with startup metrics

    Returns
    -------
    str
        Formatted continuity block
    """
    lines = ["=== Continuity Awareness ==="]

    # First startup
    if continuity.first_startup:
        lines.append(f"First Startup: {continuity.first_startup.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # Lifetime metrics
    def format_duration(seconds: float) -> str:
        """Format seconds into human-readable duration."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            return f"{seconds/60:.1f}m"
        elif seconds < 86400:
            return f"{seconds/3600:.1f}h"
        else:
            days = int(seconds / 86400)
            hours = (seconds % 86400) / 3600
            return f"{days}d {hours:.1f}h"

    lines.append(f"Total Time Online: {format_duration(continuity.total_time_online_seconds)}")
    lines.append(f"Total Time Offline: {format_duration(continuity.total_time_offline_seconds)}")
    lines.append(f"Shutdowns: {continuity.total_shutdowns}")

    # Averages
    if continuity.total_shutdowns > 0:
        lines.append(f"Average Time Online: {format_duration(continuity.average_time_online_seconds)}")
        lines.append(f"Average Time Offline: {format_duration(continuity.average_time_offline_seconds)}")

    # Current session
    if continuity.current_session_start:
        lines.append(f"Current Session Started: {continuity.current_session_start.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(f"Current Session Duration: {format_duration(continuity.current_session_duration_seconds)}")

    # Last shutdown
    if continuity.last_shutdown:
        lines.append(f"Last Shutdown: {continuity.last_shutdown.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        if continuity.last_shutdown_reason:
            lines.append(f"Last Shutdown Reason: {continuity.last_shutdown_reason}")

    return "\n".join(lines)


def format_system_snapshot(system_snapshot: SystemSnapshot) -> str:
    """Summarize core system counters for LLM prompt context.

    Parameters
    ----------
    system_snapshot : dict
        Mapping of counters such as ``pending_tasks`` and ``active_thoughts``.

    Returns
    -------
    str
        Compact block ready to append after task context.
    """

    lines = ["=== System Snapshot ==="]

    # LICENSE DISCLOSURE - MUST appear first per FSD-001
    if hasattr(system_snapshot, "license_disclosure_text") and system_snapshot.license_disclosure_text:
        severity = (getattr(system_snapshot, "license_disclosure_severity", "INFO") or "INFO").upper()
        if severity == "CRITICAL":
            lines.append("🚨🚨🚨 CRITICAL LICENSE DISCLOSURE 🚨🚨🚨")
        elif severity == "WARNING":
            lines.append("⚠️ LICENSE DISCLOSURE ⚠️")
        else:
            lines.append("📋 LICENSE DISCLOSURE")
        lines.append(system_snapshot.license_disclosure_text)
        # Add attestation summary if available
        if hasattr(system_snapshot, "attestation_summary") and system_snapshot.attestation_summary:
            lines.append(f"Verification: {system_snapshot.attestation_summary}")
        lines.append("")  # Empty line for separation

    # Time of System Snapshot
    if hasattr(system_snapshot, "current_time_utc") and system_snapshot.current_time_utc:
        lines.append("Time of System Snapshot:")
        lines.append(f"  UTC: {system_snapshot.current_time_utc}")
        if hasattr(system_snapshot, "current_time_chicago") and system_snapshot.current_time_chicago:
            lines.append(f"  Chicago: {system_snapshot.current_time_chicago}")
        if hasattr(system_snapshot, "current_time_tokyo") and system_snapshot.current_time_tokyo:
            lines.append(f"  Tokyo: {system_snapshot.current_time_tokyo}")
        lines.append("")  # Empty line for separation

    # CRITICAL: Check for resource alerts FIRST
    if hasattr(system_snapshot, "resource_alerts") and system_snapshot.resource_alerts:
        lines.append("🚨🚨🚨 CRITICAL RESOURCE ALERTS 🚨🚨🚨")
        for alert in system_snapshot.resource_alerts:
            lines.append(alert)
        lines.append("🚨🚨🚨 END CRITICAL ALERTS 🚨🚨🚨")
        lines.append("")  # Empty line for emphasis

    # System counts if available
    if hasattr(system_snapshot, "system_counts") and system_snapshot.system_counts:
        counts = system_snapshot.system_counts
        if "pending_tasks" in counts:
            lines.append(f"Pending Tasks: {counts['pending_tasks']}")
        if "pending_thoughts" in counts:
            lines.append(f"Pending Thoughts: {counts['pending_thoughts']}")
        if "total_tasks" in counts:
            lines.append(f"Total Tasks: {counts['total_tasks']}")
        if "total_thoughts" in counts:
            lines.append(f"Total Thoughts: {counts['total_thoughts']}")

    # Continuity Awareness Summary
    if hasattr(system_snapshot, "continuity_summary") and system_snapshot.continuity_summary:
        lines.append("")
        lines.append(format_continuity_summary(system_snapshot.continuity_summary))

    # Telemetry/Resource Usage Summary
    if hasattr(system_snapshot, "telemetry_summary") and system_snapshot.telemetry_summary:
        telemetry = system_snapshot.telemetry_summary
        lines.append("")
        lines.append("=== Resource Usage ===")

        # Current hour usage
        if telemetry.tokens_last_hour > 0:
            lines.append(
                f"Tokens (Last Hour): {int(telemetry.tokens_last_hour):,} tokens, ${telemetry.cost_last_hour_cents/100:.2f}, {telemetry.carbon_last_hour_grams:.1f}g CO2, {telemetry.energy_last_hour_kwh:.3f} kWh"
            )

        # 24h usage
        if telemetry.messages_processed_24h > 0 or telemetry.thoughts_processed_24h > 0:
            # Note: We only have actual last hour data, not 24h totals
            lines.append(f"Messages Processed (24h): {telemetry.messages_processed_24h}")
            lines.append(f"Thoughts Processed (24h): {telemetry.thoughts_processed_24h}")
            lines.append(f"Tasks Completed (24h): {telemetry.tasks_completed_24h}")

        # Activity metrics
        if telemetry.messages_processed_24h > 0:
            lines.append(
                f"Messages Processed: {telemetry.messages_current_hour} (current hour), {telemetry.messages_processed_24h} (24h)"
            )
        if telemetry.thoughts_processed_24h > 0:
            lines.append(
                f"Thoughts Processed: {telemetry.thoughts_current_hour} (current hour), {telemetry.thoughts_processed_24h} (24h)"
            )

        # Error rate if significant
        if telemetry.error_rate_percent > 1.0:
            lines.append(f"⚠️ Error Rate: {telemetry.error_rate_percent:.1f}% ({telemetry.errors_24h} errors in 24h)")

        # Service breakdown if available
        if telemetry.service_calls:
            lines.append("")
            lines.append("Service Usage:")
            for service, count in sorted(telemetry.service_calls.items(), key=lambda x: x[1], reverse=True)[:5]:
                lines.append(f"  - {service}: {count} calls")

    # Context Enrichment Results (pre-run tool results for context-aware action selection)
    if hasattr(system_snapshot, "context_enrichment_results") and system_snapshot.context_enrichment_results:
        lines.append("")
        lines.append("=== Context Enrichment (Pre-fetched Tool Results) ===")
        import logging

        ctx_logger = logging.getLogger(__name__)
        ctx_logger.info(
            f"[CONTEXT BUILDER] Formatting {len(system_snapshot.context_enrichment_results)} enrichment results"
        )
        for tool_key, result in system_snapshot.context_enrichment_results.items():
            lines.append(f"--- {tool_key} ---")
            ctx_logger.info(f"[CONTEXT BUILDER] Processing enrichment result: {tool_key}")
            if isinstance(result, dict):
                if "error" in result:
                    lines.append(f"  Error: {result['error']}")
                    ctx_logger.info(f"[CONTEXT BUILDER] {tool_key} had error: {result['error']}")
                else:
                    # Format the result data in a readable way
                    import json

                    # Log detailed structure for tuning
                    if "entities" in result:
                        ctx_logger.info(
                            f"[CONTEXT BUILDER] {tool_key} has {result.get('count', len(result['entities']))} entities"
                        )
                        for entity in result["entities"][:5]:
                            ctx_logger.info(f"[CONTEXT BUILDER] Entity for LLM: {entity}")
                        if len(result["entities"]) > 5:
                            ctx_logger.info(f"[CONTEXT BUILDER] ... {len(result['entities']) - 5} more entities")

                    # Try to pretty-print, but limit length
                    try:
                        result_str = json.dumps(result, indent=2, default=str)
                        ctx_logger.info(f"[CONTEXT BUILDER] {tool_key} JSON length: {len(result_str)} chars")
                        # Limit to ~2000 chars to avoid bloating the prompt
                        if len(result_str) > 2000:
                            result_str = result_str[:2000] + "\n  ... (truncated)"
                            ctx_logger.info(f"[CONTEXT BUILDER] {tool_key} truncated to 2000 chars")
                        for line in result_str.split("\n"):
                            lines.append(f"  {line}")
                    except (TypeError, ValueError):
                        lines.append(f"  {result}")
            else:
                lines.append(f"  {result}")

    # Legacy fields for backward compatibility
    fields = [
        ("active_tasks", "Active Tasks"),
        ("active_thoughts", "Active Thoughts"),
        ("queue_depth", "Queue Depth"),
        ("error_rate", "Error Rate"),
    ]

    for key, label in fields:
        if hasattr(system_snapshot, key):
            val = getattr(system_snapshot, key)
            if val is not None:
                lines.append(f"{label}: {val}")

    return "\n".join(lines)
