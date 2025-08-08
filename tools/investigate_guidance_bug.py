#!/usr/bin/env python3
"""
Investigate the guidance thought bug more thoroughly.
This script will help us understand:
1. What status the thought was created with
2. Whether it ever entered any processing queue
3. Why it's stuck
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Add the project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ciris_engine.logic.persistence.db.core import get_db_connection


def investigate_guidance_processing():
    """Deep dive into guidance thought processing."""
    conn = get_db_connection()

    print("\n" + "=" * 100)
    print("GUIDANCE THOUGHT PROCESSING INVESTIGATION")
    print("=" * 100)

    # 1. Find all guidance thoughts
    cursor = conn.execute(
        """
        SELECT thought_id, source_task_id, status, round_number,
               created_at, updated_at, parent_thought_id, content
        FROM thoughts
        WHERE thought_type = 'guidance'
        ORDER BY created_at DESC
    """
    )

    guidance_thoughts = cursor.fetchall()
    print(f"\n1. GUIDANCE THOUGHTS FOUND: {len(guidance_thoughts)}")

    for thought in guidance_thoughts:
        thought_id = thought[0]
        status = thought[2]
        created = thought[4]
        updated = thought[5]

        print(f"\n  Thought: {thought_id}")
        print(f"  Status: {status}")
        print(f"  Created: {created}")
        print(f"  Updated: {updated}")

        # Check if created == updated (never processed)
        if created == updated:
            print(f"  ⚠️  NEVER UPDATED - created and updated timestamps are identical!")

        # 2. Check if this thought ever appeared in correlations
        cursor2 = conn.execute(
            """
            SELECT COUNT(*) as correlation_count
            FROM service_correlations
            WHERE request_data LIKE ? OR response_data LIKE ?
        """,
            (f"%{thought_id}%", f"%{thought_id}%"),
        )

        corr_count = cursor2.fetchone()[0]
        print(f"  Correlations: {corr_count}")

        if corr_count == 0:
            print(f"  ❌ NEVER PROCESSED - No correlations found!")
        else:
            # Show the correlations
            cursor3 = conn.execute(
                """
                SELECT handler_name, action_type, status, created_at
                FROM service_correlations
                WHERE request_data LIKE ? OR response_data LIKE ?
                ORDER BY created_at
            """,
                (f"%{thought_id}%", f"%{thought_id}%"),
            )

            for corr in cursor3.fetchall():
                print(f"    - {corr[3]}: {corr[0]} -> {corr[1]} ({corr[2]})")

    # 3. Check what statuses thoughts are created with in the code
    print("\n2. CHECKING THOUGHT CREATION PATTERNS")
    print("-" * 50)

    # Look for thoughts created in last hour with their initial status
    cursor = conn.execute(
        """
        SELECT thought_type, status, COUNT(*) as count
        FROM thoughts
        WHERE datetime(created_at) > datetime('now', '-1 hour')
        GROUP BY thought_type, status
        ORDER BY thought_type, status
    """
    )

    print("\nThoughts created in last hour by type and status:")
    for row in cursor.fetchall():
        print(f"  {row[0]:15} | {row[1]:12} | Count: {row[2]}")

    # 4. Check if there are other PROCESSING thoughts that are stuck
    print("\n3. OTHER STUCK THOUGHTS IN PROCESSING STATUS")
    print("-" * 50)

    cursor = conn.execute(
        """
        SELECT thought_id, thought_type, source_task_id,
               created_at, updated_at
        FROM thoughts
        WHERE status = 'processing'
          AND datetime(created_at) < datetime('now', '-5 minutes')
        ORDER BY created_at DESC
        LIMIT 10
    """
    )

    stuck_thoughts = cursor.fetchall()
    print(f"\nFound {len(stuck_thoughts)} thoughts stuck in PROCESSING for >5 minutes:")

    for thought in stuck_thoughts:
        thought_id = thought[0]
        thought_type = thought[1]
        created = thought[3]
        updated = thought[4]

        # Calculate time stuck
        try:
            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            now_dt = datetime.utcnow()
            stuck_minutes = (now_dt - created_dt).total_seconds() / 60

            print(f"  {thought_id[:8]}... | {thought_type:12} | Stuck for {stuck_minutes:.0f} minutes")

            if created == updated:
                print(f"    ⚠️  Never updated since creation!")
        except:
            print(f"  {thought_id[:8]}... | {thought_type:12} | Unable to calculate time")

    # 5. Check the shutdown task specifically
    print("\n4. SHUTDOWN TASK INVESTIGATION")
    print("-" * 50)

    cursor = conn.execute(
        """
        SELECT task_id, description, status, priority, created_at
        FROM tasks
        WHERE task_id LIKE 'shutdown%'
        ORDER BY created_at DESC
        LIMIT 5
    """
    )

    for task in cursor.fetchall():
        task_id = task[0]
        desc = task[1][:50]
        status = task[2]
        priority = task[3]

        print(f"\nTask: {task_id}")
        print(f"  Description: {desc}...")
        print(f"  Status: {status}")
        print(f"  Priority: {priority}")

        # Get all thoughts for this task
        cursor2 = conn.execute(
            """
            SELECT thought_id, thought_type, status, round_number, created_at
            FROM thoughts
            WHERE source_task_id = ?
            ORDER BY created_at
        """,
            (task_id,),
        )

        thoughts = cursor2.fetchall()
        print(f"  Thoughts ({len(thoughts)}):")

        for t in thoughts:
            marker = ""
            if t[2] == "processing":
                marker = " ⚠️ STUCK"
            elif t[2] == "deferred":
                marker = " 🔄 DEFERRED"
            print(f"    {t[4]} | {t[0][:8]}... | {t[1]:12} | {t[2]:12} | Round {t[3]}{marker}")

    # 6. Check if thoughts with round_number=0 are being processed
    print("\n5. ROUND NUMBER 0 THOUGHTS")
    print("-" * 50)

    cursor = conn.execute(
        """
        SELECT thought_type, status, COUNT(*) as count
        FROM thoughts
        WHERE round_number = 0
        GROUP BY thought_type, status
        ORDER BY thought_type, status
    """
    )

    print("\nThoughts with round_number=0 by type and status:")
    for row in cursor.fetchall():
        print(f"  {row[0]:15} | {row[1]:12} | Count: {row[2]}")

    # 7. Check if there's a pattern with parent thoughts
    print("\n6. PARENT THOUGHT ANALYSIS")
    print("-" * 50)

    cursor = conn.execute(
        """
        SELECT t.thought_id, t.thought_type, t.status,
               p.thought_type as parent_type, p.status as parent_status
        FROM thoughts t
        LEFT JOIN thoughts p ON t.parent_thought_id = p.thought_id
        WHERE t.status = 'processing'
          AND t.parent_thought_id IS NOT NULL
        LIMIT 10
    """
    )

    print("\nThoughts stuck in PROCESSING with parent thoughts:")
    for row in cursor.fetchall():
        print(f"  Child:  {row[0][:8]}... | {row[1]:12} | {row[2]}")
        print(f"  Parent: {row[3]:12} | {row[4]}")
        print()


if __name__ == "__main__":
    investigate_guidance_processing()
