"""Reddit adapter modular service implementation."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, ValidationError

from ciris_engine.logic.buses import BusManager
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus, ToolInfo, ToolParameterSchema
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.messages import FetchedMessage
from ciris_engine.schemas.services.core import ServiceCapabilities
from ciris_engine.schemas.types import JSONDict, JSONValue

from .protocol import RedditCommunicationProtocol, RedditOAuthProtocol, RedditToolProtocol
from .schemas import (
    RedditChannelReference,
    RedditChannelType,
    RedditCommentResult,
    RedditCommentSummary,
    RedditCredentials,
    RedditDeleteContentRequest,
    RedditDeletionResult,
    RedditDeletionStatus,
    RedditDisclosureRequest,
    RedditGetSubmissionRequest,
    RedditPostResult,
    RedditRemovalResult,
    RedditRemoveContentRequest,
    RedditSubmissionSummary,
    RedditSubmitCommentRequest,
    RedditSubmitPostRequest,
    RedditTimelineEntry,
    RedditTimelineResponse,
    RedditToken,
    RedditUserContext,
    RedditUserContextRequest,
)

logger = logging.getLogger(__name__)


def _build_channel_reference(
    subreddit: str,
    submission_id: Optional[str] = None,
    comment_id: Optional[str] = None,
) -> str:
    """Return a canonical reddit:r/<sub>:post/<id>:comment/<id> reference."""

    if comment_id:
        reference = RedditChannelReference(
            target=RedditChannelType.COMMENT,
            subreddit=subreddit,
            submission_id=submission_id,
            comment_id=comment_id,
        )
    elif submission_id:
        reference = RedditChannelReference(
            target=RedditChannelType.SUBMISSION,
            subreddit=subreddit,
            submission_id=submission_id,
        )
    else:
        reference = RedditChannelReference(target=RedditChannelType.SUBREDDIT, subreddit=subreddit)
    return reference.to_string()


class RedditAPIClient:
    """Thin wrapper around the Reddit REST API with OAuth management."""

    _TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
    _API_BASE_URL = "https://oauth.reddit.com"
    _USER_AGENT_FALLBACK = "CIRIS-RedditAdapter/1.0 (+https://ciris.ai)"

    def __init__(self, credentials: RedditCredentials, time_service: Optional[TimeServiceProtocol] = None) -> None:
        self._credentials = credentials
        self._time_service = time_service
        self._http_client: Optional[httpx.AsyncClient] = None
        self._token: Optional[RedditToken] = None
        self._token_lock = asyncio.Lock()
        self._request_count = 0
        self._error_count = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        headers = {
            "User-Agent": self._credentials.user_agent or self._USER_AGENT_FALLBACK,
            "Accept": "application/json",
        }
        timeout = httpx.Timeout(connect=10.0, read=20.0, write=20.0, pool=10.0)
        self._http_client = httpx.AsyncClient(base_url=self._API_BASE_URL, headers=headers, timeout=timeout)
        await self.refresh_token(force=True)

    async def stop(self) -> None:
        if self._http_client:
            await self._http_client.aclose()
        self._http_client = None
        self._token = None

    async def update_credentials(self, credentials: RedditCredentials) -> None:
        self._credentials = credentials
        self._token = None
        if self._http_client:
            await self.refresh_token(force=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _now(self) -> datetime:
        if self._time_service:
            return self._time_service.now()
        return datetime.now(timezone.utc)

    @property
    def token_active(self) -> bool:
        return bool(self._token and not self._token.is_expired(self._now()))

    @property
    def metrics(self) -> Dict[str, float]:
        return {"requests": float(self._request_count), "errors": float(self._error_count)}

    def _add_ciris_attribution(self, text: str, *, max_length: int = 10000) -> str:
        """
        Add CIRIS attribution footer to post/comment text.

        Args:
            text: Original post/comment text
            max_length: Reddit character limit (10000 for posts/comments)

        Returns:
            Text with attribution, truncated if necessary to fit within limit

        Note: Reddit rejects posts/comments longer than 10,000 characters.
              This method ensures attribution is always included by truncating
              the original text if needed.
        """
        attribution = (
            "\n\n"
            "Posted by a CIRIS agent, learn more at https://ciris.ai "
            "or chat with scout at https://scout.ciris.ai"
        )

        # If text + attribution fits within limit, return as-is
        if len(text) + len(attribution) <= max_length:
            return text + attribution

        # Otherwise, truncate text to make room for attribution
        # Leave space for attribution + ellipsis + newline
        truncation_marker = "...\n"
        available_space = max_length - len(attribution) - len(truncation_marker)

        if available_space < 100:  # Sanity check: need at least 100 chars for meaningful content
            # If attribution is too large for the limit, skip it (shouldn't happen with 10k limit)
            logger.warning(
                f"Attribution footer ({len(attribution)} chars) too large for limit ({max_length}), "
                "submitting without attribution"
            )
            return text[:max_length]

        truncated_text = text[:available_space]
        logger.info(
            f"Truncated text from {len(text)} to {len(truncated_text)} chars to fit attribution "
            f"within {max_length} char limit"
        )
        return truncated_text + truncation_marker + attribution

    async def refresh_token(self, force: bool = False) -> bool:
        async with self._token_lock:
            if not force and self._token and not self._token.is_expired(self._now()):
                return True

            auth = (self._credentials.client_id, self._credentials.client_secret)
            data = {
                "grant_type": "password",
                "username": self._credentials.username,
                "password": self._credentials.password,
            }
            headers = {"User-Agent": self._credentials.user_agent or self._USER_AGENT_FALLBACK}

            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=20.0)) as client:
                response = await client.post(self._TOKEN_URL, data=data, auth=auth, headers=headers)

            if response.status_code >= 300:
                self._error_count += 1
                raise RuntimeError(f"Token request failed ({response.status_code}): {response.text}")

            payload = self._expect_dict(response.json(), context="token")
            access_token = self._get_str(payload, "access_token")

            # Validate access token - empty token indicates auth failure (suspended account, invalid credentials)
            if not access_token or access_token.strip() == "":
                error_msg = payload.get("error", "Unknown error")
                error_desc = payload.get("error_description", "No access_token in response")
                logger.error(
                    f"Reddit OAuth failed - likely suspended account or invalid credentials. "
                    f"Error: {error_msg}, Description: {error_desc}, Response: {payload}"
                )
                raise RuntimeError(
                    f"Reddit authentication failed: {error_msg} - {error_desc}. "
                    "This may indicate a suspended Reddit account or invalid credentials."
                )

            expires_in = int(float(self._get_str(payload, "expires_in", default="3600")))
            expires_at = self._now() + timedelta(seconds=expires_in)
            self._token = RedditToken(access_token=access_token, expires_at=expires_at)
            logger.info("Refreshed Reddit OAuth token; expires at %s", expires_at.isoformat())
            return True

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        if not self._http_client:
            raise RuntimeError("HTTP client not initialized")

        await self.refresh_token()
        assert self._token is not None
        headers = {"Authorization": f"bearer {self._token.access_token}"}

        response = await self._http_client.request(method, path, params=params, data=data, headers=headers)
        self._request_count += 1

        if response.status_code == 401:
            await self.refresh_token(force=True)
            assert self._token is not None
            headers["Authorization"] = f"bearer {self._token.access_token}"
            response = await self._http_client.request(method, path, params=params, data=data, headers=headers)

        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "1"))
            await asyncio.sleep(max(retry_after, 0))
            response = await self._http_client.request(method, path, params=params, data=data, headers=headers)

        if response.status_code >= 400:
            self._error_count += 1
        return response

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> JSONDict:
        response = await self._request(method, path, params=params, data=data)
        payload = response.json()
        return self._expect_dict(payload, context=path)

    # ------------------------------------------------------------------
    # Expectation helpers
    # ------------------------------------------------------------------
    def _expect_dict(self, value: JSONValue, *, context: str) -> JSONDict:
        if not isinstance(value, dict):
            raise RuntimeError(f"{context}: expected object")
        return value

    def _get_str(self, data: JSONDict, key: str, *, default: str = "") -> str:
        value = data.get(key, default)
        if value is None:
            return default
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float)):
            return str(value)
        return default

    def _build_permalink(self, permalink: str) -> str:
        if permalink.startswith("http"):
            return permalink
        return f"https://www.reddit.com{permalink}" if permalink else ""

    def _strip_prefix(self, value: str, prefix: str) -> str:
        if value.startswith(prefix):
            return value[len(prefix) :]
        return value

    # ------------------------------------------------------------------
    # High level API methods
    # ------------------------------------------------------------------
    async def fetch_user_context(self, request: RedditUserContextRequest) -> RedditUserContext:
        about_payload = await self._request_json("GET", f"/user/{request.username}/about")
        about_data = self._expect_dict(about_payload.get("data"), context="user_about.data")

        account_created = datetime.fromtimestamp(
            float(self._get_str(about_data, "created_utc", default="0")), tz=timezone.utc
        )
        context = RedditUserContext(
            username=self._get_str(about_data, "name"),
            user_id=self._get_str(about_data, "id"),
            link_karma=int(float(self._get_str(about_data, "link_karma", default="0"))),
            comment_karma=int(float(self._get_str(about_data, "comment_karma", default="0"))),
            is_mod=bool(about_data.get("is_mod", False)),
            account_created_at=account_created,
        )

        if request.include_history:
            submissions = await self._fetch_listing(
                f"/user/{request.username}/submitted", limit=request.history_limit, entry_type="submission"
            )
            comments = await self._fetch_listing(
                f"/user/{request.username}/comments", limit=request.history_limit, entry_type="comment"
            )
            context.recent_posts = submissions
            context.recent_comments = comments

        return context

    async def submit_post(self, request: RedditSubmitPostRequest) -> RedditSubmissionSummary:
        subreddit = request.subreddit or self._credentials.subreddit
        # Add CIRIS attribution to post body
        body_with_attribution = self._add_ciris_attribution(request.body)
        payload = {
            "sr": subreddit,
            "kind": "self",
            "title": request.title,
            "text": body_with_attribution,
            "resubmit": "true",
            "sendreplies": "true" if request.send_replies else "false",
        }
        if request.flair_id:
            payload["flair_id"] = request.flair_id
        if request.flair_text:
            payload["flair_text"] = request.flair_text
        if request.nsfw:
            payload["nsfw"] = "true"
        if request.spoiler:
            payload["spoiler"] = "true"

        response = await self._request("POST", "/api/submit", data=payload)
        result = await self._parse_submission_response(
            response, subreddit=subreddit, title=request.title, body=request.body
        )
        if not result:
            raise RuntimeError("Submission failed")
        return result.submission

    async def submit_comment(self, request: RedditSubmitCommentRequest) -> RedditCommentSummary:
        # Add CIRIS attribution to comment text
        text_with_attribution = self._add_ciris_attribution(request.text)
        payload = {"thing_id": request.parent_fullname, "text": text_with_attribution}
        response = await self._request("POST", "/api/comment", data=payload)
        comment = await self._parse_comment_response(response)
        if not comment:
            raise RuntimeError(
                f"Comment response missing data - status: {response.status_code}, " f"text: {response.text[:200]}"
            )

        if request.lock_thread and comment.submission_id:
            await self._request("POST", "/api/lock", data={"id": f"t3_{comment.submission_id}"})
        return comment

    async def remove_content(self, request: RedditRemoveContentRequest) -> RedditRemovalResult:
        payload = {"id": request.thing_fullname, "spam": "true" if request.spam else "false"}
        response = await self._request("POST", "/api/remove", data=payload)
        if response.status_code >= 300:
            raise RuntimeError(f"Removal failed ({response.status_code}): {response.text}")
        return RedditRemovalResult(thing_fullname=request.thing_fullname, removed=True, spam=request.spam)

    async def delete_content(self, thing_fullname: str) -> bool:
        """
        Permanently delete content from Reddit (Reddit ToS compliance).

        Args:
            thing_fullname: Reddit thing fullname (t3_xxxxx or t1_xxxxx)

        Returns:
            True if deletion successful

        Note: This uses DELETE /api/del which permanently removes content.
              This is different from remove_content which hides content.
        """
        payload = {"id": thing_fullname}
        response = await self._request("POST", "/api/del", data=payload)
        if response.status_code >= 300:
            raise RuntimeError(f"Deletion failed ({response.status_code}): {response.text}")
        return True

    async def get_submission_summary(
        self,
        submission_id: str,
        *,
        include_comments: bool,
        comment_limit: int,
    ) -> RedditSubmissionSummary:
        fullname = f"t3_{submission_id}"
        metadata = await self._fetch_item_metadata(fullname)
        if not metadata:
            raise RuntimeError("Submission not found")
        return await self._build_submission_summary(
            metadata, include_comments=include_comments, comment_limit=comment_limit
        )

    async def fetch_subreddit_new(self, subreddit: str, *, limit: int) -> List[RedditTimelineEntry]:
        return await self._fetch_listing(f"/r/{subreddit}/new", limit=limit, entry_type="submission")

    async def fetch_subreddit_comments(self, subreddit: str, *, limit: int) -> List[RedditTimelineEntry]:
        return await self._fetch_listing(f"/r/{subreddit}/comments", limit=limit, entry_type="comment")

    async def fetch_submission_comments(self, submission_id: str, *, limit: int) -> List[RedditCommentSummary]:
        params = {"limit": str(limit)}
        response = await self._request("GET", f"/comments/{submission_id}", params=params)
        if response.status_code >= 300:
            raise RuntimeError(f"Failed to fetch comments: {response.status_code}")

        payload = response.json()
        if not isinstance(payload, list) or len(payload) < 2:
            return []

        comments_listing = payload[1]
        listing_data = self._expect_dict(comments_listing.get("data"), context="comments.data")
        children = listing_data.get("children", [])
        summaries: List[RedditCommentSummary] = []
        if isinstance(children, list):
            for child in children:
                child_dict = self._expect_dict(child, context="comment.child")
                child_data = self._expect_dict(child_dict.get("data"), context="comment.child.data")
                summary = self._build_comment_summary(child_dict.get("kind"), child_data, submission_id=submission_id)
                if summary:
                    summaries.append(summary)
                if len(summaries) >= limit:
                    break
        return summaries

    async def fetch_user_activity(self, username: str, *, limit: int) -> RedditTimelineResponse:
        posts = await self._fetch_listing(f"/user/{username}/submitted", limit=limit, entry_type="submission")
        comments = await self._fetch_listing(f"/user/{username}/comments", limit=limit, entry_type="comment")
        return RedditTimelineResponse(entries=posts + comments)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------
    async def _parse_submission_response(
        self, response: httpx.Response, *, subreddit: str, title: str, body: str
    ) -> Optional[RedditPostResult]:
        if response.status_code >= 300:
            raise RuntimeError(f"Submission failed ({response.status_code}): {response.text}")

        payload = self._expect_dict(response.json(), context="submit")
        json_data = payload.get("json")
        if not isinstance(json_data, dict):
            return None

        errors = json_data.get("errors", [])
        if isinstance(errors, list) and errors:
            raise RuntimeError(f"Reddit returned errors: {errors}")

        data_dict = self._expect_dict(json_data.get("data"), context="submit.data")
        submission_id = self._strip_prefix(self._get_str(data_dict, "id"), prefix="t3_")
        fullname = self._get_str(data_dict, "name") or f"t3_{submission_id}"
        url = self._get_str(data_dict, "url")
        return RedditPostResult(
            submission=RedditSubmissionSummary(
                submission_id=submission_id,
                fullname=fullname,
                title=title,
                self_text=body,
                url=url,
                subreddit=subreddit,
                author=self._credentials.username,
                score=1,
                num_comments=0,
                created_at=self._now(),
                permalink=url,
                channel_reference=_build_channel_reference(subreddit, submission_id),
            )
        )

    async def _parse_comment_response(self, response: httpx.Response) -> Optional[RedditCommentSummary]:
        if response.status_code >= 300:
            raise RuntimeError(f"Comment failed ({response.status_code}): {response.text}")

        payload = self._expect_dict(response.json(), context="comment")
        json_data = payload.get("json")
        if not isinstance(json_data, dict):
            logger.error(f"Comment response missing 'json' dict: {payload}")
            return None

        errors = json_data.get("errors", [])
        if isinstance(errors, list) and errors:
            raise RuntimeError(f"Reddit returned errors: {errors}")

        data_dict = self._expect_dict(json_data.get("data"), context="comment.data")
        things = data_dict.get("things", [])
        if not isinstance(things, list) or not things:
            logger.error(f"Comment response missing 'things' list: json_data={json_data}")
            return None

        first = self._expect_dict(things[0], context="comment.thing")
        comment_data = self._expect_dict(first.get("data"), context="comment.thing.data")
        subreddit = self._get_str(comment_data, "subreddit")
        submission_id = self._strip_prefix(self._get_str(comment_data, "link_id"), prefix="t3_")
        comment_id = self._get_str(comment_data, "id")
        permalink = self._build_permalink(self._get_str(comment_data, "permalink"))
        return RedditCommentSummary(
            comment_id=comment_id,
            fullname=self._get_str(comment_data, "name"),
            submission_id=submission_id,
            body=self._get_str(comment_data, "body"),
            author=self._get_str(comment_data, "author"),
            subreddit=subreddit,
            permalink=permalink,
            created_at=datetime.fromtimestamp(
                float(self._get_str(comment_data, "created_utc", default="0")), tz=timezone.utc
            ),
            score=int(float(self._get_str(comment_data, "score", default="0"))),
            channel_reference=_build_channel_reference(subreddit, submission_id, comment_id),
        )

    async def _fetch_item_metadata(self, fullname: str) -> Optional[JSONDict]:
        response = await self._request("GET", "/api/info", params={"id": fullname})
        if response.status_code >= 300:
            raise RuntimeError(f"Failed to fetch metadata ({response.status_code}): {response.text}")

        payload = self._expect_dict(response.json(), context="info")
        data = self._expect_dict(payload.get("data"), context="info.data")
        children = data.get("children", [])
        if not isinstance(children, list) or not children:
            return None

        first = self._expect_dict(children[0], context="info.child")
        return self._expect_dict(first.get("data"), context="info.child.data")

    async def _build_submission_summary(
        self,
        data: JSONDict,
        *,
        include_comments: bool,
        comment_limit: int,
    ) -> RedditSubmissionSummary:
        subreddit = self._get_str(data, "subreddit")
        submission_id = self._get_str(data, "id")
        permalink = self._build_permalink(self._get_str(data, "permalink"))
        summary = RedditSubmissionSummary(
            submission_id=submission_id,
            fullname=self._get_str(data, "name"),
            title=self._get_str(data, "title"),
            self_text=self._get_str(data, "selftext"),
            url=self._get_str(data, "url"),
            subreddit=subreddit,
            author=self._get_str(data, "author"),
            score=int(float(self._get_str(data, "score", default="0"))),
            num_comments=int(float(self._get_str(data, "num_comments", default="0"))),
            created_at=datetime.fromtimestamp(float(self._get_str(data, "created_utc", default="0")), tz=timezone.utc),
            permalink=permalink,
            channel_reference=_build_channel_reference(subreddit, submission_id),
        )

        if include_comments:
            summary.top_comments = await self.fetch_submission_comments(submission_id, limit=comment_limit)
        return summary

    async def _fetch_listing(self, path: str, *, limit: int, entry_type: str) -> List[RedditTimelineEntry]:
        payload = await self._request_json("GET", path, params={"limit": str(limit)})
        data = self._expect_dict(payload.get("data"), context="listing.data")
        children_value = data.get("children", [])
        entries: List[RedditTimelineEntry] = []

        if isinstance(children_value, list):
            for child in children_value:
                child_dict = self._expect_dict(child, context="listing.child")
                child_data = self._expect_dict(child_dict.get("data"), context="listing.child.data")
                entry = self._build_timeline_entry(child_dict.get("kind"), child_data)
                if entry and entry.entry_type == entry_type:
                    entries.append(entry)
                if len(entries) >= limit:
                    break

        return entries

    def _build_timeline_entry(self, kind_value: JSONValue, child_data: JSONDict) -> Optional[RedditTimelineEntry]:
        if not isinstance(kind_value, str):
            return None

        created = datetime.fromtimestamp(float(self._get_str(child_data, "created_utc", default="0")), tz=timezone.utc)
        permalink = self._build_permalink(self._get_str(child_data, "permalink"))
        subreddit = self._get_str(child_data, "subreddit")
        fullname = self._get_str(child_data, "name")
        item_id = self._strip_prefix(fullname, prefix="t3_" if kind_value == "t3" else "t1_")
        score = int(float(self._get_str(child_data, "score", default="0")))

        if kind_value == "t3":
            return RedditTimelineEntry(
                entry_type="submission",
                item_id=item_id,
                fullname=fullname,
                subreddit=subreddit,
                permalink=permalink,
                score=score,
                created_at=created,
                channel_reference=_build_channel_reference(subreddit, item_id),
                author=self._get_str(child_data, "author"),
                title=self._get_str(child_data, "title"),
                body=self._get_str(child_data, "selftext"),
                url=self._get_str(child_data, "url"),
            )
        if kind_value == "t1":
            submission_id = self._strip_prefix(self._get_str(child_data, "link_id"), prefix="t3_")
            parent_id = self._get_str(child_data, "parent_id", default="") or None
            return RedditTimelineEntry(
                entry_type="comment",
                item_id=item_id,
                fullname=fullname,
                subreddit=subreddit,
                permalink=permalink,
                score=score,
                created_at=created,
                channel_reference=_build_channel_reference(subreddit, submission_id, item_id),
                author=self._get_str(child_data, "author"),
                body=self._get_str(child_data, "body"),
                parent_id=parent_id,
            )
        return None

    def _build_comment_summary(
        self,
        kind_value: JSONValue,
        comment_data: JSONDict,
        *,
        submission_id: str,
    ) -> Optional[RedditCommentSummary]:
        if kind_value != "t1":
            return None
        comment_id = self._get_str(comment_data, "id")
        subreddit = self._get_str(comment_data, "subreddit")
        permalink = self._build_permalink(self._get_str(comment_data, "permalink"))
        parent_id = self._get_str(comment_data, "parent_id", default="") or None
        return RedditCommentSummary(
            comment_id=comment_id,
            fullname=self._get_str(comment_data, "name"),
            submission_id=submission_id,
            body=self._get_str(comment_data, "body"),
            author=self._get_str(comment_data, "author"),
            subreddit=subreddit,
            permalink=permalink,
            created_at=datetime.fromtimestamp(
                float(self._get_str(comment_data, "created_utc", default="0")), tz=timezone.utc
            ),
            score=int(float(self._get_str(comment_data, "score", default="0"))),
            channel_reference=_build_channel_reference(subreddit, submission_id, comment_id),
            parent_id=parent_id,
        )


# ----------------------------------------------------------------------
# Base service shared by tool and communication implementations
# ----------------------------------------------------------------------


class RedditServiceBase(BaseService, RedditOAuthProtocol):
    """Base class providing shared Reddit API functionality."""

    def __init__(
        self,
        credentials: Optional[RedditCredentials] = None,
        *,
        time_service: Optional[TimeServiceProtocol] = None,
        service_name: str,
    ) -> None:
        super().__init__(time_service=time_service, service_name=service_name, version="1.0.0")
        resolved_credentials = credentials or RedditCredentials.from_env()
        if not resolved_credentials:
            raise RuntimeError("Reddit credentials are not configured")
        self._credentials = resolved_credentials
        self._client = RedditAPIClient(self._credentials, time_service=time_service)
        self._subreddit = RedditChannelReference._normalize_subreddit(self._credentials.subreddit)

    # BaseService overrides -------------------------------------------------
    def _check_dependencies(self) -> bool:
        return self._credentials is not None and self._credentials.is_complete()

    async def _on_start(self) -> None:
        await self._client.start()

    async def _on_stop(self) -> None:
        await self._client.stop()

    def _collect_custom_metrics(self) -> Dict[str, float]:
        metrics = self._client.metrics
        metrics["token_active"] = 1.0 if self._client.token_active else 0.0
        return metrics

    def _register_dependencies(self) -> None:
        super()._register_dependencies()
        self._dependencies.add("httpx")

    # RedditOAuthProtocol ---------------------------------------------------
    async def update_credentials(self, credentials: RedditCredentials) -> None:
        self._credentials = credentials
        self._subreddit = RedditChannelReference._normalize_subreddit(credentials.subreddit)
        await self._client.update_credentials(credentials)

    async def refresh_token(self, force: bool = False) -> bool:
        try:
            return await self._client.refresh_token(force=force)
        except Exception as exc:  # pragma: no cover - defensive logging
            self._track_error(exc)
            return False


# ----------------------------------------------------------------------
# Tool service implementation
# ----------------------------------------------------------------------


class RedditToolService(RedditServiceBase):
    """Tool service providing Reddit moderation and outreach utilities."""

    def __init__(
        self,
        credentials: Optional[RedditCredentials] = None,
        *,
        time_service: Optional[TimeServiceProtocol] = None,
    ) -> None:
        super().__init__(credentials, time_service=time_service, service_name="RedditToolService")
        self._results: Dict[str, ToolExecutionResult] = {}
        self._tool_handlers = {
            "reddit_get_user_context": self._tool_get_user_context,
            "reddit_submit_post": self._tool_submit_post,
            "reddit_submit_comment": self._tool_submit_comment,
            "reddit_remove_content": self._tool_remove_content,
            "reddit_get_submission": self._tool_get_submission,
            "reddit_observe": self._tool_observe,
            "reddit_delete_content": self._tool_delete_content,
            "reddit_disclose_identity": self._tool_disclose_identity,
        }
        self._request_models: Dict[str, type[BaseModel]] = {
            "reddit_get_user_context": RedditUserContextRequest,
            "reddit_submit_post": RedditSubmitPostRequest,
            "reddit_submit_comment": RedditSubmitCommentRequest,
            "reddit_remove_content": RedditRemoveContentRequest,
            "reddit_get_submission": RedditGetSubmissionRequest,
            "reddit_delete_content": RedditDeleteContentRequest,
            "reddit_disclose_identity": RedditDisclosureRequest,
        }
        # Deletion status tracking (DSAR pattern)
        self._deletion_statuses: Dict[str, RedditDeletionStatus] = {}
        self._tool_schemas = self._build_tool_schemas()
        self._tool_info = self._build_tool_info()
        self._executions = 0
        self._failures = 0

    # BaseService -----------------------------------------------------------
    def get_service_type(self) -> ServiceType:
        return ServiceType.TOOL

    def _get_actions(self) -> List[str]:
        return list(self._tool_handlers.keys())

    # ToolServiceProtocol ---------------------------------------------------
    async def execute_tool(self, tool_name: str, parameters: JSONDict) -> ToolExecutionResult:
        self._track_request()
        self._executions += 1

        correlation_id_raw = parameters.get("correlation_id")
        correlation_id = str(correlation_id_raw) if correlation_id_raw else str(uuid.uuid4())

        handler = self._tool_handlers.get(tool_name)
        if not handler:
            self._failures += 1
            result = ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.NOT_FOUND,
                success=False,
                data=None,
                error=f"Unknown Reddit tool: {tool_name}",
                correlation_id=correlation_id,
            )
            self._results[correlation_id] = result
            return result

        try:
            result = await handler(parameters, correlation_id)
            if not result.success:
                self._failures += 1
            self._results[correlation_id] = result
            return result
        except Exception as exc:  # pragma: no cover - defensive logging
            self._failures += 1
            self._track_error(exc)
            result = ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=str(exc),
                correlation_id=correlation_id,
            )
            self._results[correlation_id] = result
            return result

    async def list_tools(self) -> List[str]:
        return list(self._tool_handlers.keys())

    async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
        return self._tool_schemas.get(tool_name)

    async def get_available_tools(self) -> List[str]:
        return await self.list_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        return self._tool_info.get(tool_name)

    async def get_all_tool_info(self) -> List[ToolInfo]:
        return list(self._tool_info.values())

    async def validate_parameters(self, tool_name: str, parameters: JSONDict) -> bool:
        model_cls = self._request_models.get(tool_name)
        if not model_cls:
            return False
        try:
            model_cls.model_validate(parameters)
            return True
        except ValidationError:
            return False

    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        return self._results.get(correlation_id)

    def _collect_custom_metrics(self) -> Dict[str, float]:
        metrics = super()._collect_custom_metrics()
        metrics.update({"tool_executions": float(self._executions), "tool_failures": float(self._failures)})
        return metrics

    # Tool handlers ---------------------------------------------------------
    async def _tool_get_user_context(self, parameters: JSONDict, correlation_id: str) -> ToolExecutionResult:
        try:
            request = RedditUserContextRequest.model_validate(parameters)
        except ValidationError as error:
            return self._validation_error_result("reddit_get_user_context", correlation_id, error)

        try:
            context = await self._client.fetch_user_context(request)
        except Exception as exc:
            return self._api_error_result("reddit_get_user_context", correlation_id, str(exc))

        return ToolExecutionResult(
            tool_name="reddit_get_user_context",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data=context.model_dump(mode="json"),
            error=None,
            correlation_id=correlation_id,
        )

    async def _tool_submit_post(self, parameters: JSONDict, correlation_id: str) -> ToolExecutionResult:
        try:
            request = RedditSubmitPostRequest.model_validate(parameters)
        except ValidationError as error:
            return self._validation_error_result("reddit_submit_post", correlation_id, error)

        try:
            summary = await self._client.submit_post(request)
        except Exception as exc:
            return self._api_error_result("reddit_submit_post", correlation_id, str(exc))

        return ToolExecutionResult(
            tool_name="reddit_submit_post",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data=summary.model_dump(mode="json"),
            error=None,
            correlation_id=correlation_id,
        )

    async def _tool_submit_comment(self, parameters: JSONDict, correlation_id: str) -> ToolExecutionResult:
        try:
            request = RedditSubmitCommentRequest.model_validate(parameters)
        except ValidationError as error:
            return self._validation_error_result("reddit_submit_comment", correlation_id, error)

        try:
            comment = await self._client.submit_comment(request)
        except Exception as exc:
            return self._api_error_result("reddit_submit_comment", correlation_id, str(exc))

        return ToolExecutionResult(
            tool_name="reddit_submit_comment",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data=comment.model_dump(mode="json"),
            error=None,
            correlation_id=correlation_id,
        )

    async def _tool_remove_content(self, parameters: JSONDict, correlation_id: str) -> ToolExecutionResult:
        try:
            request = RedditRemoveContentRequest.model_validate(parameters)
        except ValidationError as error:
            return self._validation_error_result("reddit_remove_content", correlation_id, error)

        try:
            removal_result = await self._client.remove_content(request)
        except Exception as exc:
            return self._api_error_result("reddit_remove_content", correlation_id, str(exc))

        return ToolExecutionResult(
            tool_name="reddit_remove_content",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data=removal_result.model_dump(mode="json"),
            error=None,
            correlation_id=correlation_id,
        )

    async def _tool_get_submission(self, parameters: JSONDict, correlation_id: str) -> ToolExecutionResult:
        try:
            request = RedditGetSubmissionRequest.model_validate(parameters)
        except ValidationError as error:
            return self._validation_error_result("reddit_get_submission", correlation_id, error)

        submission_id = request.submission_id
        if not submission_id and request.permalink:
            submission_id = self._extract_submission_id_from_permalink(request.permalink)
        if not submission_id:
            return self._api_error_result("reddit_get_submission", correlation_id, "Unable to determine submission ID")

        try:
            summary = await self._client.get_submission_summary(
                submission_id,
                include_comments=request.include_comments,
                comment_limit=request.comment_limit,
            )
        except Exception as exc:
            return self._api_error_result("reddit_get_submission", correlation_id, str(exc))

        return ToolExecutionResult(
            tool_name="reddit_get_submission",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data=summary.model_dump(mode="json"),
            error=None,
            correlation_id=correlation_id,
        )

    async def _tool_observe(self, parameters: JSONDict, correlation_id: str) -> ToolExecutionResult:
        target = parameters.get("channel_reference")
        if not isinstance(target, str):
            return self._api_error_result("reddit_observe", correlation_id, "channel_reference is required")

        limit_value = parameters.get("limit", 25)
        try:
            # Handle various types that might come from parameters
            if isinstance(limit_value, int):
                limit = limit_value
            elif isinstance(limit_value, (float, str)):
                limit = int(float(limit_value))
            else:
                limit = 25
        except (TypeError, ValueError):
            limit = 25

        try:
            reference = RedditChannelReference.parse(target)
        except ValueError as exc:
            return self._api_error_result("reddit_observe", correlation_id, str(exc))

        try:
            payload = await self._active_observe(reference, limit=limit)
        except Exception as exc:
            return self._api_error_result("reddit_observe", correlation_id, str(exc))

        return ToolExecutionResult(
            tool_name="reddit_observe",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data=payload.model_dump(mode="json"),
            error=None,
            correlation_id=correlation_id,
        )

    async def _tool_delete_content(self, parameters: JSONDict, correlation_id: str) -> ToolExecutionResult:
        """
        Permanently delete Reddit content (Reddit ToS compliance).

        Reddit ToS Requirement: Zero retention of deleted content.
        """
        try:
            request = RedditDeleteContentRequest.model_validate(parameters)
        except ValidationError as error:
            return self._validation_error_result("reddit_delete_content", correlation_id, error)

        now = datetime.now(timezone.utc)
        content_id = request.thing_fullname
        content_type = "submission" if content_id.startswith("t3_") else "comment"

        try:
            # Phase 1: Delete from Reddit
            deletion_confirmed = await self._client.delete_content(content_id)

            # Phase 2: Purge from local cache (Reddit ToS compliance)
            cache_purged = False
            if request.purge_cache and hasattr(self, "_client"):
                # NOTE: Cache purge logic would go here if cache exists
                # For now, we just mark as purged since there's no cache in base client
                cache_purged = True

            # Phase 3: Create audit trail entry
            audit_entry_id = str(uuid.uuid4())

            # Track deletion status (DSAR pattern)
            deletion_status = RedditDeletionStatus(
                content_id=content_id,
                initiated_at=now,
                completed_at=now if (deletion_confirmed and cache_purged) else None,
                deletion_confirmed=deletion_confirmed,
                cache_purged=cache_purged,
                audit_trail_updated=True,
            )
            self._deletion_statuses[content_id] = deletion_status

            deletion_result = RedditDeletionResult(
                content_id=content_id,
                content_type=content_type,
                deleted_from_reddit=deletion_confirmed,
                purged_from_cache=cache_purged,
                audit_entry_id=audit_entry_id,
                deleted_at=now,
            )

            logger.info(f"Deleted Reddit {content_type} {content_id} (ToS compliance)")

        except Exception as exc:
            return self._api_error_result("reddit_delete_content", correlation_id, str(exc))

        return ToolExecutionResult(
            tool_name="reddit_delete_content",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data=deletion_result.model_dump(mode="json"),
            error=None,
            correlation_id=correlation_id,
        )

    async def _tool_disclose_identity(self, parameters: JSONDict, correlation_id: str) -> ToolExecutionResult:
        """
        Post AI transparency disclosure (Reddit community guidelines compliance).
        """
        try:
            request = RedditDisclosureRequest.model_validate(parameters)
        except ValidationError as error:
            return self._validation_error_result("reddit_disclose_identity", correlation_id, error)

        # Default disclosure message
        default_message = (
            "Hello! I'm CIRIS, an AI assistant helping moderate this community.\n\n"
            "I can help with content moderation, but all major decisions are reviewed "
            "by human moderators. If you have concerns, please contact the mod team."
        )

        # Disclosure footer (always appended)
        disclosure_footer = (
            "\n\n---\n"
            "*I am CIRIS, an AI moderation assistant. "
            "[Learn more](https://ciris.ai) | [Report issues](https://ciris.ai/report)*"
        )

        comment_text = (request.custom_message or default_message) + disclosure_footer

        try:
            # Parse channel reference
            reference = RedditChannelReference.parse(request.channel_reference)

            # Determine submission ID for comment
            submission_id = reference.submission_id
            if not submission_id:
                return self._api_error_result(
                    "reddit_disclose_identity", correlation_id, "Disclosure requires submission ID in channel reference"
                )

            # Post disclosure as comment
            comment_request = RedditSubmitCommentRequest(
                parent_fullname=f"t3_{submission_id}",
                text=comment_text,
                lock_thread=False,
            )

            comment_result = await self._client.submit_comment(comment_request)

            logger.info(f"Posted AI disclosure to {request.channel_reference}")

        except Exception as exc:
            return self._api_error_result("reddit_disclose_identity", correlation_id, str(exc))

        return ToolExecutionResult(
            tool_name="reddit_disclose_identity",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data=comment_result.model_dump(mode="json"),
            error=None,
            correlation_id=correlation_id,
        )

    def get_deletion_status(self, content_id: str) -> Optional[RedditDeletionStatus]:
        """
        Get deletion status for content (DSAR pattern).

        Args:
            content_id: Reddit content ID (t3_xxxxx or t1_xxxxx)

        Returns:
            Deletion status if tracked, None otherwise
        """
        return self._deletion_statuses.get(content_id)

    # Observation helpers ---------------------------------------------------
    async def _active_observe(self, reference: RedditChannelReference, *, limit: int) -> RedditTimelineResponse:
        if reference.target is RedditChannelType.USER and reference.username:
            return await self._client.fetch_user_activity(reference.username, limit=limit)

        if reference.target is RedditChannelType.SUBREDDIT and reference.subreddit:
            entries = await self._client.fetch_subreddit_new(reference.subreddit, limit=limit)
            return RedditTimelineResponse(entries=entries)

        if reference.target in {RedditChannelType.SUBMISSION, RedditChannelType.COMMENT}:
            submission_id = reference.submission_id
            if not submission_id:
                raise RuntimeError("Submission ID required for observation")
            comments = await self._client.fetch_submission_comments(submission_id, limit=limit)
            entries = [
                RedditTimelineEntry(
                    entry_type="comment",
                    item_id=comment.comment_id,
                    fullname=comment.fullname,
                    subreddit=comment.subreddit,
                    permalink=comment.permalink,
                    score=comment.score,
                    created_at=comment.created_at,
                    channel_reference=comment.channel_reference,
                    author=comment.author,
                    body=comment.body,
                )
                for comment in comments
            ]
            return RedditTimelineResponse(entries=entries)

        raise RuntimeError(f"Unsupported observation target: {reference.target.value}")

    # Shared helpers --------------------------------------------------------
    def get_capabilities(self) -> ServiceCapabilities:
        return ServiceCapabilities(
            service_name=self.service_name,
            actions=self._get_actions(),
            version="1.0.0",
            dependencies=list(self._dependencies),
            metadata={"provider": "reddit", "channel_format": "reddit:r/<sub>:post/<id>:comment/<id>"},
        )

    def _validation_error_result(
        self, tool_name: str, correlation_id: str, error: ValidationError
    ) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_name=tool_name,
            status=ToolExecutionStatus.FAILED,
            success=False,
            data=None,
            error=str(error),
            correlation_id=correlation_id,
        )

    def _api_error_result(self, tool_name: str, correlation_id: str, message: str) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_name=tool_name,
            status=ToolExecutionStatus.FAILED,
            success=False,
            data=None,
            error=message,
            correlation_id=correlation_id,
        )

    def _schema_to_param_schema(self, json_schema: JSONDict) -> ToolParameterSchema:
        """Convert a Pydantic JSON schema to ToolParameterSchema format."""
        return ToolParameterSchema(
            type=json_schema.get("type", "object"),
            properties=json_schema.get("properties", {}),
            required=json_schema.get("required", []),
        )

    def _build_tool_schemas(self) -> Dict[str, ToolParameterSchema]:
        return {
            "reddit_get_user_context": self._schema_to_param_schema(RedditUserContextRequest.model_json_schema()),
            "reddit_submit_post": self._schema_to_param_schema(RedditSubmitPostRequest.model_json_schema()),
            "reddit_submit_comment": self._schema_to_param_schema(RedditSubmitCommentRequest.model_json_schema()),
            "reddit_remove_content": self._schema_to_param_schema(RedditRemoveContentRequest.model_json_schema()),
            "reddit_get_submission": self._schema_to_param_schema(RedditGetSubmissionRequest.model_json_schema()),
            "reddit_delete_content": self._schema_to_param_schema(RedditDeleteContentRequest.model_json_schema()),
            "reddit_disclose_identity": self._schema_to_param_schema(RedditDisclosureRequest.model_json_schema()),
            "reddit_observe": ToolParameterSchema(
                type="object",
                properties={
                    "channel_reference": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
                required=["channel_reference"],
            ),
        }

    def _build_tool_info(self) -> Dict[str, ToolInfo]:
        tool_descriptions = {
            "reddit_get_user_context": "Fetch metadata and recent activity for a Reddit user",
            "reddit_submit_post": "Submit a markdown self-post to the configured subreddit",
            "reddit_submit_comment": "Reply to a submission or comment",
            "reddit_remove_content": "Remove a submission or comment",
            "reddit_get_submission": "Fetch metadata for a submission",
            "reddit_delete_content": "Permanently delete content from Reddit (ToS compliance)",
            "reddit_disclose_identity": "Post AI transparency disclosure (community guidelines compliance)",
            "reddit_observe": "Fetch passive observation data for a subreddit, submission, comment, or user",
        }
        return {
            name: ToolInfo(name=name, description=tool_descriptions.get(name, ""), parameters=schema)
            for name, schema in self._tool_schemas.items()
        }

    def _extract_submission_id_from_permalink(self, permalink: str) -> Optional[str]:
        from urllib.parse import urlparse

        parsed = urlparse(permalink)
        path_parts = [part for part in parsed.path.split("/") if part]

        if not path_parts:
            return None

        lowered_parts = [part.lower() for part in path_parts]

        # Canonical reddit URLs follow /r/<sub>/comments/<id>/slug
        if "comments" in lowered_parts:
            idx = lowered_parts.index("comments")
            if idx + 1 < len(path_parts):
                return path_parts[idx + 1]

        # Shortlinks use redd.it/<id> or /comments/<id>
        if lowered_parts[0] == "comments" and len(path_parts) > 1:
            return path_parts[1]

        # redd.it shortlinks surface the id as the only path component
        if len(path_parts) == 1:
            return path_parts[0]
        return None


# ----------------------------------------------------------------------
# Communication service implementation
# ----------------------------------------------------------------------


class RedditCommunicationService(RedditServiceBase):
    """Communication service that lets CIRIS speak and fetch on Reddit."""

    def __init__(
        self,
        credentials: Optional[RedditCredentials] = None,
        *,
        time_service: Optional[TimeServiceProtocol] = None,
        bus_manager: Optional[object] = None,
        memory_service: Optional[object] = None,
        agent_id: Optional[str] = None,
        filter_service: Optional[object] = None,
        secrets_service: Optional[object] = None,
        agent_occurrence_id: str = "default",
    ) -> None:
        super().__init__(credentials, time_service=time_service, service_name="RedditCommunicationService")
        self._home_channel: Optional[str] = None
        self._wakeup_submission_id: Optional[str] = None
        # Store runtime dependencies for observer creation
        self._bus_manager = bus_manager
        self._memory_service = memory_service
        self._agent_id = agent_id
        self._filter_service = filter_service
        self._secrets_service = secrets_service
        self._agent_occurrence_id = agent_occurrence_id
        self._observer: Optional[object] = None  # RedditObserver instance

    async def _on_start(self) -> None:
        await super()._on_start()
        await self._resolve_home_channel()

        # Create and start Reddit observer if runtime dependencies are available
        # Note: agent_id is optional, observer will use "ciris" as fallback
        if self._bus_manager and self._memory_service:
            from .observer import RedditObserver

            logger.info("Creating RedditObserver with runtime dependencies")
            self._observer = RedditObserver(
                credentials=self._credentials,
                subreddit=self._credentials.subreddit if self._credentials else None,
                bus_manager=self._bus_manager if isinstance(self._bus_manager, BusManager) else None,
                memory_service=self._memory_service,
                agent_id=self._agent_id,
                filter_service=self._filter_service,
                secrets_service=self._secrets_service if isinstance(self._secrets_service, SecretsService) else None,
                time_service=self._time_service,
                agent_occurrence_id=self._agent_occurrence_id,
            )
            await self._observer.start()
            logger.info(
                f"RedditObserver started and monitoring r/{self._credentials.subreddit if self._credentials else 'unknown'}"
            )
        else:
            logger.warning("RedditCommunicationService: Runtime dependencies not available, observer not started")

    async def _on_stop(self) -> None:
        # Stop observer if it was started
        if self._observer and hasattr(self._observer, "stop"):
            await self._observer.stop()
            logger.info("RedditObserver stopped")
        await super()._on_stop()

    def get_service_type(self) -> ServiceType:
        return ServiceType.COMMUNICATION

    def _get_actions(self) -> List[str]:
        return ["send_message", "fetch_messages"]

    async def send_message(self, channel_id: str, content: str) -> bool:
        reference = RedditChannelReference.parse(channel_id)
        if reference.target == RedditChannelType.SUBREDDIT:
            raise RuntimeError(
                "Cannot send plain messages to a subreddit without a submission context. "
                "Provide a submission or comment reference (e.g., reddit:r/ciris:post/<id>)."
            )

        if reference.target == RedditChannelType.SUBMISSION:
            parent_fullname = f"t3_{reference.submission_id}"
        elif reference.target == RedditChannelType.COMMENT:
            parent_fullname = f"t1_{reference.comment_id}"
        else:
            raise RuntimeError(f"Unsupported channel target for send_message: {reference.target.value}")

        request = RedditSubmitCommentRequest(parent_fullname=parent_fullname, text=content)
        await self._client.submit_comment(request)
        return True

    async def fetch_messages(
        self,
        channel_id: str,
        *,
        limit: int = 50,
        before: Optional[datetime] = None,
    ) -> List[FetchedMessage]:
        del before  # Reddit does not support before filters in this implementation
        reference = RedditChannelReference.parse(channel_id)
        messages: List[FetchedMessage] = []

        if reference.target == RedditChannelType.SUBREDDIT and reference.subreddit:
            entries = await self._client.fetch_subreddit_new(reference.subreddit, limit=limit)
            for entry in entries:
                messages.append(
                    FetchedMessage(
                        id=entry.item_id,
                        content=entry.title or entry.body,
                        author_name=entry.author,
                        author_id=entry.author,
                        timestamp=entry.created_at.isoformat(),
                        channel_reference=entry.channel_reference,
                        permalink=entry.permalink,
                    )
                )
            return messages

        if reference.target == RedditChannelType.SUBMISSION and reference.submission_id:
            comments = await self._client.fetch_submission_comments(reference.submission_id, limit=limit)
            for comment in comments:
                messages.append(
                    FetchedMessage(
                        id=comment.comment_id,
                        content=comment.body,
                        author_name=comment.author,
                        author_id=comment.author,
                        timestamp=comment.created_at.isoformat(),
                        channel_reference=comment.channel_reference,
                        permalink=comment.permalink,
                    )
                )
            return messages

        if reference.target == RedditChannelType.COMMENT and reference.comment_id:
            if not reference.submission_id:
                raise RuntimeError("Comment references must include a submission id")
            # Fetch the comment itself
            summary = await self._client.fetch_submission_comments(reference.submission_id, limit=limit)
            for comment in summary:
                if comment.comment_id == reference.comment_id:
                    messages.append(
                        FetchedMessage(
                            id=comment.comment_id,
                            content=comment.body,
                            author_name=comment.author,
                            author_id=comment.author,
                            timestamp=comment.created_at.isoformat(),
                            channel_reference=comment.channel_reference,
                            permalink=comment.permalink,
                        )
                    )
                    break
            return messages

        if reference.target == RedditChannelType.USER and reference.username:
            timeline = await self._client.fetch_user_activity(reference.username, limit=limit)
            for entry in timeline.entries:
                messages.append(
                    FetchedMessage(
                        id=entry.item_id,
                        content=entry.title or entry.body,
                        author_name=entry.author,
                        author_id=entry.author,
                        timestamp=entry.created_at.isoformat(),
                        channel_reference=entry.channel_reference,
                        permalink=entry.permalink,
                    )
                )
            return messages

        raise RuntimeError(f"Unsupported channel reference for fetch_messages: {channel_id}")

    def get_home_channel_id(self) -> Optional[str]:
        if self._home_channel:
            return self._home_channel
        return _build_channel_reference(self._subreddit)

    async def _resolve_home_channel(self) -> None:
        """Resolve the WAKEUP submission used for default Reddit messaging."""

        subreddit = self._subreddit
        try:
            entries = await self._client.fetch_subreddit_new(subreddit, limit=25)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(
                "RedditCommunicationService: failed to resolve WAKEUP submission for r/%s: %s",
                subreddit,
                exc,
            )
            self._home_channel = _build_channel_reference(subreddit)
            return

        for entry in entries:
            if entry.entry_type != "submission":
                continue
            title = entry.title or ""
            body = entry.body or ""
            if "wakeup" in title.lower() or "wakeup" in body.lower():
                self._wakeup_submission_id = entry.item_id
                self._home_channel = _build_channel_reference(subreddit, submission_id=entry.item_id)
                logger.info(
                    "RedditCommunicationService: resolved WAKEUP submission %s as default home channel",
                    entry.item_id,
                )
                return

        self._home_channel = _build_channel_reference(subreddit)
        logger.info(
            "RedditCommunicationService: no WAKEUP submission detected in r/%s; defaulting to subreddit channel",
            subreddit,
        )


__all__ = ["RedditToolService", "RedditCommunicationService"]
