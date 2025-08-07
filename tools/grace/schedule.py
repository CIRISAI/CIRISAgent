"""
Your actual daily schedule and transitions.
Simple, honest, based on real life.
"""

from datetime import datetime
from typing import Optional, Tuple

# Your actual work sessions
SESSIONS = {
    "morning": (7, 10),  # Peak creative time
    "midday": (12, 14),  # Good for reviews/fixes
    "evening": (17, 19),  # Mechanical tasks
    "night": (22, 24),  # Deep work (optional)
}

# Natural transition points
TRANSITIONS = {
    10: "break - kids/life",
    14: "break - post-lunch rest",
    17: "evening work block",
    19: "family - dinner/bath/bedtime",
    22: "choice point - rest or code?",
}


def get_current_session() -> Optional[str]:
    """What session are we in right now?"""
    hour = datetime.now().hour
    for session_name, (start, end) in SESSIONS.items():
        if start <= hour < end:
            return session_name
    return None


def get_next_transition() -> Tuple[int, str]:
    """When is the next transition?"""
    hour = datetime.now().hour
    for transition_hour in sorted(TRANSITIONS.keys()):
        if transition_hour > hour:
            return transition_hour, TRANSITIONS[transition_hour]
    # Next day's first transition
    first_hour = min(TRANSITIONS.keys())
    return first_hour, TRANSITIONS[first_hour]


# Removed get_remaining_time() - Anti-Goodhart Pattern
# Counting down hours creates anxiety and rush
# Better to focus on session rhythm than minute tracking
# "The clock is a poor proxy for productivity"
