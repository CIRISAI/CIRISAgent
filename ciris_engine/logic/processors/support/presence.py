from datetime import datetime, timedelta
from typing import Optional, Dict

class PresenceTracker:
    """
    Computes a presence score based on recent human interaction.
    Example signals: last WA response, thought delay, discussion intensity.
    """

    def __init__(self, wa_last_response_time: Optional[datetime], thoughts_per_hour: int):
        self.wa_last_response_time = wa_last_response_time
        self.thoughts_per_hour = thoughts_per_hour

    def compute_score(self, current_time: Optional[datetime] = None) -> float:
        if current_time is None:
            current_time = datetime.utcnow()

        # Score degrades the longer WAs are silent
        time_score = 1.0
        if self.wa_last_response_time:
            delta = current_time - self.wa_last_response_time
            minutes_passed = delta.total_seconds() / 60
            time_score = max(0.0, 1.0 - (minutes_passed / 120))  # full presence up to 2 hours

        # Score increases if thoughts are flowing
        activity_score = min(1.0, self.thoughts_per_hour / 10.0)  # full score if >10 t/h

        return round((time_score + activity_score) / 2, 2)
