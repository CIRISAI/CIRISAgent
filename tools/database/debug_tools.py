#!/usr/bin/env python3
"""
CIRIS Debug Tools - Direct persistence and protocol queries for troubleshooting.

Usage:
    python debug_tools.py tasks              # List all tasks with status
    python debug_tools.py task <task_id>     # Show task details with thoughts
    python debug_tools.py thoughts <task_id> # List thoughts for a task
    python debug_tools.py thought <id>       # Show thought details
    python debug_tools.py channel <task_id>  # Trace channel context
    python debug_tools.py correlations       # Show recent service correlations
    python debug_tools.py trace <trace_id>   # Show trace hierarchy
    python debug_tools.py traces             # List recent trace IDs
    python debug_tools.py incidents          # Show recent incidents
    python debug_tools.py api-messages       # Show API message queue
    python debug_tools.py investigate <id>   # Investigate stuck thought (prefix OK)
    python debug_tools.py guidance           # Show all guidance thoughts
    python debug_tools.py context <channel>  # Show conversation context for channel
    python debug_tools.py history            # Analyze conversation history in thoughts
    python debug_tools.py contexts           # Analyze all context building patterns
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Add the project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ciris_engine.logic import persistence
from ciris_engine.logic.persistence.db.core import get_db_connection


def list_tasks(status_filter=None):
    """List all tasks with basic info."""
    tasks = persistence.get_all_tasks()
    if status_filter:
        tasks = [t for t in tasks if t.status.value == status_filter]

    print(f"\n{'='*100}")
    print(f"TASKS ({len(tasks)} total)")
    print(f"{'='*100}")
    print(f"{'Task ID':<40} {'Status':<15} {'Priority':<8} {'Description'}")
    print(f"{'-'*100}")

    for task in sorted(tasks, key=lambda t: t.created_at, reverse=True)[:20]:
        desc = task.description[:40] + "..." if len(task.description) > 40 else task.description
        print(f"{task.task_id:<40} {task.status.value:<15} {task.priority:<8} {desc}")


def show_task_details(task_id):
    """Show detailed task information including thoughts."""
    task = persistence.get_task_by_id(task_id)
    if not task:
        print(f"Task {task_id} not found")
        return

    print(f"\n{'='*100}")
    print(f"TASK DETAILS: {task_id}")
    print(f"{'='*100}")
    print(f"Description: {task.description}")
    print(f"Status: {task.status.value}")
    print(f"Priority: {task.priority}")
    print(f"Created: {task.created_at}")
    print(f"Updated: {task.updated_at}")

    # Show context
    print(f"\nContext Type: {type(task.context).__name__}")
    if hasattr(task.context, "initial_task_context") and task.context.initial_task_context:
        itc = task.context.initial_task_context
        print(f"  Author: {itc.author_name} ({itc.author_id})")
        print(f"  Origin: {itc.origin_service}")
        if itc.channel_context:
            print(f"  Channel: {itc.channel_context.channel_id} ({itc.channel_context.channel_type})")

    # Show thoughts
    thoughts = persistence.get_thoughts_by_task_id(task_id)
    print(f"\nThoughts ({len(thoughts)}):")
    print(f"{'-'*100}")
    for i, thought in enumerate(thoughts):
        print(f"{i+1}. [{thought.thought_type.value}] (depth {thought.thought_depth}, status: {thought.status.value})")
        print(f"   ID: {thought.thought_id}")
        print(f"   Content: {thought.content[:80]}...")


def trace_channel_context(task_id):
    """Trace channel context through task and thoughts."""
    task = persistence.get_task_by_id(task_id)
    if not task:
        print(f"Task {task_id} not found")
        return

    print(f"\n{'='*100}")
    print(f"CHANNEL CONTEXT TRACE: {task_id}")
    print(f"{'='*100}")

    def extract_channel(context, prefix=""):
        """Extract channel info from context."""
        if not context:
            print(f"{prefix}Context: None")
            return

        print(f"{prefix}Context Type: {type(context).__name__}")

        if hasattr(context, "initial_task_context") and context.initial_task_context:
            itc = context.initial_task_context
            if itc.channel_context:
                cc = itc.channel_context
                print(f"{prefix}  Channel via initial_task_context: {cc.channel_id} (type: {cc.channel_type})")
            else:
                print(f"{prefix}  No channel_context in initial_task_context")

        if hasattr(context, "system_snapshot") and context.system_snapshot:
            ss = context.system_snapshot
            if ss.channel_context:
                cc = ss.channel_context
                print(f"{prefix}  Channel via system_snapshot: {cc.channel_id} (type: {cc.channel_type})")
            else:
                print(f"{prefix}  No channel_context in system_snapshot")

    print("\nTask Context:")
    extract_channel(task.context, "  ")

    thoughts = persistence.get_thoughts_by_task_id(task_id)
    print(f"\nThought Contexts ({len(thoughts)} thoughts):")
    for i, thought in enumerate(thoughts):
        print(f"\n{i+1}. Thought {thought.thought_id} [{thought.thought_type.value}]:")
        extract_channel(thought.context, "  ")


def show_correlations(limit=20, trace_id=None):
    """Show recent service correlations with trace hierarchy."""
    conn = get_db_connection()

    if trace_id:
        # Show trace hierarchy
        cursor = conn.execute(
            """
            SELECT correlation_id, service_type, handler_name, action_type,
                   status, created_at, request_data, response_data,
                   trace_id, span_id, parent_span_id, updated_at
            FROM service_correlations
            WHERE trace_id = ?
            ORDER BY created_at ASC
        """,
            (trace_id,),
        )
    else:
        # Show recent correlations
        cursor = conn.execute(
            """
            SELECT correlation_id, service_type, handler_name, action_type,
                   status, created_at, request_data, response_data,
                   trace_id, span_id, parent_span_id, updated_at
            FROM service_correlations
            ORDER BY created_at DESC
            LIMIT ?
        """,
            (limit,),
        )

    rows = cursor.fetchall()
    print(f"\n{'='*100}")
    print(f"{'TRACE HIERARCHY' if trace_id else 'RECENT CORRELATIONS'} ({len(rows)} shown)")
    print(f"{'='*100}")

    # Build parent-child relationships if showing trace
    traces = {}
    for row in rows:
        corr_id = row[0]
        traces[corr_id] = {"row": row, "children": []}

    # Link children to parents using span relationships
    span_to_corr = {}
    for corr_id, trace_info in traces.items():
        span_id = trace_info["row"][9]  # span_id
        if span_id:
            span_to_corr[span_id] = corr_id

    for corr_id, trace_info in traces.items():
        parent_span_id = trace_info["row"][10]  # parent_span_id
        if parent_span_id and parent_span_id in span_to_corr:
            parent_corr_id = span_to_corr[parent_span_id]
            if parent_corr_id in traces:
                traces[parent_corr_id]["children"].append(corr_id)

    # Display function with indentation
    def display_correlation(row, indent=0):
        (
            corr_id,
            svc_type,
            handler,
            action,
            status,
            created,
            req_data,
            resp_data,
            trace_id,
            span_id,
            parent_span_id,
            updated,
        ) = row
        prefix = "  " * indent + ("└─ " if indent > 0 else "")

        # Calculate duration
        duration = ""
        if updated and created:
            try:
                start = datetime.fromisoformat(created.replace("Z", "+00:00"))
                end = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                duration_ms = (end - start).total_seconds() * 1000
                duration = f" [{duration_ms:.0f}ms]"
            except (ValueError, TypeError, AttributeError):
                pass

        print(f"\n{prefix}{created} - {handler} -> {action} ({status}){duration}")
        print(f"{prefix}  Correlation: {corr_id}")

        # Show trace context
        if trace_id:
            print(f"{prefix}  Trace: {trace_id} / Span: {span_id}")
            if parent_span_id:
                print(f"{prefix}  Parent Span: {parent_span_id}")

        # Show request details
        if req_data:
            try:
                data = json.loads(req_data)
                if "thought_id" in data:
                    print(f"{prefix}  Thought: {data['thought_id']}")
                if "task_id" in data:
                    print(f"{prefix}  Task: {data['task_id']}")
                if "channel_id" in data:
                    print(f"{prefix}  Channel: {data['channel_id']}")
                if "parameters" in data and data["parameters"]:
                    print(f"{prefix}  Params: {str(data['parameters'])[:80]}...")
            except (json.JSONDecodeError, TypeError, KeyError):
                pass

        # Show response summary
        if resp_data:
            try:
                resp = json.loads(resp_data)
                if not resp.get("success"):
                    print(f"{prefix}  ERROR: {resp.get('error_message', 'Unknown error')}")
                elif resp.get("result_summary"):
                    print(f"{prefix}  Result: {resp['result_summary'][:80]}...")
            except (json.JSONDecodeError, TypeError, KeyError):
                pass

    if trace_id:
        # Display as hierarchy
        root_traces = [t for cid, t in traces.items() if not t["row"][10]]  # No parent_span_id
        for trace_info in root_traces:
            display_correlation(trace_info["row"])

            # Display children recursively
            def show_children(parent_id, level=1):
                for child_id in traces[parent_id]["children"]:
                    display_correlation(traces[child_id]["row"], level)
                    show_children(child_id, level + 1)

            show_children(trace_info["row"][0])
    else:
        # Display flat list
        for row in rows:
            display_correlation(row)


def show_incidents():
    """Show recent incidents."""
    incidents_path = Path("logs/incidents_latest.log")
    if not incidents_path.exists():
        print("Incidents log not found")
        return

    print(f"\n{'='*100}")
    print("RECENT INCIDENTS (last 50 lines)")
    print(f"{'='*100}")

    with open(incidents_path) as f:
        lines = f.readlines()
        for line in lines[-50:]:
            print(line.rstrip())


def show_api_messages(channel_id=None):
    """Show API message queue."""
    try:

        # This is a debug tool, so we'll query the database directly
        conn = get_db_connection()

        # Check if there's a messages table (if API adapter stores them)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%message%'")
        tables = cursor.fetchall()

        if tables:
            print(f"\n{'='*100}")
            print("MESSAGE TABLES FOUND:")
            print(f"{'='*100}")
            for table in tables:
                print(f"  - {table[0]}")
        else:
            print("No message tables found in database")

    except Exception as e:
        print(f"Error accessing API messages: {e}")


def list_traces(limit=20):
    """List recent unique trace IDs."""
    conn = get_db_connection()
    cursor = conn.execute(
        """
        SELECT DISTINCT
            trace_id,
            MIN(created_at) as first_seen,
            MAX(created_at) as last_seen,
            COUNT(*) as span_count
        FROM service_correlations
        WHERE trace_id IS NOT NULL
        GROUP BY trace_id
        ORDER BY last_seen DESC
        LIMIT ?
    """,
        (limit,),
    )

    rows = cursor.fetchall()
    print(f"\n{'='*100}")
    print(f"RECENT TRACES ({len(rows)} shown)")
    print(f"{'='*100}")
    print(f"{'Trace ID':<40} {'First Seen':<20} {'Last Seen':<20} {'Spans'}")
    print(f"{'-'*100}")

    for trace_id, first, last, count in rows:
        if trace_id:
            print(f"{trace_id:<40} {first[:19]:<20} {last[:19]:<20} {count}")


def show_thoughts(status="PENDING", thought_type=None):
    """Show thoughts by status and optionally by type."""
    conn = get_db_connection()

    if thought_type:
        cursor = conn.execute(
            """
            SELECT thought_id, source_task_id, thought_type, status,
                   thought_depth, created_at, content, parent_thought_id,
                   round_number, updated_at
            FROM thoughts
            WHERE status = ? AND thought_type = ?
            ORDER BY created_at DESC
            LIMIT 20
        """,
            (status, thought_type),
        )
    else:
        cursor = conn.execute(
            """
            SELECT thought_id, source_task_id, thought_type, status,
                   thought_depth, created_at, content, parent_thought_id,
                   round_number, updated_at
            FROM thoughts
            WHERE status = ?
            ORDER BY created_at DESC
            LIMIT 20
        """,
            (status,),
        )

    rows = cursor.fetchall()
    filter_desc = f"{status} {thought_type or ''}" if thought_type else status
    print(f"\n{'='*100}")
    print(f"{filter_desc} THOUGHTS ({len(rows)} shown)")
    print(f"{'='*100}")

    for thought_id, task_id, thought_type, status, depth, created, content, parent_id, round_num, updated in rows:
        print(f"\n{created} - {thought_type} (depth {depth}, round {round_num})")
        print(f"  Thought: {thought_id}")
        print(f"  Task: {task_id}")
        if parent_id:
            print(f"  Parent: {parent_id}")
        print(f"  Updated: {updated}")
        print(f"  Content: {content[:100]}...")


def show_tasks(limit=10):
    """Show recent tasks with thought counts."""
    conn = get_db_connection()
    cursor = conn.execute(
        """
        SELECT t.task_id, t.description, t.status, t.priority, t.created_at,
               COUNT(th.thought_id) as thought_count
        FROM tasks t
        LEFT JOIN thoughts th ON t.task_id = th.source_task_id
        GROUP BY t.task_id
        ORDER BY t.created_at DESC
        LIMIT ?
    """,
        (limit,),
    )

    rows = cursor.fetchall()
    print(f"\n{'='*100}")
    print(f"RECENT TASKS ({len(rows)} shown)")
    print(f"{'='*100}")

    for task_id, desc, status, priority, created, thought_count in rows:
        print(f"\n{created} - {status} (priority {priority})")
        print(f"  Task: {task_id}")
        print(f"  Description: {desc[:80]}...")
        print(f"  Thoughts: {thought_count}")


def show_handler_metrics():
    """Show handler execution metrics."""
    conn = get_db_connection()
    cursor = conn.execute(
        """
        SELECT handler_name, action_type, status,
               COUNT(*) as exec_count,
               AVG(JULIANDAY(updated_at) - JULIANDAY(created_at)) * 86400000 as avg_ms
        FROM service_correlations
        WHERE handler_name IS NOT NULL
        GROUP BY handler_name, action_type, status
        ORDER BY exec_count DESC
    """
    )

    rows = cursor.fetchall()
    print(f"\n{'='*100}")
    print("HANDLER METRICS")
    print(f"{'='*100}")
    print(f"{'Handler':<30} {'Action':<20} {'Status':<15} {'Count':<10} {'Avg MS'}")
    print(f"{'-'*100}")

    for handler, action, status, count, avg_ms in rows:
        avg_str = f"{avg_ms:.1f}" if avg_ms else "N/A"
        print(f"{handler:<30} {action:<20} {status:<15} {count:<10} {avg_str}")


def investigate_stuck_thought(thought_id_prefix):
    """Investigate a stuck thought - show all related data."""
    conn = get_db_connection()

    # Find the thought
    cursor = conn.execute(
        """
        SELECT thought_id, source_task_id, thought_type, status,
               thought_depth, parent_thought_id, round_number,
               created_at, updated_at, content
        FROM thoughts
        WHERE thought_id LIKE ?
    """,
        (f"{thought_id_prefix}%",),
    )

    thought_row = cursor.fetchone()
    if not thought_row:
        print(f"No thought found with ID starting with {thought_id_prefix}")
        return

    (thought_id, task_id, thought_type, status, depth, parent_id, round_num, created, updated, content) = thought_row

    print(f"\n{'='*100}")
    print(f"INVESTIGATING STUCK THOUGHT: {thought_id}")
    print(f"{'='*100}")

    print(f"\nTHOUGHT DETAILS:")
    print(f"  Type: {thought_type}")
    print(f"  Status: {status}")
    print(f"  Depth: {depth}")
    print(f"  Round: {round_num}")
    print(f"  Parent: {parent_id}")
    print(f"  Created: {created}")
    print(f"  Updated: {updated}")
    print(f"  Content Preview: {content[:200] if content else 'None'}...")

    # Check task status
    cursor = conn.execute("SELECT task_id, description, status, priority FROM tasks WHERE task_id = ?", (task_id,))
    task_row = cursor.fetchone()
    if task_row:
        print(f"\nTASK STATUS:")
        print(f"  Task ID: {task_row[0]}")
        print(f"  Description: {task_row[1][:100]}...")
        print(f"  Status: {task_row[2]}")
        print(f"  Priority: {task_row[3]}")

    # Check all thoughts for this task
    cursor = conn.execute(
        """
        SELECT thought_id, thought_type, status, round_number, created_at
        FROM thoughts
        WHERE source_task_id = ?
        ORDER BY created_at DESC
    """,
        (task_id,),
    )

    print(f"\nALL THOUGHTS FOR TASK {task_id}:")
    for row in cursor.fetchall():
        tid, ttype, tstatus, tround, tcreated = row
        marker = " <-- THIS ONE" if tid == thought_id else ""
        print(f"  {tcreated} | {tid[:8]}... | {ttype:12} | {tstatus:12} | Round {tround}{marker}")

    # Check correlations for this thought
    cursor = conn.execute(
        """
        SELECT correlation_id, handler_name, action_type, status,
               created_at, updated_at, request_data
        FROM service_correlations
        WHERE request_data LIKE ?
        ORDER BY created_at DESC
        LIMIT 10
    """,
        (f'%"{thought_id}"%',),
    )

    corr_rows = cursor.fetchall()
    if corr_rows:
        print(f"\nCORRELATIONS FOR THOUGHT {thought_id[:8]}...:")
        for row in corr_rows:
            corr_id, handler, action, corr_status, corr_created, corr_updated, req_data = row
            print(f"  {corr_created} | {handler:20} | {action:15} | {corr_status}")

    # Check if thought is in processing queue
    print(f"\nPROCESSING STATUS:")
    print(f"  Thought has been in {status} status for:")
    if updated and created:
        try:
            start = datetime.fromisoformat(created.replace("Z", "+00:00"))
            end = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            duration = (end - start).total_seconds()
            print(f"    {duration:.1f} seconds since last update")
        except:
            pass

    # Check parent thought if exists
    if parent_id:
        cursor = conn.execute("SELECT thought_type, status, content FROM thoughts WHERE thought_id = ?", (parent_id,))
        parent_row = cursor.fetchone()
        if parent_row:
            print(f"\nPARENT THOUGHT {parent_id[:8]}...:")
            print(f"  Type: {parent_row[0]}")
            print(f"  Status: {parent_row[1]}")
            print(f"  Content preview: {parent_row[2][:100] if parent_row[2] else 'None'}...")


def show_guidance_thoughts():
    """Show all guidance thoughts and their processing status."""
    conn = get_db_connection()
    cursor = conn.execute(
        """
        SELECT t.thought_id, t.source_task_id, t.status, t.round_number,
               t.created_at, t.updated_at, t.parent_thought_id,
               tk.description, tk.status as task_status
        FROM thoughts t
        LEFT JOIN tasks tk ON t.source_task_id = tk.task_id
        WHERE t.thought_type = 'guidance'
        ORDER BY t.created_at DESC
        LIMIT 20
    """
    )

    rows = cursor.fetchall()
    print(f"\n{'='*100}")
    print(f"GUIDANCE THOUGHTS ({len(rows)} found)")
    print(f"{'='*100}")

    for row in rows:
        (thought_id, task_id, status, round_num, created, updated, parent_id, task_desc, task_status) = row

        print(f"\n{created} - Status: {status} (Round {round_num})")
        print(f"  Thought: {thought_id}")
        print(f"  Parent: {parent_id[:8]}... " if parent_id else "  No parent")
        print(f"  Task: {task_id[:20]}... ({task_status})")
        if task_desc:
            print(f"  Task Desc: {task_desc[:60]}...")

        # Calculate how long in current status
        if updated and created:
            try:
                start = datetime.fromisoformat(created.replace("Z", "+00:00"))
                end = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                duration = (end - start).total_seconds()
                if duration > 60:
                    print(f"  ⚠️  In {status} for {duration:.0f} seconds!")
            except:
                pass


def show_channel_context(channel_id):
    """Show conversation context for a specific channel."""
    print(f"\n{'='*100}")
    print(f"CONVERSATION CONTEXT FOR CHANNEL: {channel_id}")
    print(f"{'='*100}")

    # Get recent correlations for this channel
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
    SELECT correlation_id, action_type, handler_name, request_data, created_at
    FROM service_correlations
    WHERE request_data LIKE ?
    ORDER BY created_at DESC
    LIMIT 20
    """

    cursor.execute(query, (f"%{channel_id}%",))
    correlations = cursor.fetchall()

    print(f"\nFound {len(correlations)} correlations for this channel\n")

    observe_count = 0
    speak_count = 0

    for corr in correlations:
        action = corr[1]
        handler = corr[2]
        created = corr[4]

        if action == "observe":
            observe_count += 1
        elif action == "speak":
            speak_count += 1

        try:
            req_data = json.loads(corr[3]) if corr[3] else {}
            message = req_data.get("parameters", {}).get("content", "")
            if message:
                message = message[:100] + "..." if len(message) > 100 else message
                print(f"{created}: {action:10} | {message}")
        except:
            print(f"{created}: {action:10} | (no message data)")

    print(f"\n{'Summary':20}: {observe_count} observations, {speak_count} speak actions")
    conn.close()


