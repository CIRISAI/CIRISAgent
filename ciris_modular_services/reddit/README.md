# Reddit Adapter Module

The Reddit adapter brings CIRIS onto a dedicated subreddit with the same multi-channel
expectations as the Discord adapter. It exposes tool, communication, and observation
capabilities that allow the agent to speak, listen, and moderate while following
Reddit's platform policies.

## Capabilities

- **Tool service** – structured tools for posting, replying, removals, submission lookups,
  user context, and active observation queries (`reddit_observe`).
- **Communication service** – the CommunicationBus can `send_message` and `fetch_messages`
  using canonical channel references such as `reddit:r/ciris:post/abc123` or
  `reddit:r/ciris:post/abc123:comment/def456`.
- **Observer** – a passive observer polls the configured subreddit and produces
  `PassiveObservationResult` entries for new submissions and comments, mirroring the
  Discord adapter’s behavior.

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

## Safety

- Adheres to the CIRIS covenant: no medical, clinical, or political campaigning actions.
- Honors Reddit best practices (user agent, rate handling, explicit channel references).
- Surfaces API failures with actionable error messages so operators can intervene safely.

See [`manifest.json`](./manifest.json) for the complete module declaration and dependency
list.
