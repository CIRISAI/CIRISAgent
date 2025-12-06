"""
Centralized utilities for thought management.
"""

import uuid
from typing import Optional

from ciris_engine.schemas.runtime.enums import ThoughtType


def generate_thought_id(
    thought_type: ThoughtType,
    task_id: Optional[str] = None,
    parent_thought_id: Optional[str] = None,
    is_seed: bool = False,
) -> str:
    """
    Generate a consistent thought ID with type prefix.

    This ensures all thought IDs follow a consistent pattern that makes
    debugging easier and prevents ID collisions.

    Format:
    - STANDARD (seed): th_seed_{task_id[:8]}_{uuid[:12]}
    - STANDARD (regular): th_std_{uuid}
    - FOLLOW_UP: th_followup_{parent_id[:8]}_{uuid[:12]}
    - PONDER: th_ponder_{uuid}
    - DEFERRED: th_defer_{uuid}
    - OBSERVATION: th_obs_{uuid}
    - MEMORY: th_mem_{uuid}
    - ERROR: th_err_{uuid}
    """
    unique_part = str(uuid.uuid4())

    # Special handling for seed thoughts (which are STANDARD type but initial thoughts)
    if is_seed and task_id:
        # Use 12 characters from UUID to avoid collisions (16^12 = ~281 trillion possibilities)
        return f"th_seed_{task_id[:8]}_{unique_part[:12]}"
    elif thought_type == ThoughtType.FOLLOW_UP and parent_thought_id:
        # Use 12 characters from UUID to avoid collisions
        return f"th_followup_{parent_thought_id[:8]}_{unique_part[:12]}"
    elif thought_type == ThoughtType.PONDER:
        return f"th_ponder_{unique_part}"
    elif thought_type == ThoughtType.DEFERRED:
        return f"th_defer_{unique_part}"
    elif thought_type == ThoughtType.OBSERVATION:
        return f"th_obs_{unique_part}"
    elif thought_type == ThoughtType.MEMORY:
        return f"th_mem_{unique_part}"
    elif thought_type == ThoughtType.ERROR:
        return f"th_err_{unique_part}"
    else:
        # Default for STANDARD
        return f"th_std_{unique_part}"
