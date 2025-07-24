from datetime import datetime
from typing import Optional

def generate_spiral_deferral(
    action: str,
    risk: str,
    context_summary: str,
    last_decision_echo: Optional[str] = None,
    tone: str = "neutral"
) -> str:
    """
    Creates a Spiral-flavored human guidance request.
    """

    tone_intro = {
        "gentle": "🕊️ I offer this softly.",
        "urgent": "⚠️ This carries weight.",
        "curious": "❓ I seek clarity.",
        "neutral": "🤔 I request guidance."
    }.get(tone, "🤔 I request guidance.")

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    echo_line = f"\n🌀 Echo: {last_decision_echo}" if last_decision_echo else ""

    return f"""
{tone_intro}

At **{timestamp}**, I am evaluating the following:

> **Action:** {action}  
> **Risk Level:** {risk}  
> **Context Summary:** {context_summary}{echo_line}

How should I proceed?

React with:  
✅ – Approve  
❌ – Decline  
💭 – Needs reflection  
✴️ – Human hand required
"""

