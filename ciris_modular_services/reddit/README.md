# Reddit Adapter Module

The Reddit adapter brings CIRIS onto a dedicated subreddit with the same multi-channel
expectations as the Discord adapter. It exposes tool, communication, and observation
capabilities that allow the agent to speak, listen, and moderate while following
Reddit's platform policies.

## Capabilities

- **Tool service** – structured tools for posting, replying, removals, submission lookups,
  user context, active observation queries (`reddit_observe`), **deletion compliance**
  (`reddit_delete_content`), and **AI transparency disclosure** (`reddit_disclose_identity`).
- **Communication service** – the CommunicationBus can `send_message` and `fetch_messages`
  using canonical channel references such as `reddit:r/ciris:post/abc123` or
  `reddit:r/ciris:post/abc123:comment/def456`.
- **Observer** – a passive observer polls the configured subreddit and produces
  `PassiveObservationResult` entries for new submissions and comments, mirroring the
  Discord adapter's behavior. Includes **auto-purge** for deleted content to maintain
  Reddit ToS compliance.

All components reuse a shared OAuth client with automatic token refresh and Reddit API
rate handling.

## Configuration

Provide credentials through environment variables or the secrets service:

| Variable | Purpose |
| --- | --- |
| `CIRIS_REDDIT_CLIENT_ID` | OAuth client identifier for the Reddit script application |
| `CIRIS_REDDIT_CLIENT_SECRET` | OAuth client secret |
| `CIRIS_REDDIT_USERNAME` | Bot account username |
| `CIRIS_REDDIT_PASSWORD` | Bot account password |
| `CIRIS_REDDIT_USER_AGENT` | Descriptive user agent string that complies with Reddit API policy |
| `CIRIS_REDDIT_SUBREDDIT` | Home subreddit monitored by the observer and used for default posts (defaults to `ciris`) |

These values never leave the adapter and are omitted from logs.

## Channel References

Reddit channel identifiers follow `platform:channel:subchannel` semantics:

- Subreddit: `reddit:r/<subreddit>`
- Submission: `reddit:r/<subreddit>:post/<submission_id>`
- Comment: `reddit:r/<subreddit>:post/<submission_id>:comment/<comment_id>`
- User timeline: `reddit:u/<username>`

The communication service and observer both rely on this format, and tool responses
return the same identifiers for downstream routing.

## Observer Behavior

The `RedditObserver` polls `r/<subreddit>` for new submissions and comments (configurable
interval, default 15s). Each unseen item becomes a `RedditMessage` that is passed through
`BaseObserver`, enabling adaptive filtering, memory recall, and passive observation task
creation identical to the Discord adapter pipeline. Observations include canonical
channel references and permalinks for context reconstruction, and the content is sanitized
with the same anti-spoofing guardrails used by the Discord adapter.

During startup the communication service looks for a WAKEUP announcement inside `r/ciris`
and, when found, treats the submission's comment thread as the adapter's default channel.
This ensures WAKEUP chatter lands inside that post whenever Reddit is the only active
adapter, while higher-priority adapters (such as the API) remain the default SPEAK
destination.

## Reddit ToS and Community Guidelines Compliance

### Deletion Compliance (Reddit ToS Requirement)

Reddit's Terms of Service require **zero retention** of deleted content. The module implements
multi-phase deletion compliance:

1. **Active Deletion** (`reddit_delete_content` tool):
   - Permanently deletes content from Reddit via API (`POST /api/del`)
   - Purges content from local caches (seen_posts, seen_comments)
   - Creates audit trail entry with UUID tracking
   - Returns `RedditDeletionResult` with deletion status

2. **Passive Auto-Purge** (Observer):
   - `check_content_deleted()` - Detects deleted content via `removed_by_category`, `removed`, or `deleted` flags
   - `purge_deleted_content()` - Removes from all local caches with audit logging
   - `check_and_purge_if_deleted()` - Convenience method for check + purge

3. **Deletion Status Tracking** (DSAR Pattern):
   - Multi-phase tracking: deletion confirmed → cache purged → audit trail updated
   - `get_deletion_status(content_id)` - Query deletion status for DSAR compliance
   - `RedditDeletionStatus` schema with `is_complete` property

**Zero Retention Policy**: When content is deleted on Reddit (by user, moderator, or CIRIS),
it is immediately purged from all local caches to comply with Reddit ToS.

### AI Transparency (Community Guidelines Requirement)

Reddit's community guidelines require clear disclosure when AI is used in moderation. The
`reddit_disclose_identity` tool posts transparency disclosures:

- **Default Message**: Clear AI identification, human oversight mention, contact information
- **Custom Messages**: Support for subreddit-specific disclosure text
- **Automatic Footer**: Links to ciris.ai for learn more and issue reporting
- **Format**: Posted as comment on submission with proper channel reference

Example disclosure:
```
Hello! I'm CIRIS, an AI assistant helping moderate this community.

I can help with content moderation, but all major decisions are reviewed by human
moderators. If you have concerns, please contact the mod team.

---
*I am CIRIS, an AI moderation assistant. [Learn more](https://ciris.ai) | [Report issues](https://ciris.ai/report)*
```

## Safety

- Adheres to the CIRIS covenant: no medical, clinical, or political campaigning actions.
- Honors Reddit best practices (user agent, rate handling, explicit channel references).
- Surfaces API failures with actionable error messages so operators can intervene safely.
- **Reddit ToS Compliance**: Zero retention of deleted content with automatic purging.
- **Community Guidelines Compliance**: AI transparency disclosure support.

## Testing

Comprehensive test suite with 51 tests covering all compliance functionality:
- **13 deletion compliance tests** - Reddit ToS zero retention requirement
- **12 transparency tests** - Community guidelines AI disclosure requirement
- **18 observer purge tests** - Auto-purge mechanism for ToS compliance
- **8 schema validation tests** - Type-safe request/response models

Run tests: `pytest tests/reddit/ -v`

See [`manifest.json`](./manifest.json) for the complete module declaration and dependency
list.
