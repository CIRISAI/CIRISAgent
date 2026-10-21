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

### Honest caveat: the predicate is necessary, not sufficient

`is_desktop()` gates the grant, but it does not *cause* it. The grant requires **both** a recognized
desktop platform **and** the `cli` adapter actually being loaded — and the shipped desktop entry
point does not load it. `ciris-agent` launches the backend as `main.py --adapter api`
(`ciris_engine/cli.py:139`), and `ciris-server` inserts `--adapter api` when none is given
(`cli.py:237-241`). So `CliPlatform` — and therefore `CLIAdapter`, and therefore the host tools — is
**not** constructed on a default desktop install.

Reaching the grant takes an explicit act: `--adapter cli`, `CIRIS_ADAPTER` including `cli`, or
`POST /v1/system/adapters/cli`. State it as *"a desktop run that loads the `cli` adapter gets shell
and file writes"*, never as *"desktop installs get shell"* — the second is what a reader will
remember, and it is not true of the shipped default.

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

**✅ Done — the documentation fix the disclosure work had to make.** The `NOTE` comment above
`BUILTIN_TOOL_SERVICES["cli"]` in `tool_disclosure.py` said *"CLIToolService … has no registration
path, so enabling 'cli' does not grant them and the disclosure must not claim it does."* The first
half stayed true (the CLI platform still registers `CLIAdapter`, not `CLIToolService`); the
conclusion did not, because `CLIAdapter` now borrows those implementations on desktop. The **code**
was correct as written and needed no change; the comment was corrected in the 2.9.7 documentation
pass (`tool_disclosure.py:151-170`).

> **Branch-topology note.** The stale comment and the code that falsifies it never coexisted on
> `feat/cli-tools-desktop` — that branch does not contain `tool_disclosure.py` at all
> (`git merge-base --is-ancestor 50470d555 feat/cli-tools-desktop` is false). The contradiction
> exists only where both `1f09778ef` (cli-tools-desktop) and `50470d555` (wizard-tool-disclosure)
> land, i.e. on `release/2.9.7`. Phrase it that way; "the NOTE is false on `feat/cli-tools-desktop`"
> is not a statement that can be checked out.

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
**precisely because `write_file` was unreachable.** This change makes it real on a desktop run that
loads the `cli` adapter. Naming it:

> The four-bypass accounting is reproduced in `FSD/TASK_ENVELOPE.md` §0, which is the place the two
> documents are kept in agreement. Short version: bypass 1 (context enrichment) is closed by the
> TaskEnvelope work; 2 (Discord double dispatch), 3 (`curl`/`http_*` on the API adapter) and 4
> (this one) are open. The numbering originates in the #938 thread and has no in-repo artifact.

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
`manifest.json` and an `adapter.py` into a discovery path, and that directory is then discovered as a
loadable adapter.

> **Correction (2.9.7 reconciliation) — this is worse than "across a restart".** The paragraph above
> originally said the drop is picked up "on the **next runtime start**". Discovery is **also reached
> during ordinary reasoning**: `ActionSelectionContextBuilder._cache_installable_tools`
> (`logic/dma/action_selection/context_builder.py:58-65`) constructs a fresh `AdapterDiscoveryService()`
> and awaits `get_discovery_report()` while building action-selection context. That call descends
> through `load_adapters_with_status` → `_try_instantiate_service`
> (`services/tool/discovery_service.py:465`) → `load_service_class` →
> `importlib.import_module(...)` (`:253`) → `service_class(**deps)` (`:478`). Nothing on that path
> consults `auto_load_adapters`. So the import — and therefore module-level code execution and class
> construction — happens **inside the reasoning loop**, not only at boot.
>
> Two things bound it, and both should be stated rather than assumed away:
> - `sys.modules` caching means an already-imported module is not re-read in-process. The reliable
>   in-process window is an adapter module that has **not yet** been imported; a restart reloads
>   everything regardless.
> - `AdapterDiscoveryService.__init__` only builds a loader for a path that already exists
>   (`discovery_service.py:86`), and `write_file` is a bare `open(path, "w")` (`cli_tools.py:209`)
>   that does **not** create parent directories. Creating a *new* adapter directory under
>   `~/ciris/adapters/` therefore needs a `mkdir`, i.e. `shell_command`.
>
> But `DISCOVERY_PATHS[0]` and `[1]` (`discovery_service.py:53-56`) are the **installed and
> current-directory `ciris_adapters/` trees, which always exist**. Overwriting or adding a file
> under an existing adapter package there needs no `mkdir` and no shell — `write_file` alone reaches
> it, subject only to filesystem permissions for the agent's own uid (which, in a user venv or a
> bundled install, generally include that tree).

That is: **file write reaches runtime extension, in-process and across restarts.** It is one step, not
a chain of improbable ones. `shell_command` reaches the same outcome more directly.

**Honest weighting.** Where `shell_command` is available, write-then-load is not the *first* code
execution — `shell_command` already is that. Its real significance there is **persistence and
privilege**: the dropped adapter survives restart and is registered inside the agent's own service
graph as a `ServiceType.TOOL` / `WISE_AUTHORITY` provider (`service_initializer.py:1623-1664`), where
the gated bootstrap path additionally injects `secrets_service`, `memory_service` and `bus_manager`
(`:1938-1946`). Where only `write_file` is available, it *is* a code-execution primitive.

Nothing in this change constrains that, and no existing control catches it:

- the write is not path-restricted,
- **discovery performs no provenance check of any kind** — no signature, no hash, no pinning.
  `_should_skip_for_auto_load` (`discovery_service.py:341-372`) reads `auto_load`,
  `requires_consent` and `opt_in_required` out of the **manifest the attacker just wrote**, so those
  flags are self-asserted by the thing being trusted. `ToolEligibilityChecker` checks binaries,
  env vars, platform and config keys — nothing about origin.
- `requires_approval` on `shell_command` is inert (§5) and `write_file` does not declare it at all,
- an adapter dropped into a discovery path is loaded with no second consent prompt.

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
- **Does not benefit from any task-scoped authorization.** `TaskEnvelope` Phase 1 shipped in the same
  release and grants every enabled tool to every task by design, and **nothing enforces the envelope
  yet** (`FSD/TASK_ENVELOPE.md` §0). So these tools are in every task's grant and no gate reads that
  grant. Do not read "TaskEnvelope landed" as "the shell tool is now scoped".
- **Is not the largest exposure in this release.** The `api` adapter — the default — ships
  `curl`/`http_get`/`http_post` with no URL validation at all, and that requires no opt-in. The
  consolidated picture, and the ranking, is in `FSD/THREAT_MODEL_2.9.7.md`.

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
