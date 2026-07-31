# CLI host tools on desktop installs

**Status:** implemented
**Issue:** [#941](https://github.com/CIRISAI/CIRISAgent/issues/941)
**Related:** [#942](https://github.com/CIRISAI/CIRISAgent/issues/942) (inert `requires_approval`), [#938](https://github.com/CIRISAI/CIRISAgent/issues/938) (task-scoped authorization), [#909](https://github.com/CIRISAI/CIRISAgent/issues/909) (deterministic sandbox)

---

## 1. The decision

> *"CLIToolService should be registered for desktop installs to support coding, it is a common use
> case, on mobile it should not be, since it would not provide any meaningful functionality"*

Coding assistance on a machine the operator owns is the intended use case. An agent that can read
files but cannot run a test, write a patch, or grep a tree is not a coding assistant. So on desktop
the CLI adapter now grants `shell_command`, `write_file` and `search_text` in addition to the
`list_files` / `read_file` / `system_info` it already granted.

On Android and iOS the app is sandboxed: a shell has nothing meaningful to run and a file write
nothing meaningful to write. The mobile grant is **unchanged** — three tools, no shell, no writes.

### What was true before

`CLIToolService` (`ciris_engine/logic/adapters/cli/cli_tools.py`) was fully implemented, unit-tested,
and referenced by nothing. The CLI platform registered `CLIAdapter` as its `ServiceType.TOOL`
provider, so `shell_command` and `write_file` existed in the tree but were **unreachable by the
agent**. #941's correction comment established this. This change is what makes them reachable.

---

## 2. What changed

Three files:

| File | Change |
|---|---|
| `ciris_engine/logic/utils/platform_detection.py` | New `is_desktop()` + `DESKTOP_PLATFORM_NAMES` |
| `ciris_engine/logic/adapters/cli/cli_tools.py` | `time_service` now optional; new `get_tool_callable()` delegation seam |
| `ciris_engine/logic/adapters/cli/cli_adapter.py` | On desktop, the tool set is the union; metadata delegates to `CLIToolService` |

### One provider, not two

`CliPlatform.get_services_to_register()` is **unchanged**. It still registers exactly three services
and exactly one `ServiceType.TOOL` provider — `provider=self.cli_adapter`. On a desktop install
`CLIAdapter` constructs a `CLIToolService` and borrows its `write_file` / `shell_command` /
`search_text` implementations and metadata; on mobile it constructs nothing and borrows nothing (the
`cli_tools` module is not even imported).

This was chosen over a second `AdapterServiceRegistration` for one concrete reason: **name collision**.
`CLIAdapter` and `CLIToolService` both define `list_files` and `read_file`. Registering both as TOOL
providers puts two services in `ToolBus`'s `supporting_services` list for those names, and
`tool_bus.py:140-172` resolves that case by looking for Discord context, then for `APIToolService`,
then falling back to `supporting_services[0]` — i.e. **registry order**. The agent would see one
tool description and could execute a different implementation. Discord already has this shape
(`discord/adapter.py:287` + `discord_adapter.py:1559`) and it makes ToolBus choose between aliases of
one surface. Not repeating it.

`list_files` and `read_file` therefore keep `CLIAdapter`'s existing implementations, unchanged.
`CLIToolService` contributes only the three names the adapter does not already have. A test asserts
that every CLI tool name resolves to exactly one supporting provider.

### Result-shape correction

`CLIAdapter`'s own tools return an explicit `success` field; `CLIToolService`'s results signal failure
via `error` alone. `CLIAdapter.execute_tool` previously defaulted `success` to `True` when the key
was absent, which would have reported every failed write and failed shell command as a success. It
now falls back to `error is None`. Behaviour for the pre-existing tools is unchanged (they always set
`success` explicitly).

---

## 3. The platform predicate, and how it fails

```python
DESKTOP_PLATFORM_NAMES = frozenset({"linux", "macos", "windows"})

def is_desktop() -> bool:
    return get_platform_name() in DESKTOP_PLATFORM_NAMES
```

`get_platform_name()` (pre-existing) resolves in this order:

| Signal | Source | Result |
|---|---|---|
| `ANDROID_ROOT` / `ANDROID_DATA` env | Android system | `android` |
| `sys.getandroidapilevel` present | **Chaquopy** — how the Android app hosts this runtime | `android` |
| `sys.platform == "linux"` and `/data/data` exists | Android filesystem layout | `android` |
| `sys.platform == "ios"` | BeeWare/Briefcase | `ios` |
| `darwin` with a simulator / `/var/mobile` home | iOS | `ios` |
| `darwin` / `win32` / `linux*` | desktop | `macos` / `windows` / `linux` |
| anything else | — | `unknown` |

**It fails closed.** `DESKTOP_PLATFORM_NAMES` is a positive allow-list, and `"unknown"` is not in it.
An unrecognized platform — a new mobile target, an exotic OS, a stripped runtime where the Android
signals are missing but so is everything else — gets the **mobile** answer: no shell, no writes. The
capability is only ever granted on a platform we positively recognize as a desktop host. Tests
exercise `unknown` explicitly, and exercise Android through both the env-var and the Chaquopy signal
rather than by patching the predicate.

The decision is made once, in `CLIAdapter.__init__`. There is no runtime toggle and no environment
override: nothing can turn shell execution on for a platform the predicate says is not desktop.

### Honest caveat: "desktop" means "not mobile, and recognized"

The predicate cannot distinguish a Linux laptop from a Linux server or a Docker container. If the
`cli` adapter is loaded on a headless Linux host — production, CI, a container — `is_desktop()` is
true and the host tools are granted. In practice production loads `api` (and `discord`), never `cli`:
`cli` is an interactive terminal transport, `main.py` defaults to `["api"]`, and the Android
bootstrap pins `adapter_types = ["api"]`. But the grant follows *loading the cli adapter*, not
*being at a keyboard*. `is_managed()` exists in `path_resolution.py` and could tighten this later;
it is deliberately **not** used here, because the ask was desktop-vs-mobile and adding an
unrequested container heuristic would surprise a self-hoster running the desktop stack in Docker.

---

## 4. Disclosure

An operator must be told that enabling `cli` grants shell execution and file writes.

The generated first-run disclosure built on `feat/wizard-tool-disclosure`
(`ciris_engine/logic/services/tool/tool_disclosure.py`, `GET /v1/setup/tool-disclosure`) picks this
up **automatically, with no changes on that branch**, because:

1. Its `BUILTIN_TOOL_SERVICES["cli"]` pointer resolves to `CLIAdapter` — still the registered TOOL
   provider — and its drift guards are anchored on `provider=self.<attr>` in `adapter.py`, which this
   change does not touch.
2. It reads tools from a live `get_all_tool_info()` call, and `CLIAdapter.get_all_tool_info()` now
   returns the union on desktop.
3. Its capability flags are derived **structurally** from parameter names, so `command` →
   `shell_execution` and `path`+`content` → `file_write` fire without any name table.

Verified by running that branch's generator and its 26 drift tests against this change:

```
# desktop
adapter: cli | source: PROSPECTIVE | name: Command Line
    list_files    -> ['file_read']
    read_file     -> ['file_read']
    system_info   -> []
    write_file    -> ['file_write']
    shell_command -> ['shell_execution', 'requires_approval']
    search_text   -> ['file_read']

# same code, ANDROID_ROOT=/system
adapter: cli | source: PROSPECTIVE
    list_files    -> ['file_read']
    read_file     -> ['file_read']
    system_info   -> []
```

Because the disclosure is generated by the server the operator is setting up, it is **automatically
platform-correct**: a desktop operator is told about shell execution, a mobile operator is not told
about a capability they do not have. A static per-adapter tool table could not have done this.

**One documentation fix the disclosure work must make:** the `NOTE` comment above
`BUILTIN_TOOL_SERVICES["cli"]` in `tool_disclosure.py` says *"CLIToolService … has no registration
path, so enabling 'cli' does not grant them and the disclosure must not claim it does."* That is no
longer true on desktop. The **code** is correct as written and needs no change; only the comment is
stale.

Two further gaps, neither introduced here, both worth naming:

- **`cli` is not in the wizard's adapter list at all.** `_get_available_adapters()`
  (`routes/setup/helpers.py:180`) returns a hard-coded `api` plus whatever `discover_adapters()`
  finds under `ciris_adapters/`; `cli` is a core adapter under `ciris_engine/logic/adapters/`, so it
  never appears as a checkbox. It *is* in the tool-disclosure report, which is where the grant is now
  described. An operator enables `cli` via `--adapter cli`, `CIRIS_ADAPTER`, or
  `POST /v1/system/adapters/cli`.
- **`get_core_adapter_info("cli")` under-declares.** `_adapter_discovery.py:307` lists
  `service_types: ["COMMUNICATION"]` for `cli`, though it has registered `TOOL` and `WISE_AUTHORITY`
  since well before this change. Pre-existing drift, unrelated to this change, not fixed here.

---

## 5. `requires_approval` gates nothing

`shell_command` ships with `dma_guidance=ToolDMAGuidance(..., requires_approval=True)`
(`cli_tools.py:492`; `:472` before this change). **This does not gate execution.**

Per #942, the field's only consumer in the entire codebase is `ciris_engine/logic/dma/tsaspdma.py:247`:

```python
if guidance.requires_approval:
    sections.append("**⚠️ Requires wise authority approval**")
```

That appends a line of markdown to the action-selection prompt. Nothing in the handler path, the
bus, or the conscience layer reads the field. There is no interception, no deferral, no approval
record, no check between action selection and dispatch. A model that selects `shell_command` executes
`shell_command`.

**So this ships with an approval marker that enforces nothing, and this document does not rely on it.**
Do not describe `shell_command` as "gated", "approval-required", or "human-in-the-loop" on the
strength of that flag. What actually constrains the tool is model-mediated and semantic: the
conscience layer reviews every selected action, `DEFER` is a real action routing to a Wise Authority,
and the tool's own `ToolDocumentation` / `ToolDMAGuidance` text argues against destructive use. Those
are real, and they are not deterministic.

Making the field load-bearing is #942 and is deliberately **out of scope here**. This change does not
make #942 worse in kind — `send_money` in the wallet adapter already ships with the same inert marker
— but it does raise the stakes, and that is stated rather than smoothed over.

---

## 6. Write-then-load: file writes reach runtime extension

This coupling was assessed as non-existent (BYPASS 4 in the #938 gate-placement thread was withdrawn)
**precisely because `write_file` was unreachable.** This change makes it real on desktop. Naming it:

`AdapterDiscoveryService.DISCOVERY_PATHS` (`services/tool/discovery_service.py:53-58`) scans:

```
<install>/ciris_adapters/     # bundled
./ciris_adapters/             # cwd
~/ciris/adapters/             # user
./.ciris/adapters/            # workspace
$CIRIS_EXTRA_ADAPTERS         # colon-separated, widens the above arbitrarily
```

`write_file` takes an unconstrained `path` — no allow-list, no root confinement, no path validation
beyond what the OS enforces for the agent's own uid. So on a desktop install the agent can write a
`manifest.json` and an `adapter.py` into `~/ciris/adapters/<name>/`, and on the **next runtime start**
that directory is discovered as a loadable adapter.

That is: **file write reaches runtime extension across a restart.** It is one step, not a chain of
improbable ones, and it needs no shell — `write_file` alone suffices. `shell_command` reaches the
same outcome more directly and does not need to wait for a restart.

Nothing in this change constrains that, and no existing control catches it:

- the write is not path-restricted,
- discovery does not verify provenance or signatures,
- `requires_approval` on `shell_command` is inert (§5) and `write_file` does not declare it at all,
- an adapter dropped into a discovery path is loaded on the operator's next start with no second
  consent prompt.

This is the substantive consequence of the decision, and it is the correct place to look first if the
blast radius is later judged too wide. Plausible mitigations, none implemented here: confine
`write_file` to a workspace root; exclude the discovery paths specifically; require a signed manifest
for discovered adapters (#938/#909 territory).

---

## 7. What this does **not** do

- **Does not gate, sandbox, or rate-limit anything.** `shell_command` runs
  `asyncio.create_subprocess_shell` with the agent process's full permissions — same uid, same
  environment, same filesystem, same network. No container, no seccomp, no allow-list, no timeout
  beyond the caller's. #909 remains open and now has a shipped motivating case.
- **Does not add an approval path.** See §5.
- **Does not restrict paths.** `write_file`, `read_file`, `list_files` and `search_text` reach
  anything the process can reach.
- **Does not change what mobile can do**, in either direction. Android/iOS keep exactly
  `list_files` / `read_file` / `system_info`.
- **Does not change any adapter default.** `cli` is not enabled by default and is not offered in the
  first-run wizard's adapter list. Nothing here turns an adapter on.
- **Does not touch `ToolBus`**, `tsaspdma.py`, the Discord adapter, or `ServiceInitializer`.
- **Does not add a second TOOL provider**, so it does not change how ToolBus resolves anything.
- **Does not fix** #942's inert marker, the `get_core_adapter_info("cli")` under-declaration, or the
  `ServiceInitializer` `"service_name": "SecretsToolService"` mislabel.

---

## 8. Tests

`tests/adapters/cli/test_cli_desktop_tools.py` (27 tests):

- **Predicate, both ways, unmocked** — Android via `ANDROID_ROOT` *and* via Chaquopy's
  `sys.getandroidapilevel`; iOS via `sys.platform`; each desktop platform; and `unknown` asserting
  fail-closed. No test patches `is_desktop` or `is_android`.
- **Desktop reachability through ToolBus** — `shell_command` is executed through the bus and its
  stdout checked; `write_file` writes a real file to a real path and the content is read back. A
  registered-but-unreachable tool would pass an inspection test and fail these.
- **Mobile denial through ToolBus** — `shell_command` / `write_file` / `search_text` each return
  `NOT_FOUND` from `ToolBus.execute_tool`, against a bus that *is* serving the CLI adapter's other
  three tools (asserted non-empty, so the denial is a real absence and not an empty lookup).
  `get_tool_info` returns `None` and `validate_parameters` returns `False` for them.
- **No ambiguous collision** — exactly one `ServiceType.TOOL` registration on both platforms with
  `provider is platform.cli_adapter`; every tool name resolves to exactly one supporting provider;
  `list_files` / `read_file` still bound to `CLIAdapter`'s own implementations.
- **Failure reporting** — a failed `write_file` reports `success=False`, not the pre-existing
  default-True.

Existing suites unchanged and green: `tests/adapters/cli/`,
`tests/ciris_engine/logic/adapters/cli/`, `tests/ciris_engine/logic/buses/` — 343 passed, 3 skipped.
`mypy` clean on all three changed files.