def analyze_conversation_history():
    """Analyze conversation history in recent observation thoughts."""
    print(f"\n{'='*100}")
    print("CONVERSATION HISTORY ANALYSIS")
    print(f"{'='*100}")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get recent observation thoughts
    query = """
    SELECT thought_id, content, created_at
    FROM thoughts
    WHERE thought_type = 'observation'
      AND created_at > datetime('now', '-2 hours')
    ORDER BY created_at DESC
    LIMIT 20
    """

    cursor.execute(query)
    thoughts = cursor.fetchall()

    print(f"\nAnalyzing {len(thoughts)} recent observation thoughts:\n")

    with_history = 0
    without_history = 0
    total_history_msgs = 0
    total_history_chars = 0

    for thought in thoughts:
        thought_id = thought[0]
        content = thought[1] if thought[1] else ""
        created = thought[2]

        if "CONVERSATION HISTORY" in content:
            with_history += 1

            # Count history entries
            history_count = content.count(". @")
            total_history_msgs += history_count

            # Calculate history size
            history_start = content.find("=== CONVERSATION HISTORY")
            history_end = content.find("=== EVALUATE")
            if history_start > 0 and history_end > history_start:
                history_section = content[history_start:history_end]
                total_history_chars += len(history_section)

            print(f"✅ {created}: {thought_id[:20]}... - {history_count} messages in history")
        else:
            without_history += 1
            print(f"❌ {created}: {thought_id[:20]}... - NO HISTORY")

    print(f"\n{'='*50}")
    print(f"SUMMARY:")
    print(f"  With history:    {with_history} thoughts ({with_history*100//len(thoughts) if thoughts else 0}%)")
    print(f"  Without history: {without_history} thoughts ({without_history*100//len(thoughts) if thoughts else 0}%)")
    if with_history > 0:
        print(f"  Avg messages:    {total_history_msgs // with_history} per thought")
        print(f"  Avg history size: {total_history_chars // with_history} chars")

    conn.close()


