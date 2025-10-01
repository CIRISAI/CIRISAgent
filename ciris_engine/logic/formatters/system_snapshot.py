from ciris_engine.schemas.runtime.system_context import SystemSnapshot


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
