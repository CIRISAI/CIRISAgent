"""
Centralized utilities for thought management.
"""

import re
import uuid
from typing import Optional

from ciris_engine.schemas.runtime.enums import ThoughtType

# Every id this module mints starts `th_<type>_`. Stripping it is what makes the
# REST of the id the identifying part.
_TYPE_PREFIX = re.compile(r"^th_[a-z]+_")


def _parent_discriminator(parent_thought_id: str) -> str:
    """The identifying bits of a parent id, for embedding in a child's id.

    `parent_thought_id[:8]` was used here directly, and for a seed parent it
    returned the literal string "th_seed_" — exactly 8 characters of type
    prefix and ZERO identity. Every follow-up of every seed was therefore named
    `th_followup_th_seed__<uuid12>` (note the double underscore: an empty field
    between two separators), so the id said only "the parent was a seed" and
    could not name WHICH seed.

    The seed branch uses the same `[:8]` idiom on `task_id`, which is a bare
    UUID with no prefix, so it is correct there. Same operation, two
    differently-shaped inputs — right for one, vacuous for the other.

    Nothing broke: linkage rides on `task_id`, which is intact, so the causal
    graph in the data is complete. What broke is reading it — searching the
    canonical for a follow-up by its parent's id can never match, because the
    parent's id is not in there.
    """
    stripped = _TYPE_PREFIX.sub("", parent_thought_id, count=1)
    # A parent id that is nothing but a type prefix would put us right back to an
    # empty discriminator; prefer the raw id over silently emitting nothing.
    return (stripped or parent_thought_id)[:8]


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
    - FOLLOW_UP: th_followup_{parent_discriminator}_{uuid[:12]}
      where parent_discriminator is 8 chars of the parent id AFTER its
      `th_<type>_` prefix — see _parent_discriminator for why the prefix must
      go first.
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
        return f"th_followup_{_parent_discriminator(parent_thought_id)}_{unique_part[:12]}"
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
