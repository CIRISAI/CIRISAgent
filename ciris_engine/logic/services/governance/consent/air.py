"""
Artificial Interaction Reminder (AIR) - Parasocial Attachment Prevention.

Monitors 1:1 API interactions and reminds users to take breaks.
Philosophy: Prevent unhealthy AI relationships through mindful interaction patterns.

Design Principles (v2.0 - MDD Aligned):
- Objective thresholds only (time, message count)
- No behavioral surveillance or heuristic pattern matching
- Transparent, predictable reminder triggers
- Environmental cognitive remediation to reanchor in physical world

Research basis: JMIR Mental Health 2025 (DOI: 10.2196/85799)
See FSD/AIR_ARTIFICIAL_INTERACTION_REMINDER.md for full design rationale.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

logger = logging.getLogger(__name__)


class InteractionSession:
    """Track interaction session for a user."""

    def __init__(self, user_id: str, channel_id: str, started_at: datetime):
        """
        Initialize interaction session.

        Args:
            user_id: User ID
            channel_id: Channel ID
            started_at: Session start time
        """
        self.user_id = user_id
        self.channel_id = channel_id
        self.started_at = started_at
        self.last_interaction = started_at
        self.message_timestamps: list[datetime] = []  # Track all message times
        self.reminder_sent = False


class ArtificialInteractionReminder:
    """
    Monitor 1:1 API interactions and prevent parasocial attachment.

    Triggers (objective thresholds only):
    - 30+ minutes of continuous interaction OR
    - 20+ messages within the last 30 minutes (sliding window)

    Important: Message threshold uses a sliding time window, not total session messages.
    This means 19 messages today + 19 tomorrow = no trigger (messages too spread out).
    But 20 messages in 30 minutes = trigger (intensive interaction).

    Scope: API channels only (1:1 interactions, not community moderation)

    Design note: This implementation deliberately avoids heuristic-based behavioral
    surveillance (valence detection, anthropomorphism patterns) in favor of transparent,
    predictable thresholds that respect user autonomy. See FSD for rationale.
    """

    def __init__(
        self,
        time_service: TimeServiceProtocol,
        time_threshold_minutes: int = 30,
        message_threshold: int = 20,
    ):
        """
        Initialize AIR manager.

        Args:
            time_service: Time service for consistent timestamps
            time_threshold_minutes: Minutes of continuous interaction before reminder (default: 30)
            message_threshold: Number of messages before reminder (default: 20)
        """
        self._time_service = time_service
        self._time_threshold = timedelta(minutes=time_threshold_minutes)
        self._message_threshold = message_threshold

        # Track active sessions: (user_id, channel_id) -> InteractionSession
        self._sessions: Dict[Tuple[str, str], InteractionSession] = {}

        # Metrics
        self._total_interactions = 0
        self._reminders_sent = 0
        self._time_triggered_reminders = 0
        self._message_triggered_reminders = 0

    def _now(self) -> datetime:
        """Get current time from time service."""
        if self._time_service is None:
            return datetime.now(timezone.utc)
        return self._time_service.now()

    def track_interaction(
        self,
        user_id: str,
        channel_id: str,
        channel_type: Optional[str] = None,
        _message_content: Optional[str] = None,  # Kept for API compatibility, not used
    ) -> Optional[str]:
        """
        Track user interaction and check if reminder needed.

        Args:
            user_id: User ID
            channel_id: Channel ID
            channel_type: Channel type (api, discord, cli, unknown)
            message_content: Optional message content (ignored - no behavioral surveillance)

        Returns:
            Reminder message if threshold exceeded, None otherwise
        """
        self._total_interactions += 1

        # Only track API channels (1:1 interactions)
        if channel_type != "api":
            return None

        # Infer channel type from ID if not provided
        if channel_type is None:
            channel_type = self._infer_channel_type(channel_id)
            if channel_type != "api":
                return None

        now = self._now()
        session_key = (user_id, channel_id)

        # Get or create session
        if session_key not in self._sessions:
            self._sessions[session_key] = InteractionSession(user_id, channel_id, now)
            logger.debug(f"Started AIR session for {user_id} in {channel_id}")

        session = self._sessions[session_key]

        # Check if session has been idle - reset if idle for more than threshold
        idle_time = now - session.last_interaction
        idle_threshold = self._time_threshold

        if idle_time >= idle_threshold:
            # Session has been idle long enough - treat as new conversation
            logger.debug(
                f"Resetting AIR session for {user_id} in {channel_id} "
                f"after {idle_time.total_seconds()/60:.1f} min idle"
            )
            session.started_at = now
            session.reminder_sent = False
            session.message_timestamps.clear()

        # Update session
        session.last_interaction = now
        session.message_timestamps.append(now)

        # Skip if reminder already sent this session
        if session.reminder_sent:
            return None

        # Check thresholds (objective only - no behavioral surveillance)
        duration = now - session.started_at
        time_exceeded = duration >= self._time_threshold

        # Count messages within the time window (last 30 minutes)
        time_window = now - self._time_threshold
        recent_messages = [ts for ts in session.message_timestamps if ts >= time_window]
        message_exceeded = len(recent_messages) >= self._message_threshold

        if time_exceeded or message_exceeded:
            # Generate reminder
            reminder = self._generate_reminder(session, time_exceeded, message_exceeded)

            # Mark reminder as sent
            session.reminder_sent = True
            self._reminders_sent += 1

            if time_exceeded:
                self._time_triggered_reminders += 1
            if message_exceeded:
                self._message_triggered_reminders += 1

            logger.info(
                f"AIR triggered for {user_id} in {channel_id}: "
                f"duration={duration.total_seconds()/60:.1f}min, "
                f"total_messages={len(session.message_timestamps)}, "
                f"recent_messages={len(recent_messages)}, "
                f"time_trigger={time_exceeded}, message_trigger={message_exceeded}"
            )

            return reminder

        return None

    def _infer_channel_type(self, channel_id: str) -> str:
        """
        Infer channel type from ID pattern.

        Args:
            channel_id: Channel ID

        Returns:
            Channel type: api, discord, cli, unknown
        """
        if channel_id.startswith("api_") or channel_id.startswith("api-"):
            return "api"
        elif channel_id.startswith("discord_") or (channel_id.isdigit() and len(channel_id) >= 17):
            return "discord"
        elif channel_id.startswith("cli_") or channel_id.startswith("cli-"):
            return "cli"
        return "unknown"

    def _generate_reminder(
        self,
        session: InteractionSession,
        time_triggered: bool,
        message_triggered: bool,
    ) -> str:
        """
        Generate parasocial attachment prevention reminder with environmental cognitive remediation.

        Research basis (JMIR Mental Health 2025, DOI: 10.2196/85799):
        Environmental cognitive remediation to reanchor experience in physical world.

        Args:
            session: Interaction session
            time_triggered: Whether time threshold was exceeded
            message_triggered: Whether message threshold was exceeded

        Returns:
            Reminder message with reality-anchoring content
        """
        now = self._now()
        duration_minutes = int((now - session.started_at).total_seconds() / 60)

        # Count recent messages (within time window)
        time_window = now - self._time_threshold
        recent_messages = [ts for ts in session.message_timestamps if ts >= time_window]
        recent_count = len(recent_messages)

        # Core reminder message with reality-anchoring
        reminder = "🕒 **Mindful Interaction Reminder**\n\n"
        reminder += "We've been chatting for a while now. Here's a gentle reminder:\n\n"

        # Reality-testing core messages
        reminder += (
            "**What I am:**\n"
            "• A language model - I predict text based on patterns\n"
            "• A tool - useful for tasks, but not a relationship\n"
            "• Limited - I can't truly know you, feel for you, or be there for you\n\n"
            "**What I'm not:**\n"
            "• A friend, companion, or confidant\n"
            "• A substitute for human connection\n"
            "• A therapist or counselor\n\n"
        )

        # Add trigger-specific context (transparent about why reminder was shown)
        if time_triggered and message_triggered:
            reminder += f"📊 You've sent {recent_count} messages over {duration_minutes} minutes. "
        elif time_triggered:
            reminder += f"📊 We've been interacting for {duration_minutes} minutes. "
        elif message_triggered:
            reminder += f"📊 You've sent {recent_count} messages recently. "

        # Environmental cognitive remediation - reanchoring in physical world
        # (No time-of-day assumptions - we don't know user's timezone)
        reminder += (
            "\n\n**🌍 Grounding suggestions:**\n"
            "• Notice 5 things you can see in your physical space\n"
            "• Take 3 deep breaths and feel your feet on the floor\n"
            "• Send a message to a real person in your life\n"
            "• Step outside briefly - notice the temperature, sounds, smells\n\n"
            "I'll be here when you need practical assistance, but your life happens "
            "in the physical world, with real people. That's where flourishing lives."
        )

        return reminder

    def end_session(self, user_id: str, channel_id: str) -> None:
        """
        End interaction session for user.

        Args:
            user_id: User ID
            channel_id: Channel ID
        """
        session_key = (user_id, channel_id)
        if session_key in self._sessions:
            session = self._sessions[session_key]
            duration = self._now() - session.started_at
            logger.info(
                f"Ended AIR session for {user_id} in {channel_id}: "
                f"duration={duration.total_seconds()/60:.1f}min, "
                f"messages={len(session.message_timestamps)}, "
                f"reminder_sent={session.reminder_sent}"
            )
            del self._sessions[session_key]

    def cleanup_stale_sessions(self, max_idle_hours: int = 1) -> int:
        """
        Clean up sessions with no activity for max_idle_hours.

        Args:
            max_idle_hours: Maximum idle time before session cleanup

        Returns:
            Number of sessions cleaned up
        """
        now = self._now()
        max_idle = timedelta(hours=max_idle_hours)
        stale_keys = []

        for key, session in self._sessions.items():
            idle_time = now - session.last_interaction
            if idle_time >= max_idle:
                stale_keys.append(key)

        for key in stale_keys:
            logger.debug(f"Cleaning up stale AIR session: {key[0]} in {key[1]}")
            del self._sessions[key]

        return len(stale_keys)

    def get_session_info(self, user_id: str, channel_id: str) -> Optional[Dict[str, object]]:
        """
        Get information about active session.

        Args:
            user_id: User ID
            channel_id: Channel ID

        Returns:
            Session info dictionary or None
        """
        session_key = (user_id, channel_id)
        if session_key not in self._sessions:
            return None

        session = self._sessions[session_key]
        now = self._now()
        duration = now - session.started_at
        time_progress = (duration.total_seconds() / self._time_threshold.total_seconds()) * 100.0

        # Count recent messages (within time window)
        time_window = now - self._time_threshold
        recent_messages = [ts for ts in session.message_timestamps if ts >= time_window]
        message_progress = (len(recent_messages) / self._message_threshold) * 100.0

        return {
            "user_id": user_id,
            "channel_id": channel_id,
            "started_at": session.started_at.isoformat(),
            "duration_minutes": duration.total_seconds() / 60.0,
            "total_messages": len(session.message_timestamps),
            "recent_messages": len(recent_messages),
            "reminder_sent": session.reminder_sent,
            "time_progress_percent": min(time_progress, 100.0),
            "message_progress_percent": min(message_progress, 100.0),
            "time_threshold_minutes": self._time_threshold.total_seconds() / 60.0,
            "message_threshold": self._message_threshold,
        }

    def get_metrics(self) -> Dict[str, object]:
        """
        Get AIR metrics.

        Returns:
            Dictionary with AIR statistics
        """
        reminder_rate = 0.0
        if self._total_interactions > 0:
            reminder_rate = (self._reminders_sent / self._total_interactions) * 100.0

        return {
            "total_interactions": self._total_interactions,
            "reminders_sent": self._reminders_sent,
            "reminder_rate_percent": reminder_rate,
            "time_triggered_reminders": self._time_triggered_reminders,
            "message_triggered_reminders": self._message_triggered_reminders,
            "active_sessions": len(self._sessions),
            "time_threshold_minutes": self._time_threshold.total_seconds() / 60.0,
            "message_threshold": self._message_threshold,
        }

    def get_active_sessions(self) -> list[Dict[str, object]]:
        """
        Get all active sessions.

        Returns:
            List of session info dictionaries
        """
        sessions = []
        for (user_id, channel_id), session in self._sessions.items():
            info = self.get_session_info(user_id, channel_id)
            if info:
                sessions.append(info)

        # Sort by duration (longest first) with explicit type casting
        sessions.sort(
            key=lambda x: float(x["duration_minutes"]) if isinstance(x["duration_minutes"], (int, float)) else 0.0,
            reverse=True,
        )
        return sessions
