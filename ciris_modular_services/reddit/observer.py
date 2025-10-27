"""Passive observation support for the Reddit adapter."""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from typing import Optional

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
            message = self._build_message_from_entry(entry)
            await self.handle_incoming_message(message)

        comments = await self._api_client.fetch_subreddit_comments(self._subreddit, limit=_PASSIVE_LIMIT)
        for entry in comments:
            if self._mark_seen(self._seen_comments, entry.item_id):
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
