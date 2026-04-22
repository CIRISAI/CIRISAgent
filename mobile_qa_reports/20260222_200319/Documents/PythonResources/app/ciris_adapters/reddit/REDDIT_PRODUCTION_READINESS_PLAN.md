# Reddit Module Production Readiness Plan

**Status**: 🟡 NOT PRODUCTION-READY
**Current Version**: 1.0 (1,900 lines implemented)
**Target Version**: 1.1 (Production-ready)

---

## Implementation Status

### ✅ Complete Features (1,900 lines)
- **Reddit API Integration**: Custom httpx-based client (no PRAW dependency)
- **OAuth2 Authentication**: Password grant flow with async token refresh
- **Rate Limiting**: 429 handling with Retry-After parsing
- **Content Moderation**: 6 tools (remove, post, comment, lookup, fetch, observe)
- **Channel References**: Canonical format (reddit:r/sub:post/id:comment/id)
- **Type Safety**: 15+ Pydantic models with ~95% type coverage
- **Async/Await**: Non-blocking I/O throughout
- **Error Handling**: Comprehensive logging and recovery
- **Bot Identification**: User-agent "CIRIS-RedditAdapter/1.0 (+https://ciris.ai)"

### ⚠️ Partial Features
- **Data Retention**: Token expiration + 500-item cache limit, but no deletion webhook
- **Transparency**: Bot identified in user-agent, but no programmatic disclosure tool

### ❌ Missing Features (Blocking Production)
1. **Test Coverage** - 0 tests (BLOCKING)
2. **Deletion Compliance** - No Reddit-aware deletion tools (CRITICAL)
3. **Transparency Tool** - No disclosure mechanism (REQUIRED)
4. **Moderation Queue** - Cannot fetch reported content

---

## Gap Analysis by Priority

### 🚨 P0: Test Suite (BLOCKING)

**Current State**: 0 dedicated test files for Reddit adapter

**Required Coverage**:
```
tests/reddit/
├── test_reddit_api_client.py         # OAuth, rate limiting, API calls
├── test_reddit_tool_service.py       # Tool execution, validation
├── test_reddit_communication_service.py  # Message handling, WAKEUP
└── test_reddit_deletion_compliance.py    # Deletion tools, cache purge
```

**Test Requirements**:
- Validate bot user-agent present in all requests
- Verify OAuth2 token refresh logic
- Test rate limit 429 handling with Retry-After
- Ensure deleted content not cached
- Test removal tools (submissions + comments)
- Validate channel reference parsing
- Test WAKEUP discovery mechanism

---

### 🔴 P1: Reddit Deletion Compliance (CRITICAL)

**Current State**: Can remove via API, but no auto-deletion or retention policy

**Reddit ToS Requirement**:
> "ZERO retention of deleted content" - Even if de-identified or anonymized

**Existing Framework**: DSAR Automation Service provides deletion pattern

**Location**: `ciris_engine/logic/services/governance/consent/dsar_automation.py`

**Key Pattern to Adopt**:
```python
# From DSAR service (lines 297-367)
async def get_deletion_status(self, user_id: str, ticket_id: str) -> Optional[DSARDeletionStatus]:
    """Get status of DSAR deletion request (linked to decay protocol)."""

    # Check decay protocol status
    decay_status = self._consent_service._decay_manager.check_decay_status(user_id)

    # Track deletion progress with milestones
    # Return status with completion percentage
```

**Also see**: `ciris_engine/logic/services/governance/consent/decay.py`
- `initiate_decay()` - Start deletion protocol
- `check_decay_status()` - Query deletion status
- `get_decay_progress()` - Get completion percentage

#### Required Implementation

**1. Reddit Content Deletion Tools** (`service.py:+60 lines`)

```python
async def reddit_delete_submission(self, submission_id: str, purge_cache: bool = True) -> dict:
    """
    Permanently delete submission from Reddit and purge local cache.

    Reddit ToS Compliance: Zero retention of deleted content.

    Args:
        submission_id: Reddit submission ID (t3_xxxxx)
        purge_cache: Whether to purge from local cache (default: True)

    Returns:
        Deletion result with audit trail
    """
    # 1. Delete from Reddit via API (DELETE /api/del)
    # 2. Purge from local cache (if purge_cache=True)
    # 3. Log deletion event to audit trail
    # 4. Return deletion status

async def reddit_delete_comment(self, comment_id: str, purge_cache: bool = True) -> dict:
    """
    Permanently delete comment from Reddit and purge local cache.

    Reddit ToS Compliance: Zero retention of deleted content.

    Args:
        comment_id: Reddit comment ID (t1_xxxxx)
        purge_cache: Whether to purge from local cache (default: True)

    Returns:
        Deletion result with audit trail
    """
    # 1. Delete from Reddit via API (DELETE /api/del)
    # 2. Purge from local cache (if purge_cache=True)
    # 3. Log deletion event to audit trail
    # 4. Return deletion status
```