def analyze_context_building():
    """Analyze context building patterns in recent thoughts."""
    print(f"\n{'='*100}")
    print("CONTEXT BUILDING ANALYSIS")
    print(f"{'='*100}")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get recent thoughts with context
    query = """
    SELECT t.thought_id, t.thought_type, t.content, t.created_at, t.context
    FROM thoughts t
    WHERE t.created_at > datetime('now', '-2 hours')
      AND t.content IS NOT NULL
    ORDER BY t.created_at DESC
    LIMIT 30
    """

    cursor.execute(query)
    thoughts = cursor.fetchall()

    print(f"\nAnalyzing {len(thoughts)} recent thoughts for context patterns:\n")

    # Statistics
    with_user_context = 0
    with_channel_context = 0
    with_conversation_history = 0
    channel_ids_found = set()
    user_ids_found = set()

    for thought in thoughts:
        thought_id = thought[0]
        thought_type = thought[1]
        content = thought[2] if thought[2] else ""
        created = thought[3]
        context = thought[4] if thought[4] else ""

        # Check for various context elements
        has_user = False
        has_channel = False
        has_history = False

        # Check content for patterns
        if "@" in content and "ID:" in content:
            has_user = True
            with_user_context += 1
            # Extract user IDs
            import re

            user_pattern = r"ID:\s*([^\s\)]+)"
            matches = re.findall(user_pattern, content)
            user_ids_found.update(matches[:3])  # First 3 user IDs

        if "channel" in content.lower() or "discord_" in content:
            has_channel = True
            with_channel_context += 1
            # Extract channel IDs
            channel_pattern = r"(discord_\d+_\d+|cli_[^\s]+|api_[^\s]+)"
            matches = re.findall(channel_pattern, content)
            channel_ids_found.update(matches[:3])

        if "CONVERSATION HISTORY" in content:
            has_history = True
            with_conversation_history += 1

        # Print summary for this thought
        indicators = []
        if has_user:
            indicators.append("U")
        if has_channel:
            indicators.append("C")
        if has_history:
            indicators.append("H")

        indicator_str = f"[{'/'.join(indicators) if indicators else '-'}]"
        print(f"{created}: {thought_type:12} {indicator_str:8} {thought_id[:20]}...")

    print(f"\n{'='*50}")
    print(f"CONTEXT STATISTICS:")
    print(
        f"  With user context:     {with_user_context}/{len(thoughts)} ({with_user_context*100//len(thoughts) if thoughts else 0}%)"
    )
    print(
        f"  With channel context:  {with_channel_context}/{len(thoughts)} ({with_channel_context*100//len(thoughts) if thoughts else 0}%)"
    )
    print(
        f"  With conversation:     {with_conversation_history}/{len(thoughts)} ({with_conversation_history*100//len(thoughts) if thoughts else 0}%)"
    )
    print(f"\n  Unique channels found: {len(channel_ids_found)}")
    for ch_id in list(channel_ids_found)[:3]:
        print(f"    - {ch_id}")
    print(f"\n  Unique users found:    {len(user_ids_found)}")
    for user_id in list(user_ids_found)[:3]:
        print(f"    - {user_id}")

    conn.close()


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1]

    if command == "tasks":
        status = sys.argv[2] if len(sys.argv) > 2 else None
        list_tasks(status)

    elif command == "task" and len(sys.argv) > 2:
        show_task_details(sys.argv[2])

    elif command == "thoughts" and len(sys.argv) > 2:
        task_id = sys.argv[2]
        thoughts = persistence.get_thoughts_by_task_id(task_id)
        print(f"\nThoughts for task {task_id}:")
        for i, t in enumerate(thoughts):
            print(f"{i+1}. [{t.thought_type.value}] {t.thought_id} (depth {t.thought_depth}, status: {t.status.value})")
            print(f"   {t.content[:100]}...")

    elif command == "thought" and len(sys.argv) > 2:
        thought = persistence.get_thought_by_id(sys.argv[2])
        if thought:
            print(f"\nThought {thought.thought_id}:")
            print(f"  Type: {thought.thought_type.value}")
            print(f"  Status: {thought.status.value}")
            print(f"  Depth: {thought.thought_depth}")
            print(f"  Task: {thought.source_task_id}")
            print(f"  Content: {thought.content}")
            print(f"  Context: {thought.context}")
        else:
            print("Thought not found")

    elif command == "channel" and len(sys.argv) > 2:
        trace_channel_context(sys.argv[2])

    elif command == "correlations":
        show_correlations()

    elif command == "trace" and len(sys.argv) > 2:
        show_correlations(trace_id=sys.argv[2])

    elif command == "traces":
        list_traces()

    elif command == "incidents":
        show_incidents()

    elif command == "api-messages":
        channel = sys.argv[2] if len(sys.argv) > 2 else None
        show_api_messages(channel)

    elif command == "investigate" and len(sys.argv) > 2:
        investigate_stuck_thought(sys.argv[2])

    elif command == "guidance":
        show_guidance_thoughts()

    elif command == "context" and len(sys.argv) > 2:
        show_channel_context(sys.argv[2])

    elif command == "history":
        analyze_conversation_history()

    elif command == "contexts":
        analyze_context_building()

    else:
        print(__doc__)


# Add these functions that were referenced in the debug script but not included

# Make functions available when imported
__all__ = [
    "list_tasks",
    "show_task_details",
    "trace_channel_context",
    "show_correlations",
    "show_incidents",
    "show_api_messages",
    "list_traces",
    "show_thoughts",
    "show_tasks",
    "show_handler_metrics",
    "investigate_stuck_thought",
    "show_guidance_thoughts",
    "show_channel_context",
    "analyze_conversation_history",
    "analyze_context_building",
]


if __name__ == "__main__":
    main()
