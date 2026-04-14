# Gemma 4 Compatibility Note

CIRIS relies on structured-output (JSON) responses from its LLM provider via
the [`instructor`](https://github.com/567-labs/instructor) library. Gemma 4
("Gemini-class") models emit an internal **chain-of-thought** stream by
default — and on OpenAI-compatible backends (llama.cpp, vLLM, some ollama
builds) that stream lands in a non-standard `reasoning_content` field while
the regular `content` field is returned empty:

```json
{
  "choices": [{
    "message": {
      "content": "",
      "reasoning_content": "Thinking Process:\n1. Analyze the request..."
    },
    "finish_reason": "length"
  }]
}
```

Instructor reads `content`, sees an empty string, retries, each retry
exhausts tokens on reasoning again, and eventually bubbles up an
`InstructorRetryException`. CIRIS's LLM service currently re-labels this as
`"Request timed out"`, which is misleading — the network call itself
succeeded in a few seconds. No Gemma-family DMA evaluation will complete
until reasoning mode is disabled.

## Symptoms

- `LLM UNEXPECTED ERROR - InstructorRetryException` spamming logs against a
  responsive endpoint (ping works, `GET /v1/models` returns 200 in ms).
- `finish_reason: length` with `max_tokens` far from exhausted on real
  content.
- Every DMA (EthicalPDMAEvaluator, CSDMAEvaluator, BaseDSDMA, …) fails with
  `All LLM services failed for <DMA>. Last error: LLM call failed
  (InstructorRetryException): <failed_attempts>`.

## Fix (server side)

Start the backend with reasoning disabled, or pass the chat-template flag
per request. For llama.cpp's OpenAI-compatible server:

```bash
curl -X POST http://<host>:<port>/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gemma-4-E2B-it-Q4_K_M.gguf",
    "messages": [{"role":"user","content":"Reply with JSON {\"ok\":true} only."}],
    "chat_template_kwargs": {"enable_thinking": false}
  }'
```

With `enable_thinking: false` the same model returns proper JSON in
`content` and `finish_reason: stop` — CIRIS's instructor pipeline is
satisfied without changes.

## Fix (CIRIS side, pending)

A targeted patch in `ciris_engine/logic/services/runtime/llm_service/service.py`
should:

1. When the configured model matches a Gemma-4 family pattern (e.g. any
   `gemma-4*` or `gemini-*it*` variant on a local endpoint), set
   `extra_body={"chat_template_kwargs": {"enable_thinking": false}}` on
   every `AsyncOpenAI.chat.completions.create` call so reasoning is
   suppressed at the protocol level.
2. Surface the real exception class when instructor retries exhaust, rather
   than relabelling it `"Request timed out"` — the misleading error sent
   operators down the DNS/timeout rabbit hole.

Until that lands, the workaround is to configure your inference server to
default `enable_thinking` to `false` (most llama.cpp builds support this via
`--chat-template-kwargs enable_thinking=false` or a server-side template
override), or to use a non-reasoning model (e.g. `qwen2.5:3b`, `mistral-7b`,
non-`it` Gemma variants).

## Reference log signature

Healthy request against Gemma 4 with reasoning disabled:
```
content: '```json\n{"ok":true}\n```'
reasoning_content: <none>
finish_reason: stop
```

Broken request against Gemma 4 with reasoning enabled (default):
```
content: ''
reasoning_content: 'Thinking Process: ...'
finish_reason: length
```

Observed on: llama.cpp build `b8638-5803c8d11`, `gemma-4-E2B-it-Q4_K_M.gguf`,
Jetson Nano over LAN (2026-04-14).