**2. Auto-Purge on Deletion Detection** (`observer.py:+40 lines`)

```python
async def _check_content_deleted(self, submission_id: str) -> bool:
    """Check if submission has been deleted on Reddit."""
    try:
        submission = await self._api_client.get_submission(submission_id)
        return submission.get("removed_by_category") is not None
    except Exception:
        return True  # Assume deleted if unreachable

async def _purge_deleted_content(self, submission_id: str) -> None:
    """Purge deleted content from local cache (Reddit ToS compliance)."""
    # Remove from submission cache
    if submission_id in self._submission_cache:
        del self._submission_cache[submission_id]
        logger.info(f"Purged deleted submission {submission_id} from cache (ToS compliance)")

    # Log purge event to audit trail
    audit_event = {
        "event": "reddit_content_purged",
        "submission_id": submission_id,
        "reason": "reddit_tos_compliance",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    logger.audit(audit_event)
```

**3. Deletion Event Schema** (`schemas.py:+30 lines`)

```python
class RedditDeletionResult(BaseModel):
    """Result of Reddit content deletion."""
    content_id: str
    content_type: Literal["submission", "comment"]
    deleted_from_reddit: bool
    purged_from_cache: bool
    audit_entry_id: str
    deleted_at: datetime

class RedditDeletionStatus(BaseModel):
    """Status of Reddit content deletion tracking."""
    content_id: str
    initiated_at: datetime
    completed_at: Optional[datetime] = None
    deletion_confirmed: bool
    cache_purged: bool
    audit_trail_updated: bool
```

#### Adoption of DSAR Pattern

**Key Learnings from DSAR Service**:

1. **Deletion is NOT instant** - Track as a process with status
2. **Audit trail is mandatory** - Every deletion logged
3. **Multiple phases** - Deletion, purge, verification
4. **Status queries** - Provide deletion status endpoint

**Reddit-Specific Adaptation**:
```python
# Similar to DSAR's get_deletion_status()
async def get_reddit_deletion_status(self, content_id: str) -> RedditDeletionStatus:
    """
    Get status of Reddit content deletion.

    Args:
        content_id: Reddit content ID (t3_xxxxx or t1_xxxxx)

    Returns:
        Deletion status with cache purge confirmation
    """
    # Check if deleted from Reddit
    deleted_from_reddit = await self._check_content_deleted(content_id)

    # Check if purged from cache
    cache_purged = content_id not in self._submission_cache

    # Check audit trail
    audit_trail_updated = True  # Query audit service

    return RedditDeletionStatus(
        content_id=content_id,
        initiated_at=...,  # From audit trail
        completed_at=... if deleted_from_reddit and cache_purged else None,
        deletion_confirmed=deleted_from_reddit,
        cache_purged=cache_purged,
        audit_trail_updated=audit_trail_updated,
    )
```

---

### 🔴 P1: Transparency Disclosure Tool (REQUIRED)

**Current State**: Bot identified in user-agent, but no programmatic disclosure

**Reddit Community Guidelines Requirement**:
> "Clear AI disclosure in all interactions"

#### Required Implementation

**1. Disclosure Tool** (`service.py:+50 lines`)

