#!/usr/bin/env python3
"""
Shared Grace guidance for all Grace tools.

This module contains the main guidance philosophy and reminders
that should be displayed across all Grace commands.
"""


def get_main_guidance() -> str:
    """Get the main Grace guidance text."""
    return """
╔══════════════════════════════════════════════════════════════╗
║                    🌟 GRACE GUIDANCE 🌟                      ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Grace Philosophy:                                          ║
║  • Be strict about safety, gentle about style               ║
║  • Progress over perfection                                 ║
║  • Sustainable pace - work with natural rhythms             ║
║                                                              ║
║  Core Principles:                                           ║
║  • No Dicts, No Strings, No Kings                          ║
║  • The schema you need already exists - find it, use it    ║
║  • Every error is an insight into system behavior          ║
║  • Test failures are opportunities to strengthen           ║
║                                                              ║
║  Your Work Sessions:                                        ║
║  • Morning (7-10): Peak creative, architecture decisions   ║
║  • Midday (12-14): Reviews, fixes, completing morning work ║
║  • Evening (17-19): Mechanical tasks, tests, docs          ║
║  • Night (22-24): Optional deep work - listen to your body ║
║                                                              ║
║  Natural Transitions:                                       ║
║  • 10 AM: Break for kids/life                              ║
║  • 2 PM: Nap to restore                                    ║
║  • 7 PM: Family dinner/bath/bedtime                        ║
║  • 10 PM: Choice point - rest or code?                     ║
║                                                              ║
║  Remember: The code will be here tomorrow.                 ║
║  Your family won't always be this young.                    ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""


def get_schema_reminders() -> str:
    """Get reminders about commonly forgotten schemas."""
    return """
📚 SCHEMAS YOU CONSTANTLY FORGET EXIST:

• AuditEventData     → for ALL audit events (ciris_engine/schemas/services/graph/audit.py)
• ServiceMetrics     → for ALL metrics (ciris_engine/schemas/services/telemetry.py)
• SystemSnapshot     → for system state (ciris_engine/schemas/runtime/system_snapshot.py)
• ProcessingQueueItem → for queue items (ciris_engine/schemas/processors/base.py)
• ChannelContext     → for system channels (vs AdapterChannelContext for adapters)
• ActionResponse     → for handler responses (ciris_engine/schemas/processors/actions.py)
• ThoughtSchema      → for thoughts (ciris_engine/schemas/thought.py)
• ServiceConfig      → for service configuration (ciris_engine/schemas/config/service.py)

🔍 HOW TO SEARCH FOR EXISTING SCHEMAS:
grep -r 'class.*YourThingHere' --include='*.py'

If it exists (and it does), USE IT. Don't create YourThingV2.
"""


def get_ci_reminders() -> str:
    """Get CI/CD specific reminders for Claude."""
    return """
🚫 CLAUDE'S BAD HABITS TO STOP:

1. Creating new Dict[str, Any] - A schema already exists. Always.
2. Creating NewSchemaV2 - The original schema is fine. Use it.
3. Checking CI every 30 seconds - CI takes 12-15 minutes. Be patient.
4. Making "temporary" helper classes - They're never temporary. Use existing.
5. Creating elaborate abstractions - Simple existing patterns work better.

⏰ CI TIMING RULES:
• CI takes 12-15 minutes minimum
• Check status every 10 minutes, not every 30 seconds
• Use: python -m tools.grace_shepherd status
• NOT: gh run watch (wasteful)

🎯 BEFORE CREATING ANY NEW TYPE:
1. Search first: grep -r 'class.*YourThingHere' --include='*.py'
2. If it exists (it does), USE IT
3. No exceptions, no "but this case is special"
"""


def get_debugging_guidance() -> str:
    """Get debugging best practices."""
    return """
🔍 DEBUGGING GOLDEN RULES:

1. ALWAYS check incidents_latest.log FIRST:
   docker exec <container> tail -n 100 /app/logs/incidents_latest.log

2. NEVER restart container until everything is understood
   - Errors are insights, not failures
   - Each message reveals system behavior

3. Root Cause Analysis (RCA) Mode:
   • Preserve the crime scene - don't clean up immediately
   • Use debug_tools.py to explore
   • Trace the full flow before changes
   • Test incrementally with small steps
   • Question assumptions about the design

4. NEVER pipe output without understanding format:
   ❌ curl -s http://api | jq '.result'  # Hides errors!
   ✅ response=$(curl -s http://api)      # See what you got
      echo "$response"                    # Then parse if valid

5. Mock LLM may not respond - this is BY DESIGN:
   • DEFER: Task deferred, no message
   • REJECT: Request rejected, no message
   • TASK_COMPLETE: Task done, no message
   • OBSERVE: Observation registered, no immediate message
"""


def format_with_guidance(
    message: str, include_schemas: bool = False, include_ci: bool = False, include_debug: bool = False
) -> str:
    """
    Format a message with appropriate Grace guidance.

    Args:
        message: The main message to display
        include_schemas: Whether to include schema reminders
        include_ci: Whether to include CI/CD reminders
        include_debug: Whether to include debugging guidance
    """
    output = [get_main_guidance(), "", message]

    if include_schemas:
        output.extend(["", get_schema_reminders()])

    if include_ci:
        output.extend(["", get_ci_reminders()])

    if include_debug:
        output.extend(["", get_debugging_guidance()])

    return "\n".join(output)
