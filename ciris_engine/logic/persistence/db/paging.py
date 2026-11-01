"""Following persist's cursor pages.

Every persist list page (NodeListPage, AuditListPage, TicketListPage, ...)
carries its continuation as `next_cursor`: a cursor OBJECT, absent on the last
page. The next request takes that object back, JSON-encoded, as its
`cursor_json` argument.

2.18.0 had three hand-rolled readings of that contract, two of them wrong:
- `{"cursor": next_cursor}`: persist rejects it ("ListCursor decode: missing
  field `version`"), so the graph scope-walk failed past its first page.
- `page["cursor"]`: a field no page has, so audit listings, the data export,
  memory queries and cross-channel history silently stopped after one page.
"""

from __future__ import annotations

import json
from typing import Any, Optional


def next_page_cursor(page: Any) -> Optional[str]:
    """The `cursor_json` for the page after `page`, or None when `page` was the last."""
    if not isinstance(page, dict):
        return None
    cursor = page.get("next_cursor")
    if cursor is None:
        cursor = page.get("cursor")  # tolerated: no current persist page uses it
    if not cursor:
        return None
    return cursor if isinstance(cursor, str) else json.dumps(cursor)
