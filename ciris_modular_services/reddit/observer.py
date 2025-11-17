"""Passive observation support for the Reddit adapter."""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import uuid4

import httpx

from ciris_engine.logic.adapters.base_observer import BaseObserver, detect_and_replace_spoofed_markers
from ciris_engine.logic.buses import BusManager
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.types import JSONDict

from .error_handler import RedditErrorHandler
from .schemas import RedditChannelReference, RedditChannelType, RedditCredentials, RedditMessage
from .service import RedditAPIClient

logger = logging.getLogger(__name__)

_PASSIVE_LIMIT = 25
_CACHE_LIMIT = 500


class RedditObserver(BaseObserver[RedditMessage]):
    """Observer that converts Reddit activity into passive observations."""

    def __init__(
        self,
        *,
        credentials: Optional[RedditCredentials] = None,
        subreddit: Optional[str] = None,
        poll_interval: float = 15.0,
        bus_manager: Optional[BusManager] = None,
        memory_service: Optional[object] = None,
        agent_id: Optional[str] = None,
        filter_service: Optional[object] = None,
        secrets_service: Optional[SecretsService] = None,
        time_service: Optional[TimeServiceProtocol] = None,
        agent_occurrence_id: str = "default",
    ) -> None:
        creds = credentials or RedditCredentials.from_env()
        if not creds:
            raise RuntimeError("RedditObserver requires credentials")

        self._subreddit = RedditChannelReference._normalize_subreddit(subreddit or creds.subreddit)
        self._poll_interval = max(poll_interval, 5.0)
        self._api_client = RedditAPIClient(creds, time_service=time_service)

        super().__init__(
            on_observe=lambda _: asyncio.sleep(0),
            bus_manager=bus_manager,
            memory_service=memory_service,
            agent_id=agent_id,
            filter_service=filter_service,
            secrets_service=secrets_service,
            time_service=time_service,
            agent_occurrence_id=agent_occurrence_id,
            origin_service="reddit",
        )

        self._poll_task: Optional[asyncio.Task[None]] = None
        self._seen_posts: "OrderedDict[str, None]" = OrderedDict()
        self._seen_comments: "OrderedDict[str, None]" = OrderedDict()
        self._error_handler = RedditErrorHandler()
        self._consecutive_errors = 0
        self._max_consecutive_errors = 5
        self._startup_timestamp: Optional[datetime] = None  # Only process content created after this
        logger.info("RedditObserver configured for r/%s", self._subreddit)

    def _is_agent_message(self, msg: RedditMessage) -> bool:
        """
        Override BaseObserver to check against Reddit username, not CIRIS agent_id.

        BaseObserver compares msg.author_id against self.agent_id (CIRIS agent ID),
        but for Reddit, msg.author_id is the Reddit username (e.g., "CIRIS-Scout").
        We need to compare against the Reddit credentials username to prevent
        the agent from replying to its own messages.
        """
        return msg.author_id == self._api_client._credentials.username

    # ------------------------------------------------------------------
    async def start(self) -> None:
        await self._api_client.start()
        # Record startup time - only process content created after this point
        # Use 60s grace period to avoid missing content that's "in flight"
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        self._startup_timestamp = now - timedelta(seconds=60)
        logger.info(
            f"RedditObserver started - will only process content created after {self._startup_timestamp.isoformat()}"
        )
        self._poll_task = asyncio.create_task(self._poll_loop(), name="reddit-observer-poll")

    async def stop(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        await self._api_client.stop()
        logger.info("RedditObserver stopped")

    # ------------------------------------------------------------------
    async def _poll_loop(self) -> None:
        """Poll subreddit with robust error handling and exponential backoff."""
        try:
            while True:
                try:
                    # Poll subreddit with retry logic
                    await self._error_handler.retry_with_backoff(
                        operation=self._poll_subreddit,
                        max_retries=3,
                        base_delay=1.0,
                        max_delay=30.0,
                        operation_name="poll_subreddit",
                    )
                    # Reset consecutive error count on success
                    self._consecutive_errors = 0

                except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError, httpx.ConnectError) as exc:
                    # Network-level errors with circuit breaker
                    self._consecutive_errors += 1
                    error_info = self._error_handler.classify_error(exc, "poll_subreddit")

                    if self._consecutive_errors >= self._max_consecutive_errors:
                        logger.error(
                            f"Max consecutive network errors reached ({self._consecutive_errors}), "
                            "stopping observer to prevent resource exhaustion"
                        )
                        break

                    # Exponential backoff with circuit breaker
                    backoff = min(5 * (2 ** (self._consecutive_errors - 1)), 60)
                    logger.warning(
                        f"Network error (attempt {self._consecutive_errors}/{self._max_consecutive_errors}): "
                        f"{error_info.message}, backing off for {backoff}s"
                    )
                    await asyncio.sleep(backoff)
                    continue

                except Exception as exc:
                    # Unexpected errors - log and continue with backoff
                    self._consecutive_errors += 1
                    logger.exception(f"Unexpected poll error (count: {self._consecutive_errors}): {exc}")

                    if self._consecutive_errors >= self._max_consecutive_errors:
                        logger.error("Too many consecutive errors, stopping observer")
                        break

                    await asyncio.sleep(min(self._poll_interval * 2, 60))
                    continue

                # Normal sleep before next poll
                await asyncio.sleep(self._poll_interval)

        except asyncio.CancelledError:
            logger.debug("RedditObserver poll loop cancelled")
            raise
        except Exception as exc:
            logger.critical(f"RedditObserver poll loop fatal error: {exc}", exc_info=True)

    async def _poll_subreddit(self) -> None:
        posts = await self._api_client.fetch_subreddit_new(self._subreddit, limit=_PASSIVE_LIMIT)
        for entry in posts:
            if self._mark_seen(self._seen_posts, entry.item_id):
                continue
            # CRITICAL: Only process content created after startup (prevent historical backfill)
            if self._startup_timestamp and entry.created_at < self._startup_timestamp:
                logger.debug(
                    f"Reddit post {entry.item_id} created before startup "
                    f"({entry.created_at.isoformat()} < {self._startup_timestamp.isoformat()}), skipping"
                )
                continue
            # Check persistent storage for existing task with this correlation_id
            if await self._already_handled(entry.item_id):
                logger.debug(f"Reddit post {entry.item_id} already handled (found in task database), skipping")
                continue
            message = self._build_message_from_entry(entry)
            await self.handle_incoming_message(message)

        comments = await self._api_client.fetch_subreddit_comments(self._subreddit, limit=_PASSIVE_LIMIT)
        for entry in comments:
            if self._mark_seen(self._seen_comments, entry.item_id):
                continue
            # CRITICAL: Only process content created after startup (prevent historical backfill)
            if self._startup_timestamp and entry.created_at < self._startup_timestamp:
                logger.debug(
                    f"Reddit comment {entry.item_id} created before startup "
                    f"({entry.created_at.isoformat()} < {self._startup_timestamp.isoformat()}), skipping"
                )
                continue
            # Check persistent storage for existing task with this correlation_id
            if await self._already_handled(entry.item_id):
                logger.debug(f"Reddit comment {entry.item_id} already handled (found in task database), skipping")
                continue
            # CRITICAL: Only process comments that are replies to Scout's own comments/posts
            if not await self._is_reply_to_scout(entry):
                logger.debug(f"Reddit comment {entry.item_id} is not a reply to Scout's content, skipping observation")
                continue
            message = self._build_message_from_entry(entry)
            await self.handle_incoming_message(message)

    def _mark_seen(self, cache: "OrderedDict[str, None]", key: str) -> bool:
        if key in cache:
            return True
        cache[key] = None
        while len(cache) > _CACHE_LIMIT:
            cache.popitem(last=False)
        return False

    async def _already_handled(self, reddit_item_id: str) -> bool:
        """
        Check if a Reddit post/comment has already been handled.

        This queries the task database for any task with this correlation_id,
        preventing re-processing of content after restart.

        Args:
            reddit_item_id: The Reddit post/comment ID

        Returns:
            True if already handled, False otherwise
        """
        try:
            from ciris_engine.logic.persistence.models.tasks import get_task_by_correlation_id

            # Query tasks table for this correlation_id
            existing_task = get_task_by_correlation_id(reddit_item_id, self.agent_occurrence_id)
            if existing_task:
                logger.debug(
                    f"Found existing task {existing_task.task_id} for Reddit item {reddit_item_id}, "
                    f"status={existing_task.status.value}"
                )
                return True
            return False
        except Exception as exc:
            # If database query fails, log error but don't block processing
            # (fail open - better to potentially re-process than miss content)
            logger.warning(f"Failed to check if Reddit item {reddit_item_id} already handled: {exc}")
            return False

    async def _is_reply_to_scout(self, entry: object) -> bool:
        """
        Check if a comment is a reply to Scout's own comment or post.

        Args:
            entry: RedditTimelineEntry for a comment

        Returns:
            True if parent was authored by Scout, False otherwise
        """
        # Must be a comment with a parent_id
        if not hasattr(entry, "entry_type") or not hasattr(entry, "parent_id"):
            return False
        if entry.entry_type != "comment" or not entry.parent_id:
            return False

        try:
            # Fetch parent item metadata to check author
            parent_response = await self._api_client._request("GET", f"/api/info", params={"id": entry.parent_id})
            if parent_response.status_code >= 300:
                item_id = entry.item_id if hasattr(entry, "item_id") else "unknown"
                parent_id_str = entry.parent_id if hasattr(entry, "parent_id") else "unknown"
                logger.warning(
                    f"Failed to fetch parent {parent_id_str} for comment {item_id}: "
                    f"status={parent_response.status_code}"
                )
                return False

            parent_data = parent_response.json()
            if not isinstance(parent_data, dict):
                return False

            # Navigate Reddit API response structure: data -> children -> [0] -> data -> author
            data = parent_data.get("data", {})
            children = data.get("children", [])
            if not children or not isinstance(children[0], dict):
                return False

            parent_author = children[0].get("data", {}).get("author")
            scout_username = self._api_client._credentials.username

            # Check if parent was authored by Scout
            is_scouts_content = parent_author == scout_username
            if is_scouts_content:
                item_id = entry.item_id if hasattr(entry, "item_id") else "unknown"
                parent_id_str = entry.parent_id if hasattr(entry, "parent_id") else "unknown"
                logger.debug(
                    f"Comment {item_id} is a reply to Scout's {parent_id_str} " f"(parent_author={parent_author})"
                )
            return bool(is_scouts_content)

        except Exception as exc:
            item_id = entry.item_id if hasattr(entry, "item_id") else "unknown"
            logger.warning(f"Error checking if comment {item_id} is reply to Scout: {exc}")
            # Fail closed - if we can't verify, don't create observation
            return False

    def _build_message_from_entry(self, entry: Any) -> RedditMessage:
        content = entry.title or entry.body or "(no content)"
        if entry.entry_type == "submission" and entry.body:
            content = f"{entry.title}\n\n{entry.body}" if entry.title else entry.body

        reference = RedditChannelReference.parse(entry.channel_reference)
        submission_id = reference.submission_id if reference.submission_id else entry.item_id
        comment_id = reference.comment_id if reference.target is RedditChannelType.COMMENT else None

        return RedditMessage(
            message_id=entry.item_id,
            author_id=entry.author or "unknown",
            author_name=entry.author or "Unknown",
            content=content,
            channel_id=entry.channel_reference,
            channel_reference=entry.channel_reference,
            permalink=entry.permalink,
            subreddit=self._subreddit,
            submission_id=submission_id,
            comment_id=comment_id,
            timestamp=entry.created_at.isoformat(),
        )

    async def _should_process_message(self, msg: RedditMessage) -> bool:
        if not msg.channel_reference:
            return False
        try:
            reference = RedditChannelReference.parse(msg.channel_reference)
        except ValueError:
            return False
        if reference.target == RedditChannelType.USER:
            return False
        if reference.subreddit and reference.subreddit.lower() != self._subreddit.lower():
            return False
        return True

    async def _enhance_message(self, msg: RedditMessage) -> RedditMessage:
        """Apply Reddit-specific content hardening before processing."""

        cleaned = detect_and_replace_spoofed_markers(msg.content)
        if cleaned != msg.content:
            msg.content = cleaned

        # Surface permalink metadata for downstream context builders
        if msg.permalink:
            setattr(msg, "permalink_url", msg.permalink)

        return msg

    async def _add_custom_context_sections(
        self, task_lines: List[str], msg: RedditMessage, history_context: List[JSONDict]
    ) -> None:
        """
        Add Reddit-specific context sections: thread comments and recent subreddit posts.

        Similar to Discord's ACTIVE MODS section, this provides Reddit-specific context
        for better understanding of the conversation and subreddit activity.

        Args:
            task_lines: List of strings to append context to
            msg: RedditMessage being processed
            history_context: Existing conversation history (unused, but required by interface)
        """
        try:
            # Add thread context if this is a comment on a submission
            if msg.submission_id:
                await self._add_thread_context(task_lines, msg.submission_id, msg.comment_id)

            # Add recent subreddit activity
            if msg.subreddit:
                await self._add_recent_posts_context(task_lines, msg.subreddit)

        except Exception as exc:
            logger.warning(f"Failed to add Reddit custom context: {exc}")
            # Add a note about missing context but continue processing
            task_lines.append("\n=== REDDIT CONTEXT ===")
            task_lines.append(f"(Context fetch failed: {str(exc)})")
            task_lines.append("=== END REDDIT CONTEXT ===")

    async def _add_thread_context(
        self, task_lines: List[str], submission_id: str, current_comment_id: Optional[str]
    ) -> None:
        """Add other comments from the same Reddit post thread."""
        try:
            comments = await self._api_client.fetch_submission_comments(submission_id, limit=10)

            if comments:
                task_lines.append("\n=== THREAD CONTEXT (Other replies on this post) ===")
                comment_count = 0
                for comment in comments:
                    # Skip the current comment to avoid duplication
                    if comment.comment_id == current_comment_id:
                        continue

                    # Format: Author | Score | Body (truncated)
                    body_preview = comment.body[:150] + "..." if len(comment.body) > 150 else comment.body
                    task_lines.append(f"@{comment.author} ({comment.score} pts): {body_preview}")
                    comment_count += 1

                    if comment_count >= 5:  # Limit to 5 other comments to avoid context bloat
                        break

                if comment_count == 0:
                    task_lines.append("(No other comments on this post yet)")

                task_lines.append("=== END THREAD CONTEXT ===")

        except Exception as exc:
            logger.debug(f"Could not fetch thread context for submission {submission_id}: {exc}")

    async def _add_recent_posts_context(self, task_lines: List[str], subreddit: str) -> None:
        """Add recent posts from the same subreddit."""
        try:
            # Fetch recent posts from the subreddit
            posts = await self._api_client.fetch_subreddit_new(subreddit, limit=5)

            if posts:
                task_lines.append(f"\n=== RECENT POSTS IN r/{subreddit} ===")
                for post in posts[:3]:  # Show only top 3 to avoid context bloat
                    # Format: Title | Author | Score
                    title_preview = (
                        post.title[:100] + "..." if post.title and len(post.title) > 100 else post.title or "(no title)"
                    )
                    task_lines.append(f"• {title_preview} (by @{post.author}, {post.created_at.strftime('%Y-%m-%d')})")

                task_lines.append(f"=== END RECENT POSTS IN r/{subreddit} ===")

        except Exception as exc:
            logger.debug(f"Could not fetch recent posts for r/{subreddit}: {exc}")

    # ------------------------------------------------------------------
    # Reddit ToS Compliance - Auto-purge on deletion detection
    # ------------------------------------------------------------------

    async def check_content_deleted(self, content_id: str) -> bool:
        """
        Check if content has been deleted on Reddit (Reddit ToS compliance).

        Args:
            content_id: Reddit content ID (without t3_/t1_ prefix)

        Returns:
            True if content is deleted or inaccessible
        """
        try:
            # Try to fetch the content
            fullname = f"t3_{content_id}" if not content_id.startswith("t") else content_id
            metadata = await self._api_client._fetch_item_metadata(fullname)

            # Check for deletion markers
            if metadata is not None:
                removed_by = metadata.get("removed_by_category")
                if removed_by is not None:
                    return True

                # Check if marked as deleted
                if metadata.get("removed") or metadata.get("deleted"):
                    return True

            return False

        except Exception as exc:
            # If we can't fetch it, assume it's deleted
            logger.debug(f"Unable to fetch {content_id}, assuming deleted: {exc}")
            return True

    async def purge_deleted_content(self, content_id: str, content_type: str = "unknown") -> None:
        """
        Purge deleted content from local caches (Reddit ToS compliance).

        Reddit ToS Requirement: Zero retention of deleted content.

        Args:
            content_id: Reddit content ID (without prefixes)
            content_type: Type of content (submission or comment)
        """
        purged_from_posts = False
        purged_from_comments = False

        # Purge from submission cache
        if content_id in self._seen_posts:
            del self._seen_posts[content_id]
            purged_from_posts = True

        # Purge from comment cache
        if content_id in self._seen_comments:
            del self._seen_comments[content_id]
            purged_from_comments = True

        if purged_from_posts or purged_from_comments:
            # Log purge event (audit trail)
            audit_event = {
                "event": "reddit_content_purged",
                "content_id": content_id,
                "content_type": content_type,
                "purged_from_posts": purged_from_posts,
                "purged_from_comments": purged_from_comments,
                "reason": "reddit_tos_compliance",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "audit_id": str(uuid4()),
            }
            logger.info(
                f"Purged deleted {content_type} {content_id} from cache (ToS compliance): "
                f"posts={purged_from_posts}, comments={purged_from_comments}"
            )

            # TODO: Send audit event to audit service if available
            # if self._audit_service:
            #     await self._audit_service.log_event(audit_event)

    async def check_and_purge_if_deleted(self, content_id: str) -> bool:
        """
        Check if content is deleted and purge if so (convenience method).

        Args:
            content_id: Reddit content ID

        Returns:
            True if content was deleted and purged
        """
        is_deleted = await self.check_content_deleted(content_id)
        if is_deleted:
            content_type = "submission" if content_id.startswith("t3_") else "comment"
            await self.purge_deleted_content(content_id, content_type)
            return True
        return False
