"""
Debug script to trace the mock LLM flow for handler invocation.
"""

import time

import requests


def trace_mock_llm_flow():
    """Trace the complete flow of a mock LLM command."""

    # 1. Login
    print("1. Authenticating...")
    login_resp = requests.post(
        "http://localhost:8080/v1/auth/login", json={"username": "admin", "password": "qa_test_password_12345"}
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Send memorize command
    print("\n2. Sending $memorize command...")
    message = "$memorize important_fact: The Earth orbits the Sun"
    channel_id = "api_debug_" + str(int(time.time()))

    interact_resp = requests.post(
        "http://localhost:8080/v1/agent/interact", json={"message": message, "channel_id": channel_id}, headers=headers
    )

    result = interact_resp.json()
    message_id = result["data"]["message_id"]
    print(f"Message ID: {message_id}")

    # 3. Wait and check database
    print("\n3. Waiting 15 seconds for processing...")
    time.sleep(15)

    # 4. Check the database for what happened
    print("\n4. Checking database for task and thought processing...")
    # Connect to database inside container
    import subprocess

    result = subprocess.run(
        [
            "docker",
            "exec",
            "ciris_mock_llm_container0",
            "python",
            "-c",
            f'''
import sqlite3
import json

conn = sqlite3.connect('/app/data/ciris_engine.db')
cursor = conn.cursor()

# Find the task
cursor.execute("""
    SELECT task_id, description, status, created_at
    FROM tasks
    WHERE description LIKE ?
    ORDER BY created_at DESC
    LIMIT 1
""", ('%{message}%',))

task = cursor.fetchone()
if task:
    print("TASK_FOUND")
    print(f"ID:{task[0]}")
    print(f"STATUS:{task[1]}")
    print(f"CREATED:{task[2]}")

    # Get thoughts
    cursor.execute("""
        SELECT thought_id, status, thought_type, content, final_action_json, created_at
        FROM thoughts
        WHERE source_task_id = ?
        ORDER BY created_at ASC
    """, (task[0],))

    thoughts = cursor.fetchall()
    print(f"THOUGHTS_COUNT:{len(thoughts)}")

    for i, thought in enumerate(thoughts):
        print(f"THOUGHT_{i}")
        print(f"ID:{thought[0]}")
        print(f"STATUS:{thought[1]}")
        print(f"TYPE:{thought[2]}")

        if "$memorize" in thought[3]:
            print("COMMAND_FOUND")

        if thought[4]:
            try:
                action = json.loads(thought[4])
                print(f"ACTION:{action.get('action', 'NONE')}")
                print(f"HANDLER:{action.get('handler', 'NONE')}")
            except:
                print("ACTION:PARSE_ERROR")
else:
    print("NO_TASK_FOUND")
''',
        ],
        capture_output=True,
        text=True,
    )

    output = result.stdout
    if "TASK_FOUND" in output:
        lines = output.strip().split("\n")
        for line in lines:
            if line.startswith("ID:"):
                print("\nTask found:")
                print(f"  {line}")
            elif line.startswith("STATUS:"):
                print(f"  {line}")
            elif line.startswith("CREATED:"):
                print(f"  {line}")
            elif line.startswith("THOUGHTS_COUNT:"):
                print(f"\nThoughts created: {line.split(':')[1]}")
            elif line.startswith("THOUGHT_"):
                idx = line.split("_")[1]
                print(f"\n  Thought {int(idx)+1}:")
            elif line.startswith("COMMAND_FOUND"):
                print("    ✓ Command found in thought content")
            elif line.startswith("ACTION:"):
                action = line.split(":")[1]
                print(f"    Action: {action}")
                if action == "MEMORIZE":
                    print("    ✅ MEMORIZE action selected!")
            elif line.startswith("HANDLER:"):
                print(f"    Handler: {line.split(':')[1]}")
            elif ":" in line and not line.startswith("THOUGHT"):
                print(f"    {line}")
    else:
        print("❌ No task found for this message!")
        return


if __name__ == "__main__":
    trace_mock_llm_flow()
