"""Passive observation support for the Reddit adapter."""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from ciris_engine.logic.adapters.base_observer import BaseObserver, detect_and_replace_spoofed_markers
from ciris_engine.logic.buses import BusManager
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

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
            origin_service="reddit",
        )

        self._poll_task: Optional[asyncio.Task[None]] = None
        self._seen_posts: "OrderedDict[str, None]" = OrderedDict()
        self._seen_comments: "OrderedDict[str, None]" = OrderedDict()
        logger.info("RedditObserver configured for r/%s", self._subreddit)

    # ------------------------------------------------------------------
    async def start(self) -> None:
        await self._api_client.start()
        self._poll_task = asyncio.create_task(self._poll_loop(), name="reddit-observer-poll")
        logger.info("RedditObserver started")

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
        try:
            while True:
                await self._poll_subreddit()
                await asyncio.sleep(self._poll_interval)
        except asyncio.CancelledError:
            logger.debug("RedditObserver poll loop cancelled")
        except Exception as exc:
            logger.exception("RedditObserver poll loop error: %s", exc)

    async def _poll_subreddit(self) -> None:
        posts = await self._api_client.fetch_subreddit_new(self._subreddit, limit=_PASSIVE_LIMIT)
        for entry in posts:
            if self._mark_seen(self._seen_posts, entry.item_id):
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
            # Check persistent storage for existing task with this correlation_id
            if await self._already_handled(entry.item_id):
                logger.debug(f"Reddit comment {entry.item_id} already handled (found in task database), skipping")
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

    def _build_message_from_entry(self, entry) -> RedditMessage:
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