```python
DISCLOSURE_FOOTER = """

---
*I am CIRIS, an AI moderation assistant. [Learn more](https://ciris.ai) | [Report issues](https://ciris.ai/report)*
"""

async def reddit_disclose_identity(self, channel_ref: str, custom_message: Optional[str] = None) -> dict:
    """
    Post AI disclosure comment to specified thread.

    Reddit Community Guidelines Compliance: Clear AI disclosure.

    Args:
        channel_ref: Channel reference (reddit:r/sub:post/id)
        custom_message: Optional custom disclosure message

    Returns:
        Comment result with disclosure confirmation
    """
    default_message = (
        "Hello! I'm CIRIS, an AI assistant helping moderate this community.\n\n"
        "I can help with content moderation, but all major decisions are reviewed "
        "by human moderators. If you have concerns, please contact the mod team."
    )

    comment_text = (custom_message or default_message) + DISCLOSURE_FOOTER

    # Post disclosure comment
    result = await self.reddit_comment(channel_ref, comment_text)

    # Log disclosure event
    logger.info(f"Posted AI disclosure to {channel_ref}")

    return result

async def reddit_comment_with_disclosure(
    self, channel_ref: str, text: str, append_footer: bool = True
) -> dict:
    """
    Post comment with optional disclosure footer.

    Args:
        channel_ref: Channel reference
        text: Comment text
        append_footer: Whether to append disclosure footer (default: True)

    Returns:
        Comment result
    """
    comment_text = text + (DISCLOSURE_FOOTER if append_footer else "")
    return await self.reddit_comment(channel_ref, comment_text)
```

**2. Tool Registration** (`service.py:700-750`)

Add to tool list:
```python
ToolInfo(
    name="reddit_disclose_identity",
    description="Post AI disclosure comment to thread (community guidelines compliance)",
    parameters=[
        ToolParameterSchema(
            name="channel_ref",
            type="string",
            description="Channel reference (reddit:r/sub:post/id)",
            required=True,
        ),
        ToolParameterSchema(
            name="custom_message",
            type="string",
            description="Optional custom disclosure message",
            required=False,
        ),
    ],
)
```

---

### 🟡 P2: Moderation Queue Support

**Current State**: Cannot fetch reported content from modqueue

**Current Tools**:
- ✅ `reddit_remove` - Remove posts/comments
- ✅ `reddit_fetch_submission` - Get specific submission
- ❌ `reddit_fetch_modqueue` - NOT IMPLEMENTED
- ❌ `reddit_fetch_reports` - NOT IMPLEMENTED
- ❌ `reddit_approve` - NOT IMPLEMENTED

#### Required Implementation

**1. Moderation Queue Tools** (`service.py:+100 lines`)

```python
async def reddit_fetch_modqueue(self, limit: int = 25) -> dict:
    """
    Fetch items from moderation queue.

    Args:
        limit: Maximum items to fetch (1-100)

    Returns:
        List of modqueue items with metadata
    """
    # GET /r/{subreddit}/about/modqueue

async def reddit_fetch_reports(self, limit: int = 25) -> dict:
    """
    Fetch reported posts/comments.

    Args:
        limit: Maximum items to fetch (1-100)

    Returns:
        List of reported items with report reasons
    """
    # GET /r/{subreddit}/about/reports

async def reddit_approve(self, thing_id: str, reason: Optional[str] = None) -> dict:
    """
    Approve a post/comment (remove from modqueue).

    Args:
        thing_id: Reddit thing ID (t3_xxxxx or t1_xxxxx)
        reason: Optional approval reason

    Returns:
        Approval result
    """
    # POST /api/approve
```

**2. Modqueue Schemas** (`schemas.py:+40 lines`)

```python
class RedditModqueueItem(BaseModel):
    """Item in moderation queue."""
    thing_id: str
    thing_type: Literal["submission", "comment"]
    author: str
    subreddit: str
    created_utc: int
    report_count: int
    report_reasons: List[str]
    content: str

class RedditModqueueResponse(BaseModel):
    """Response from modqueue fetch."""
    items: List[RedditModqueueItem]
    fetched_at: datetime
    count: int
```

---

## Implementation Checklist

### Phase 1: Test Coverage (BLOCKING)
- [ ] Create `tests/reddit/` directory structure
- [ ] Implement `test_reddit_api_client.py` (OAuth, rate limiting)
- [ ] Implement `test_reddit_tool_service.py` (tool execution)
- [ ] Implement `test_reddit_communication_service.py` (message handling)
- [ ] Implement `test_reddit_deletion_compliance.py` (deletion tools)
- [ ] Achieve 80%+ test coverage for Reddit module
- [ ] All tests passing

### Phase 2: Deletion Compliance (CRITICAL)
- [ ] Implement `reddit_delete_submission()` tool
- [ ] Implement `reddit_delete_comment()` tool
- [ ] Add `_check_content_deleted()` to observer
- [ ] Add `_purge_deleted_content()` to observer
- [ ] Create `RedditDeletionResult` schema
- [ ] Create `RedditDeletionStatus` schema
- [ ] Add deletion event to audit trail integration
- [ ] Write deletion compliance tests
- [ ] Document Reddit ToS compliance in README

