"""
Pagination utilities for CIRIS SDK.

Provides standardized cursor-based pagination for all list endpoints.
"""

import base64
import json
import logging
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class CursorInfo(BaseModel):
    """Decoded cursor information."""

    offset: int = Field(0, description="Current offset")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Applied filters")
    sort_key: Optional[str] = Field(None, description="Sort field")
    sort_value: Optional[Any] = Field(None, description="Last item's sort value")


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Standardized paginated response.

    All list endpoints return data in this format with cursor-based pagination.
    """

    items: List[T] = Field(..., description="List of items in current page")
    total: Optional[int] = Field(None, description="Total count if available")
    cursor: Optional[str] = Field(None, description="Cursor for next page")
    has_more: bool = Field(..., description="Whether more items exist")

    model_config = ConfigDict(arbitrary_types_allowed=True)


class PageIterator(Generic[T]):
    """
    Iterator for paginated results.

    Automatically fetches pages as needed for seamless iteration.
    """

    def __init__(
        self,
        fetch_func: Callable[..., Awaitable[Any]],
        initial_params: Dict[str, Any],
        item_class: type[T],
    ):
        """
        Initialize page iterator.

        Args:
            fetch_func: Async function to fetch a page
            initial_params: Initial query parameters
            item_class: Class for items in the response
        """
        self.fetch_func = fetch_func
        self.params = initial_params.copy()
        self.item_class = item_class
        self._current_page: Optional[PaginatedResponse[T]] = None
        self._current_index = 0
        self._exhausted = False

    async def __aiter__(self) -> AsyncIterator[T]:
        """Async iteration support."""
        while not self._exhausted:
            # Fetch next page if needed
            if self._current_page is None or self._current_index >= len(self._current_page.items):
                await self._fetch_next_page()

                # Check if we're done
                if self._current_page is None or not self._current_page.items:
                    self._exhausted = True
                    break

                self._current_index = 0

            # Yield current item
            yield self._current_page.items[self._current_index]
            self._current_index += 1

    async def _fetch_next_page(self) -> None:
        """Fetch the next page of results."""
        try:
            # Use cursor if we have one
            if self._current_page and self._current_page.cursor:
                self.params["cursor"] = self._current_page.cursor

            # Fetch page
            response = await self.fetch_func(**self.params)

            # Parse response
            if isinstance(response, dict):
                # Type assertion: we know item_class is bound to T
                assert isinstance(self.item_class, type)
                self._current_page = PaginatedResponse[T](**response)
            else:
                self._current_page = response

            # Check if we should continue
            if self._current_page is None or not self._current_page.has_more:
                self._exhausted = True

        except Exception as e:
            logger.error(f"Error fetching page: {e}")
            self._exhausted = True
            raise


def encode_cursor(cursor_info: CursorInfo) -> str:
    """
    Encode cursor information.

    Args:
        cursor_info: Cursor information to encode

    Returns:
        Base64-encoded cursor string
    """
    data = cursor_info.model_dump(exclude_none=True)
    json_str = json.dumps(data, sort_keys=True)
    return base64.urlsafe_b64encode(json_str.encode()).decode()


def decode_cursor(cursor: str) -> CursorInfo:
    """
    Decode cursor string.

    Args:
        cursor: Base64-encoded cursor

    Returns:
        Decoded cursor information
    """
    try:
        json_str = base64.urlsafe_b64decode(cursor.encode()).decode()
        data = json.loads(json_str)
        return CursorInfo(**data)
    except Exception as e:
        logger.error(f"Invalid cursor: {e}")
        # Return default cursor on error
        return CursorInfo()


class PaginationParams(BaseModel):
    """Standard pagination parameters."""

    cursor: Optional[str] = Field(None, description="Cursor for pagination")
    limit: int = Field(50, ge=1, le=200, description="Items per page")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for API calls."""
        return self.model_dump(exclude_none=True)


class QueryParams(PaginationParams):
    """
    Extended query parameters with filtering.

    Base class for resource-specific query parameters.
    """

    # Common filter fields
    since: Optional[str] = Field(None, description="Filter by creation time")
    until: Optional[str] = Field(None, description="Filter by creation time")
    sort: Optional[str] = Field(None, description="Sort field")
    order: Optional[str] = Field("desc", pattern="^(asc|desc)$", description="Sort order")

    # Search
    q: Optional[str] = Field(None, description="Search query")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict, handling special cases."""
        data = super().to_dict()

        # Remove empty strings
        return {k: v for k, v in data.items() if v != ""}


async def paginate_all(
    fetch_func: Callable[..., Awaitable[Any]],
    params: Dict[str, Any],
    item_class: type[T],
    max_items: Optional[int] = None,
) -> List[T]:
    """
    Fetch all pages of a paginated endpoint.

    Args:
        fetch_func: Async function to fetch a page
        params: Query parameters
        item_class: Class for items
        max_items: Maximum items to fetch (None = all)

    Returns:
        List of all items
    """
    all_items = []
    iterator = PageIterator(fetch_func, params, item_class)

    async for item in iterator:
        all_items.append(item)

        if max_items and len(all_items) >= max_items:
            break

    return all_items
