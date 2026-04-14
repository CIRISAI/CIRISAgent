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

## Fix (CIRIS side, implemented ✅)

As of v2.4.4, CIRIS automatically disables reasoning/thinking mode on ALL
local endpoints. This is done in `_build_extra_kwargs()` in
`ciris_engine/logic/services/runtime/llm_service/service.py`:

```python
# For local endpoints (llama.cpp, vLLM, ollama, LM Studio)
extra_kwargs["extra_body"] = {
    "chat_template_kwargs": {"enable_thinking": False}
}
```

**Rationale**: CIRIS provides its own reasoning structure via the DMA
(Decision Making Architecture) pipeline. We don't need or want the model's
built-in chain-of-thought reasoning - it just slows things down and breaks
instructor's JSON parsing.

**Local endpoint detection** (`_is_local_endpoint()`):
- Matches: `localhost`, `127.0.0.1`, `192.168.x`, `10.x`, `.local` hostnames
- Matches common ports: `:11434` (Ollama), `:8080` (llama.cpp), `:1234` (LM Studio), `:8000` (vLLM)
- Excludes cloud providers: `ciris.ai`, `openrouter.ai`, `openai.com`, etc.

No manual configuration required - just point CIRIS at your local server.

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