### Phase 3: Transparency Tool (REQUIRED)
- [ ] Implement `reddit_disclose_identity()` tool
- [ ] Implement `reddit_comment_with_disclosure()` helper
- [ ] Add `DISCLOSURE_FOOTER` constant
- [ ] Register transparency tool in tool list
- [ ] Write transparency tests
- [ ] Document community guidelines compliance

### Phase 4: Moderation Queue (OPTIONAL)
- [ ] Implement `reddit_fetch_modqueue()` tool
- [ ] Implement `reddit_fetch_reports()` tool
- [ ] Implement `reddit_approve()` tool
- [ ] Create `RedditModqueueItem` schema
- [ ] Create `RedditModqueueResponse` schema
- [ ] Write modqueue tests

### Phase 5: Production Validation
- [ ] Run full test suite (target: 80%+ coverage)
- [ ] Validate Reddit API ToS compliance
- [ ] Validate community guidelines compliance
- [ ] Load testing (rate limit validation)
- [ ] Security audit (OAuth token handling)
- [ ] Documentation review
- [ ] Deployment runbook creation

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| **No test coverage** | HIGH - Cannot validate compliance | Phase 1 test suite |
| **Deleted content retained** | CRITICAL - Reddit ToS violation | Phase 2 deletion tools |
| **No AI disclosure** | HIGH - Community guideline violation | Phase 3 transparency |
| **Rate limit exceeded** | MEDIUM - API access blocked | Existing 429 handling |
| **OAuth token leak** | HIGH - Account compromise | Secure secrets management |

---

## Success Criteria

### Production Readiness Gates

1. ✅ **Test Coverage** ≥ 80% for Reddit module
2. ✅ **Deletion Compliance** - All deletion tests passing
3. ✅ **Transparency** - Disclosure tool implemented and tested
4. ✅ **Reddit ToS** - Compliance validated by legal review
5. ✅ **Community Guidelines** - Disclosure mechanism verified
6. ✅ **Performance** - Rate limit handling validated under load

### Documentation Requirements

- [x] README.md updated with deletion compliance
- [ ] Community guidelines compliance documented
- [ ] Deployment runbook with Reddit API setup
- [ ] Troubleshooting guide for common Reddit API errors
- [ ] Security best practices for OAuth credentials

---

## Estimated Effort (Developer Days)

| Phase | Effort |
|-------|--------|
| Phase 1: Test Coverage | 2-3 days |
| Phase 2: Deletion Compliance | 1-2 days |
| Phase 3: Transparency Tool | 0.5-1 day |
| Phase 4: Moderation Queue | 1-2 days |
| Phase 5: Production Validation | 1-2 days |
| **Total** | **5.5-10 days** |

---

## Next Steps

1. **Immediate**: Create test suite (Phase 1) - BLOCKING
2. **Critical**: Implement deletion compliance (Phase 2) - Reddit ToS requirement
3. **Required**: Add transparency tool (Phase 3) - Community guidelines
4. **Optional**: Add moderation queue (Phase 4) - Feature enhancement

---

## References

### Existing Framework
- **DSAR Service**: `ciris_engine/logic/services/governance/consent/dsar_automation.py`
- **Decay Protocol**: `ciris_engine/logic/services/governance/consent/decay.py`
- **Deletion Pattern**: Lines 297-367 (get_deletion_status)

### Reddit Module
- **Service**: `ciris_adapters/reddit/service.py` (1,188 lines)
- **Schemas**: `ciris_adapters/reddit/schemas.py` (356 lines)
- **Observer**: `ciris_adapters/reddit/observer.py` (162 lines)
- **Protocol**: `ciris_adapters/reddit/protocol.py`
- **README**: `ciris_adapters/reddit/README.md`

### External Documentation
- **Reddit API Terms**: https://www.reddit.com/wiki/api
- **Reddit Community Guidelines**: https://www.reddit.com/r/ciris (to be created)
- **OAuth2 Documentation**: https://github.com/reddit-archive/reddit/wiki/OAuth2

---

*Last Updated*: 2025-10-28
*Status*: Draft - Awaiting implementation
