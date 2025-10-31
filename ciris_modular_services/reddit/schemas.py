"""Typed schemas backing the Reddit adapter modular service."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ciris_engine.schemas.runtime.messages import IncomingMessage


class RedditCredentials(BaseModel):
    """Configuration required to authenticate with Reddit."""

    client_id: str = Field(..., alias="reddit_client_id")
    client_secret: str = Field(..., alias="reddit_client_secret")
    username: str = Field(..., alias="reddit_username")
    password: str = Field(..., alias="reddit_password")
    user_agent: str = Field(..., alias="reddit_user_agent")
    subreddit: str = Field("ciris", alias="reddit_subreddit")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @classmethod
    def from_env(cls) -> "RedditCredentials | None":
        """Create credentials from environment variables if available."""

        env_mapping = {
            "reddit_client_id": os.getenv("CIRIS_REDDIT_CLIENT_ID"),
            "reddit_client_secret": os.getenv("CIRIS_REDDIT_CLIENT_SECRET"),
            "reddit_username": os.getenv("CIRIS_REDDIT_USERNAME"),
            "reddit_password": os.getenv("CIRIS_REDDIT_PASSWORD"),
            "reddit_user_agent": os.getenv("CIRIS_REDDIT_USER_AGENT", "CIRIS-RedditAdapter/1.0 (+https://ciris.ai)"),
            "reddit_subreddit": os.getenv("CIRIS_REDDIT_SUBREDDIT", "ciris"),
        }

        if all(value for value in env_mapping.values()):
            return cls.model_validate(env_mapping)
        return None

    def is_complete(self) -> bool:
        """Return True when all credential fields are populated."""

        return all(
            [
                self.client_id,
                self.client_secret,
                self.username,
                self.password,
                self.user_agent,
                self.subreddit,
            ]
        )


class RedditToken(BaseModel):
    """OAuth token state."""

    access_token: str
    expires_at: datetime

    model_config = ConfigDict(extra="forbid")

    def is_expired(self, now: Optional[datetime] = None, *, buffer_seconds: int = 60) -> bool:
        """Return True if the token is expired or within the refresh buffer."""

        reference = now or datetime.now(timezone.utc)
        refresh_threshold = self.expires_at - timedelta(seconds=buffer_seconds)
        return reference >= refresh_threshold


class RedditChannelType(str, Enum):
    """Supported channel targets for the Reddit adapter."""

    SUBREDDIT = "subreddit"
    SUBMISSION = "submission"
    COMMENT = "comment"
    USER = "user"


class RedditChannelReference(BaseModel):
    """Structured representation of a Reddit channel identifier."""

    target: RedditChannelType
    subreddit: Optional[str] = None
    submission_id: Optional[str] = None
    comment_id: Optional[str] = None
    username: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    @staticmethod
    def _normalize_subreddit(subreddit: str) -> str:
        return subreddit.lower().lstrip("r/")

    @staticmethod
    def _normalize_username(username: str) -> str:
        return username.lower().lstrip("u/")

    def to_string(self) -> str:
        """Serialize the reference to the canonical reddit:... form."""

        if self.target is RedditChannelType.USER:
            username = self._normalize_username(self.username or "")
            return f"reddit:u/{username}"

        subreddit = self._normalize_subreddit(self.subreddit or "")
        parts = [f"reddit:r/{subreddit}"]
        if self.target in (RedditChannelType.SUBMISSION, RedditChannelType.COMMENT):
            parts.append(f"post/{self.submission_id}")
        if self.target is RedditChannelType.COMMENT:
            parts.append(f"comment/{self.comment_id}")
        return ":".join(parts)

    @classmethod
    def parse(cls, reference: str) -> "RedditChannelReference":
        """Parse a string channel reference into a structured object."""

        parts = reference.split(":")
        if not parts or parts[0].lower() != "reddit":
            raise ValueError(f"Invalid reddit channel reference: {reference}")

        if len(parts) == 2 and parts[1].startswith("u/"):
            username = cls._normalize_username(parts[1])
            return cls(target=RedditChannelType.USER, username=username)

        if len(parts) >= 2 and parts[1].startswith("r/"):
            subreddit = cls._normalize_subreddit(parts[1])
            if len(parts) == 2:
                return cls(target=RedditChannelType.SUBREDDIT, subreddit=subreddit)

            submission = None
            comment = None
            for part in parts[2:]:
                if part.startswith("post/"):
                    submission = part.split("/", 1)[1]
                elif part.startswith("comment/"):
                    comment = part.split("/", 1)[1]

            if submission and comment:
                return cls(
                    target=RedditChannelType.COMMENT,
                    subreddit=subreddit,
                    submission_id=submission,
                    comment_id=comment,
                )
            if submission:
                return cls(target=RedditChannelType.SUBMISSION, subreddit=subreddit, submission_id=submission)

        raise ValueError(f"Unsupported reddit channel reference: {reference}")


class RedditUserContextRequest(BaseModel):
    """Parameters for the reddit_get_user_context tool."""

    username: str
    include_history: bool = True
    history_limit: int = Field(5, ge=1, le=25)

    model_config = ConfigDict(extra="forbid")


class RedditSubmitPostRequest(BaseModel):
    """Parameters for submitting a new post."""

    title: str
    body: str = Field(..., description="Markdown body for the self post")
    send_replies: bool = True
    flair_id: Optional[str] = None
    flair_text: Optional[str] = None
    nsfw: bool = False
    spoiler: bool = False
    subreddit: Optional[str] = Field(None, description="Override subreddit for the post")

    model_config = ConfigDict(extra="forbid")


class RedditSubmitCommentRequest(BaseModel):
    """Parameters for submitting a comment."""

    parent_fullname: str = Field(..., description="Thing ID of the parent submission or comment")
    text: str = Field(..., description="Markdown body of the comment")
    lock_thread: bool = Field(False, description="Lock the submission after replying")

    model_config = ConfigDict(extra="forbid")


class RedditRemoveContentRequest(BaseModel):
    """Parameters for removing content."""

    thing_fullname: str = Field(..., description="Thing ID of the submission or comment")
    spam: bool = Field(False, description="Mark as spam (True) or just remove (False)")

    model_config = ConfigDict(extra="forbid")


class RedditGetSubmissionRequest(BaseModel):
    """Parameters for fetching submission metadata."""

    submission_id: Optional[str] = Field(None, description="ID without the t3_ prefix")
    permalink: Optional[str] = Field(None, description="Canonical reddit permalink")
    include_comments: bool = False
    comment_limit: int = Field(3, ge=1, le=20)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_source(self) -> "RedditGetSubmissionRequest":
        """Ensure either submission_id or permalink is provided."""

        if not self.submission_id and not self.permalink:
            raise ValueError("Either submission_id or permalink must be provided")
        return self


class RedditDeleteContentRequest(BaseModel):
    """
    Parameters for permanently deleting content (Reddit ToS compliance).

    Note: This is different from remove_content which hides content.
          This permanently deletes it from Reddit.
    """

    thing_fullname: str = Field(..., description="Thing ID (t3_xxxxx or t1_xxxxx)")
    purge_cache: bool = Field(True, description="Purge from local cache (Reddit ToS compliance)")

    model_config = ConfigDict(extra="forbid")


class RedditDisclosureRequest(BaseModel):
    """Parameters for AI transparency disclosure (community guidelines compliance)."""

    channel_reference: str = Field(..., description="Channel reference (reddit:r/sub:post/id)")
    custom_message: Optional[str] = Field(None, description="Optional custom disclosure message")

    model_config = ConfigDict(extra="forbid")


class RedditTimelineEntry(BaseModel):
    """Simplified timeline entry for submissions and comments."""

    entry_type: Literal["submission", "comment"]
    item_id: str
    fullname: str
    subreddit: str
    permalink: str
    score: int
    created_at: datetime
    channel_reference: str
    author: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    url: Optional[str] = None
    parent_id: Optional[str] = None  # Reddit fullname of parent (t1_xxx for comment, t3_xxx for post)

    model_config = ConfigDict(extra="forbid")


class RedditUserContext(BaseModel):
    """Aggregated user context details."""

    username: str
    user_id: str
    link_karma: int
    comment_karma: int
    is_mod: bool
    account_created_at: datetime
    recent_posts: List[RedditTimelineEntry] = Field(default_factory=list)
    recent_comments: List[RedditTimelineEntry] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class RedditSubmissionSummary(BaseModel):
    """Submission metadata returned by reddit_get_submission and reddit_submit_post."""

    submission_id: str
    fullname: str
    title: str
    self_text: Optional[str]
    url: str
    subreddit: str
    author: str
    score: int
    num_comments: int
    created_at: datetime
    permalink: str
    channel_reference: str
    top_comments: List["RedditCommentSummary"] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class RedditCommentSummary(BaseModel):
    """Comment metadata used in responses."""

    comment_id: str
    fullname: str
    submission_id: str
    body: str
    author: str
    subreddit: str
    permalink: str
    created_at: datetime
    score: int
    channel_reference: str
    parent_id: Optional[str] = None  # Reddit fullname of parent (t1_xxx for comment, t3_xxx for post)

    model_config = ConfigDict(extra="forbid")


class RedditPostResult(BaseModel):
    """Result returned when a post is created."""

    submission: RedditSubmissionSummary

    model_config = ConfigDict(extra="forbid")


class RedditCommentResult(BaseModel):
    """Result returned when a comment is created."""

    comment: RedditCommentSummary

    model_config = ConfigDict(extra="forbid")


class RedditRemovalResult(BaseModel):
    """Result returned when content is removed."""

    thing_fullname: str
    removed: bool
    spam: bool

    model_config = ConfigDict(extra="forbid")


class RedditTimelineResponse(BaseModel):
    """Response returned when fetching listings for active observation."""

    entries: List[RedditTimelineEntry] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class RedditMessage(IncomingMessage):
    """Incoming Reddit message formatted for observers."""

    permalink: Optional[str] = None
    subreddit: Optional[str] = None
    submission_id: Optional[str] = None
    comment_id: Optional[str] = None
    channel_reference: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")


__all__ = [
    "RedditCredentials",
    "RedditToken",
    "RedditChannelType",
    "RedditChannelReference",
    "RedditUserContextRequest",
    "RedditSubmitPostRequest",
    "RedditSubmitCommentRequest",
    "RedditRemoveContentRequest",
    "RedditGetSubmissionRequest",
    "RedditTimelineEntry",
    "RedditUserContext",
    "RedditSubmissionSummary",
    "RedditCommentSummary",
    "RedditPostResult",
    "RedditCommentResult",
    "RedditRemovalResult",
    "RedditTimelineResponse",
    "RedditMessage",
    "RedditDeletionResult",
    "RedditDeletionStatus",
    "RedditDeleteContentRequest",
    "RedditDisclosureRequest",
]


# ============================================================================
# Reddit ToS Compliance - Deletion Schemas
# ============================================================================


class RedditDeletionResult(BaseModel):
    """
    Result of Reddit content deletion operation.

    Reddit ToS Compliance: Zero retention of deleted content.
    All deleted content must be purged from local cache immediately.
    """

    content_id: str = Field(..., description="Reddit content ID (t3_xxxxx or t1_xxxxx)")
    content_type: Literal["submission", "comment"] = Field(..., description="Type of content deleted")
    deleted_from_reddit: bool = Field(..., description="Whether content was deleted from Reddit API")
    purged_from_cache: bool = Field(..., description="Whether content was purged from local cache")
    audit_entry_id: str = Field(..., description="Audit trail entry ID for this deletion")
    deleted_at: datetime = Field(..., description="Timestamp of deletion")

    model_config = ConfigDict(extra="forbid")


class RedditDeletionStatus(BaseModel):
    """
    Status tracking for Reddit content deletion (similar to DSAR deletion status).

    Tracks deletion progress through multiple phases:
    1. Initiated - Deletion request received
    2. Reddit deletion - Content deleted from Reddit API
    3. Cache purge - Content removed from local cache
    4. Audit complete - Deletion logged to audit trail
    """

    content_id: str = Field(..., description="Reddit content ID being tracked")
    initiated_at: datetime = Field(..., description="When deletion was initiated")
    completed_at: Optional[datetime] = Field(None, description="When deletion completed (all phases)")
    deletion_confirmed: bool = Field(..., description="Whether deletion from Reddit confirmed")
    cache_purged: bool = Field(..., description="Whether local cache purged")
    audit_trail_updated: bool = Field(..., description="Whether audit trail updated")

    model_config = ConfigDict(extra="forbid")

    @property
    def is_complete(self) -> bool:
        """Return True if all deletion phases are complete."""
        return self.deletion_confirmed and self.cache_purged and self.audit_trail_updated
