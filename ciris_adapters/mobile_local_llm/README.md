# Mobile Local LLM Adapter

Runs a local Gemma 4 inference server as part of the CIRIS runtime on
mobile devices — Android today, iOS as soon as Google AI Edge ships an
adequate LiteRT-LM model for iPhone/iPad — that are capable enough to
host it. The adapter registers the local provider with the LLM bus so
the rest of CIRIS can call it through the same `call_llm_structured`
interface it uses for every other provider.

Built around the Google AI Edge / LiteRT-LM guidance for mobile Gemma 4:

- Prefer the smaller **E2B** variant on mobile; only step up to **E4B** on
  high-end phones with headroom for memory and thermals.
- Android builds target **arm64-v8a**; iOS targets **arm64** only.
- Start with a small model that works reliably, not the largest model that
  barely fits.

On weaker devices (insufficient RAM, 32-bit CPU, etc.) the adapter still
loads cleanly but stays unavailable, so the LLM bus silently falls back
to the hosted provider. On iOS the adapter may detect a capable device
but report a dedicated `IOS_STUB` tier when the Gemma 4 model bundle is
not yet installed — the setup wizard uses this state to show a
"coming soon" option rather than offering a broken local path.

## Architecture

| File | Responsibility |
|------|----------------|
| `config.py` | Typed config + environment variable bindings |
| `capability.py` | Device tier probe (RAM, ABI, disk, platform) |
| `inference_server.py` | Subprocess lifecycle + `/health` probing |
| `service.py` | `LLMServiceProtocol` implementation |
| `adapter.py` | `BaseAdapterProtocol` wrapper + health loop |
| `manifest.json` | Adapter metadata for dynamic loading |

The adapter registers a single `LLM` service at `Priority.HIGH`, one step
below the mock LLM provider (`CRITICAL`) and above hosted providers
(`NORMAL`). That means capable phones try on-device inference first and
drop to cloud automatically on failure.

## Capability tiers

Set by `probe_device_capability()` in `capability.py`:

| Tier | Meaning | When the wizard uses it |
|------|---------|-------------------------|
| `capable_e4b` | ≥ 8 GB RAM, arm64, mobile — can run E2B and E4B | Offer local inference with E4B as default |
| `capable_e2b` | ≥ 6 GB RAM, arm64, mobile — can run E2B only | Offer local inference with E2B |
| `ios_stub`    | iOS hardware looks fine but no Gemma 4 model bundle installed yet | Show "On-Device (Coming Soon)" — disabled |
| `incapable`   | < 6 GB RAM, wrong ABI, desktop without opt-in, etc. | Do not show the local option at all |

The reasons list on the report shows exactly why a device landed in a
given tier, which makes it easy to debug a phone that the LLM bus keeps
routing to the cloud.

## Lifecycle

1. `start()` probes `DeviceCapabilityReport`.
2. If the device is incapable or iOS-stub, the service stays unhealthy
   and the adapter logs the reasons. Nothing else runs.
3. If the device is capable, the adapter either spawns the configured
   `server_binary` or attaches to an already-running inference server on
   `host:port`. It then polls `/health` until the server responds or
   `ready_timeout_seconds` elapses.
4. A background health loop re-probes every `health_interval_seconds`.
   After three consecutive failed probes the adapter marks the local
   provider permanently unavailable and the LLM bus takes over.
5. `stop()` sends SIGTERM, waits 10s, and SIGKILLs if necessary. Any
   owned process is reaped and the exit code is reported via
   `get_status()`.

## Configuration

Everything is driven by environment variables so the mobile harness can
configure it at startup without touching Python code. See `manifest.json`
for the full list; the most important ones:

| Env var | Default | Meaning |
|---------|---------|---------|
| `CIRIS_MOBILE_LOCAL_LLM_ENABLED` | `true` | Master switch |
| `CIRIS_MOBILE_LOCAL_LLM_MODEL` | `gemma-4-e2b` | Variant to serve |
| `CIRIS_MOBILE_LOCAL_LLM_MODEL_PATH` | _(none)_ | Path to the model bundle |
| `CIRIS_MOBILE_LOCAL_LLM_IOS_MODEL_PATH` | _(none)_ | Expected path to the iOS model bundle (absence => IOS_STUB) |
| `CIRIS_MOBILE_LOCAL_LLM_SERVER_BINARY` | _(none)_ | Path to the local server binary |
| `CIRIS_MOBILE_LOCAL_LLM_PORT` | `8091` | Loopback port for the server |
| `CIRIS_MOBILE_LOCAL_LLM_MIN_RAM_GB` | `6.0` | RAM gate for the E2B tier |
| `CIRIS_MOBILE_LOCAL_LLM_FORCE_CAPABILITY` | _(none)_ | Override the probe for testing |
| `CIRIS_MOBILE_LOCAL_LLM_ALLOW_DESKTOP` | `false` | Allow desktop dev/QA use |

## Wizard integration

The cross-platform Kotlin Multiplatform wizard uses `canRunLocalInference()`
(in `mobile/shared/src/commonMain/.../platform/Platform.kt`) to decide
whether to show the "On-Device (Local)" option on the LLM selection
screen. The mapping between the Python capability tiers and the wizard
states is:

- `capable_e2b` / `capable_e4b` → wizard shows local option as normal.
- `ios_stub` → wizard shows local option labelled "Coming Soon" and
  disabled. Selecting BYOK / proxy continues normally.
- `incapable` → wizard hides the local option entirely.

## Testing

The adapter is designed so every layer can be unit tested without
touching the real mobile runtime:

- `probe_device_capability()` accepts callable overrides for every probe.
- `InferenceServerManager` works against any OpenAI-compatible server,
  so tests can point it at a lightweight fixture.
- `MobileLocalLLMService` accepts a pre-built capability report so tests
  can simulate the full capability / model-tier matrix without monkey
  patching the filesystem.

Unit tests live in `tests/ciris_adapters/mobile_local_llm/`.
