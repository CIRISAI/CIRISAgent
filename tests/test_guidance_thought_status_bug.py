"""
Simple test to validate the guidance thought status bug is fixed.

BUG: Guidance thoughts were being created with status=PROCESSING instead of PENDING,
causing them to never enter the processing queue and get stuck forever.

FIX: Guidance thoughts must be created with status=PENDING so they can be picked up
by the normal thought processing pipeline.
"""

import ast
from pathlib import Path

import pytest


def test_guidance_thoughts_created_with_pending_status():
    """Test that guidance thoughts are created with PENDING status in the code."""
    # Read the discord_observer.py file and check the status assignment
    observer_path = Path(__file__).parent.parent / "ciris_engine/logic/adapters/discord/discord_observer.py"
    if not observer_path.exists():
        pytest.skip("Discord observer file not found")

    with open(observer_path, "r") as f:
        content = f.read()
        tree = ast.parse(content)

    # Find all Thought() instantiations
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "Thought":
                # Check if this is a guidance thought
                is_guidance = False
                status_value = None

                for keyword in node.keywords:
                    if keyword.arg == "thought_type":
                        if isinstance(keyword.value, ast.Attribute) and keyword.value.attr == "GUIDANCE":
                            is_guidance = True
                    elif keyword.arg == "status":
                        if isinstance(keyword.value, ast.Attribute):
                            status_value = keyword.value.attr

                # If it's a guidance thought, check its status
                if is_guidance:
                    assert status_value == "PENDING", (
                        f"Found guidance thought being created with status {status_value}! "
                        f"This is the bug that causes guidance thoughts to get stuck. "
                        f"Guidance thoughts must be created with status=PENDING."
                    )


def test_thought_manager_only_processes_pending_thoughts():
    """Test that ThoughtManager's populate_queue only fetches PENDING thoughts."""
    manager_path = Path(__file__).parent.parent / "ciris_engine/logic/processors/support/thought_manager.py"
    if not manager_path.exists():
        pytest.skip("ThoughtManager file not found")

    with open(manager_path, "r") as f:
        content = f.read()

    # Check that populate_queue calls get_pending_thoughts_for_active_tasks
    assert (
        "get_pending_thoughts_for_active_tasks" in content
    ), "ThoughtManager.populate_queue must call get_pending_thoughts_for_active_tasks"

    # Verify the line exists in populate_queue method
    lines = content.split("\n")
    in_populate_queue = False
    found_pending_call = False

    for line in lines:
        if "def populate_queue" in line:
            in_populate_queue = True
        elif in_populate_queue and "def " in line and "populate_queue" not in line:
            # We've left the method
            break
        elif in_populate_queue and "get_pending_thoughts_for_active_tasks" in line:
            found_pending_call = True
            break

    assert found_pending_call, (
        "populate_queue method must call get_pending_thoughts_for_active_tasks " "to fetch only PENDING thoughts"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
