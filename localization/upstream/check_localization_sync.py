#!/usr/bin/env python3
"""Guard the CIRIS client localization bundles.

Adopted from the CIRISServer copy in the 0.5.185 three-way merge (see
client/VENDORING.md) — it supersedes the key-parity checker vendored from
CIRISAgent tools/dev: byte-identity across the four bundles, runtime
resolveKey semantics, placeholder parity, and a mutation self-test.

One adaptation for this repo: the Rust server source the server-id-* checks
scan lives in the CONSUMERS, not here. CI here passes ``--no-server-src`` to
DECLARE that absence — the checks report SKIP with the reason, never a silent
pass and never a false DEAD error. Run without the flag (e.g. from a CIRISServer
checkout) and the checks run exactly as upstream. The two mirrors that were
never under client/ (the agent's prompt bundle, the iOS substrate copy) remain
cross-repo obligations in evidence/blocked_upstream.tsv.

The client UI strings live in FOUR committed runtime bundles that MUST stay
byte-identical — one per platform loader (any that goes stale ships raw keys at
runtime):

  - client/shared/src/desktopMain/resources/localization/*.json   (CANONICAL)
  - client/desktopApp/src/main/resources/localization/*.json      (desktop pkg)
  - client/androidApp/src/main/assets/localization/*.json         (Android)
  - client/iosApp/iosApp/localization/*.json                      (iOS)

``en.json`` is the source of truth. The supported-language list is read from the
bundle ``manifest.json`` (never hardcoded).

WHY THIS FILE READS THE WAY IT DOES (CIRISServer#366)
-----------------------------------------------------
The previous revision printed ``OK: all locales at key parity`` over a bundle in
which 53 server-message ids were **dead in every language, including English** —
because it compared FLATTENED key sets, and flattening maps both the nested form
``{"admin": {"ttl": {"expired": …}}}`` and the flat form
``{"admin.ttl.expired": …}`` onto the same dotted string. To a key-set
comparison a flat key and a nested key are the same key. They are not the same
at runtime: ``LocalizationManager.resolveKey`` ALWAYS splits on ``.`` and walks
nested objects, and never tries an exact top-level match, so a flat dotted key
resolves to null — and the English fallback failed identically, because en.json
carried the same flat shape. The strings were present, byte-identical across all
four bundles, and completely dead. The instrument could not see the defect it
was pointed at. (Data fixed in 26605b5; this guard is why it cannot recur.)

So every check here is written against the RUNTIME semantics, not against a
convenient normal form, and every check reports the size of what it examined —
a zero finding is only evidence when the denominator is non-zero. A check whose
denominator is zero is itself an error.

The checks, two severities:

  ERROR (exit 1 — blocks CI):
    json-validity      every *.json in all four bundles parses.
    bundle-mirror      the four bundles carry identical file sets and every
                       file is byte-identical to canonical.
    manifest-coverage  every manifest language has a file, and every locale
                       file is listed in the manifest.
    reference-coverage every literal key passed to localizedString("…") /
                       getString("…") in commonMain Kotlin RESOLVES in en.json
                       under resolveKey semantics (undefined -> renders raw).
    key-resolvability  every leaf address in every locale file is reachable by
                       a faithful port of resolveKey — i.e. no flat dotted keys,
                       in any language. This is the #366 check.
    placeholder-parity a translated value carries exactly the placeholders of
                       its en.json source ({named}, ${…}, {0}, %s, %1$s).
                       Corruption, not lag: "{cont}" renders literally.

  WARNING (exit 0 by default; exit 1 under --strict):
    translation-drift  a locale missing en.json keys, or carrying empty values,
                       or carrying keys en.json does not have. Missing
                       translations fall back to English by design, so this
                       informs rather than blocks — it is what the ``localize-ui``
                       Claude workflow fixes.

Usage:
    python3 client/tools/check_localization_sync.py            # ERRORs block
    python3 client/tools/check_localization_sync.py --strict   # drift blocks too
    python3 client/tools/check_localization_sync.py --self-test # mutation-verify

``--self-test`` builds a synthetic bundle in a temp dir, breaks it one way at a
time, and asserts each check fires with a message naming the break. It is the
answer to "this gate has never been shown able to fail" — CI runs it before the
real check, so the gate proves it can fail on every run.

Exit codes:
    0 - no errors (and no warnings under --strict; all mutations caught under
        --self-test)
    1 - at least one error (or any warning under --strict, or an uncaught
        mutation under --self-test)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Repo root: this file lives at <root>/client/tools/check_localization_sync.py
REPO_ROOT = Path(__file__).resolve().parents[2]

# Every COMMITTED runtime localization bundle. The first is canonical; ALL the
# others are platform packaging/runtime copies that must mirror it byte-for-byte
# — desktop (JVM), Android (assets), AND iOS (bundle). The Android + iOS loaders
# read their own committed copies (LocalizationResourceLoader.{android,ios}.kt),
# so leaving them out of the guard let them ship stale and render raw keys
# (Codex review, PR #40). The untracked iosApp/Resources/app copy is a build
# artifact and is intentionally excluded.
CANONICAL_BUNDLE = "client/shared/src/desktopMain/resources/localization"
MIRROR_BUNDLES: Tuple[str, ...] = (
    CANONICAL_BUNDLE,
    "client/desktopApp/src/main/resources/localization",
    "client/androidApp/src/main/assets/localization",
    "client/iosApp/iosApp/localization",
)

# Kotlin source set whose literal string keys must resolve against en.json.
COMMON_MAIN = "client/shared/src/commonMain"

# The OTHER emitter of localization keys: the Rust server. Operator surfaces
# never send a sentence — they send ``{id, text}``, an id a UI resolves in the
# reader's language plus the English source to fall back to (operator_surface.rs
# SOURCE_LOCALE). Those ids are localization keys with no Kotlin call site, so
# the commonMain scan below cannot see a single one of them; a guard that checks
# only Kotlin has never looked at the surface #366 was actually about.
SERVER_SRC = "src"

# Set by ``--server-src``. Each entry is a checkout that CONTAINS the Rust
# sources emitting localized message ids — CIRISServer, and CIRISAgent when it
# grows its own.
#
# WHY THIS IS A POINTER AND NOT A SKIP. CIRISClient owns the localization
# BUNDLES; the code that emits ids into them lives in the consumers. That is a
# fact about where files sit, not permission to stop checking: the sources are
# public and one checkout away, and a guard that declares them "somebody else's
# CI" is a guard reporting green over a denominator of zero. So the absence is
# not declarable any more — say WHERE the emitters are, or fail and be told to.
EMITTER_ROOTS: Tuple[Path, ...] = ()

# The ONE tree ``EMITTER_ROOTS`` describes — set beside it, never separately.
#
# Without this the pointer is global, and the self-test's SYNTHETIC fixtures
# start reporting the real server's 303 ids instead of their own single planted
# one. The mutation that DELETES a fixture's ``src/`` to prove a zero
# denominator is caught would then quietly scan CIRISServer and pass. Fixtures
# must be hermetic; a fixture tree is never the tree the CLI was pointed at, so
# comparing roots is what makes them so.
EMITTER_FOR_ROOT: Optional[Path] = None

# localizedString("key" …) / getString("key" …) — capture the literal first arg.
# ``[^"$\\]`` rejects interpolated keys ("mobile.foo_${x}") which can't be
# checked statically; those are skipped, not failed.
_KEY_CALL = re.compile(r'(?:localizedString|getString)\(\s*"([^"$\\]+)"')

# A server-emitted localizable string is an ``(id, english_text)`` literal pair,
# whatever helper wraps it — ``m(id, text)`` (admin_ops.rs, mesh_config_surface.rs),
# ``refusal(code, token, id, text)`` (admin_ops.rs), or a bare ``Msg`` tuple
# (operator_surface.rs). Matching the PAIR rather than one helper name is what
# makes this scan cover all three; requiring a space in the text is what keeps it
# from matching adjacent unrelated literals.
# The FULL Rust string literal, including escapes and `\`-line-continuations.
#
# The previous pattern was `"([^"\\]{0,80})` — it stopped at the first backslash,
# and EVERY operator string in this codebase is `\`-continued by rustfmt. So it
# captured only the first physical line, silently, and a bulk import built from
# it wrote 55 ids into en.json truncated mid-word at ~80 chars. The cut landed on
# the load-bearing clause every time: `root_absent` lost "...is filed where no
# fold will ever count it" (the remedy), `withhold_class.fault` lost "it is this
# node's fault to fix" (the limiting sense).
#
# No check caught it, because until `check_server_id_text_matches_source` below
# NOTHING compared VALUES — only key sets and placeholders. A truncated value has
# the right key and the right (zero) placeholders.
_SERVER_MSG = re.compile(
    r'"([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)"\s*,\s*"((?:[^"\\]|\\.)*)"', re.S
)


def _without_test_modules(text: str) -> str:
    r"""Blank out every ``#[cfg(test)]`` item so test fixtures are not mistaken
    for server-emitted message ids.

    A test's ``Warning::error("t.reduced", "a plane is shed")`` has exactly the
    shape this scanner hunts for, and the scanner had no idea it was reading a
    fixture. `src/degradation.rs` produced FIVE such phantoms on first contact
    — ids no server will ever emit, demanding en.json entries that would put
    test strings into the shipped product bundle in 29 languages.

    That is the sibling of the #461 class: the id set was wrong, and being
    wrong in the direction of MORE findings is what made it look like
    diligence. A check that invents work is trusted exactly as long as it takes
    someone to look at one finding.

    Brace-matched rather than regex'd, because a test module is nested and the
    literals inside it contain braces of their own. Replaced with newlines, not
    deleted, so reported line numbers elsewhere stay honest.
    """
    out = list(text)
    i = 0
    marker = "#[cfg(test)]"
    while (i := text.find(marker, i)) != -1:
        # Find this item's opening brace, then its matching close. Anything
        # before the brace (`mod tests`, attributes) is inert either way.
        # **A brace-less item ends at its SEMICOLON, not at the next `{`.**
        #
        # `#[cfg(test)] use foo::bar;` / `const N: usize = 3;` / a type alias
        # are all valid, and searching blindly for `{` skips the semicolon and
        # adopts the opening brace of the NEXT — production — item. The matcher
        # then blanks that item, so a real server-emitted id silently
        # disappears from both coverage checks. Verified: `#[cfg(test)] use
        # foo::bar;` ate the emission after it.
        brace = _attributed_item_body(text, i)
        if brace is None:
            # Brace-less item: the attribute and its item are stripped, and the
            # scan resumes after the semicolon.
            semi = text.find(";", i)
            if semi == -1:
                break
            for k in range(i, semi + 1):
                if out[k] != "\n":
                    out[k] = " "
            i = semi + 1
            continue
        # `block_depth`, not a boolean: RUST BLOCK COMMENTS NEST (codex review,
        # PR #483). `/* outer /* inner */ } still outer */` exits at the first
        # `*/` with a flag, so the brace after it is counted as syntax — which
        # terminates the matcher early (test ids survive) or, with `{`, runs it
        # past the module and blanks production emissions.
        depth, j, in_str, in_line_comment, block_depth, esc = 0, brace, False, False, 0, False
        while j < len(text):
            c = text[j]
            if esc:
                esc = False
            elif c == "\\" and in_str:
                esc = True
            elif in_line_comment:
                if c == "\n":
                    in_line_comment = False
            elif block_depth:
                if text[j : j + 2] == "/*":
                    block_depth += 1
                    j += 2
                    continue
                if text[j : j + 2] == "*/":
                    block_depth -= 1
                    j += 2
                    continue
            elif in_str:
                if c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "r" and (raw := _raw_string_end(text, j)) is not None:
                # A RAW string (`r"..."`, `r#"..."#`). Its content may hold bare
                # quotes AND braces, and the ordinary string state machine flips
                # out of the string at the first inner quote and then counts the
                # braces after it as syntax. Measured both ways: `r#"a" } "#`
                # stops the matcher early (phantom survives) and `r#"a" { "#`
                # runs it past the module and eats the production emission
                # after it. Skipped whole.
                j = raw + 1
                continue
            elif c == "'":
                # A CHAR LITERAL or a LIFETIME, and they must be told apart.
                #
                # `'{'` and `'}'` are braces that must NOT count, and getting
                # this wrong is not cosmetic: `'{'` inside a test module runs
                # the matcher past the module's real end and blanks every
                # production emission site after it — which reads as "no
                # findings" and is indistinguishable from a clean file.
                #
                # A lifetime (`&'static str`, `MutexGuard<'static, ()>`) has no
                # closing quote, so treating every apostrophe as opening a char
                # literal is the mirror failure. Only a genuine literal is
                # skipped; a lifetime tick is simply ignored.
                end = _char_literal_end(text, j)
                if end is not None:
                    j = end + 1
                    continue
            elif text[j : j + 2] == "//":
                in_line_comment = True
            elif text[j : j + 2] == "/*":
                block_depth = 1
                j += 2
                continue
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        for k in range(i, min(j + 1, len(text))):
            if out[k] != "\n":
                out[k] = " "
        i = j + 1
    return "".join(out)


def _attributed_item_body(text: str, attr_start: int) -> "int | None":
    """Index of the `{` opening the body of the item attributed at `attr_start`.

    `None` when the item has NO body (`use`, `const`, `static`, a type alias) —
    those end at a top-level semicolon, and treating the next item's `{` as
    theirs is how a production emission site gets blanked.

    Decided by which comes first at NESTING DEPTH ZERO, skipping the attribute's
    own brackets and any string content, so `#[cfg(test)] const S: &str = "a {";`
    is still recognised as brace-less.
    """
    j = attr_start
    depth_brack = 0
    in_str = False
    esc = False
    while j < len(text):
        c = text[j]
        if esc:
            esc = False
        elif c == "\\" and in_str:
            esc = True
        elif in_str:
            if c == '"':
                in_str = False
        elif c == "r" and _raw_string_end(text, j) is not None:
            j = _raw_string_end(text, j) + 1
            continue
        elif c == '"':
            in_str = True
        elif text[j : j + 2] == "//":
            # A COMMENT between the attribute and its item. `#[cfg(test)]
            # // uses { syntax` followed by a `const` made the comment's brace
            # the item's body, and the matcher then blanked the following
            # PRODUCTION function (codex review, PR #483).
            nl = text.find("\n", j)
            j = len(text) if nl == -1 else nl
            continue
        elif text[j : j + 2] == "/*":
            # Nested, same as above.
            depth_c, k = 1, j + 2
            while k < len(text) and depth_c:
                if text[k : k + 2] == "/*":
                    depth_c += 1
                    k += 2
                    continue
                if text[k : k + 2] == "*/":
                    depth_c -= 1
                    k += 2
                    continue
                k += 1
            j = k
            continue
        elif c == "[":
            depth_brack += 1
        elif c == "]":
            depth_brack -= 1
        elif depth_brack == 0:
            if c == "{":
                return j
            if c == ";":
                return None
        j += 1
    return None


def _raw_string_end(text: str, start: int) -> "int | None":
    """Index of the final `"` of a Rust raw string starting at `text[start]`.

    `None` if `text[start]` does not begin one. Recognises `r"..."` and
    `r#*"..."#*`, matching the closing delimiter to the SAME number of hashes —
    which is what lets a raw string legally contain `"#` sequences.
    """
    if text[start] != "r":
        return None
    k = start + 1
    hashes = 0
    while k < len(text) and text[k] == "#":
        hashes += 1
        k += 1
    if k >= len(text) or text[k] != '"':
        return None
    closer = '"' + "#" * hashes
    end = text.find(closer, k + 1)
    if end == -1:
        return None
    return end + len(closer) - 1


def _char_literal_end(text: str, start: int) -> "int | None":
    r"""Index of the closing quote if `text[start]` opens a Rust char literal.

    `None` means the apostrophe is a LIFETIME or label tick, which closes
    nothing and must be stepped over rather than tracked.

    Handles the escape forms whose payload can itself contain braces —
    `'\u{7d}'` is a right brace written three ways from Sunday — by scanning to
    the terminating quote rather than assuming a fixed width. Bounded, so a
    malformed literal cannot send the scan to EOF.
    """
    if text[start] != "'":
        return None
    k = start + 1
    if k >= len(text):
        return None
    if text[k] == "\\":
        limit = min(len(text), start + 12)
        k += 1
        while k < limit:
            if text[k] == "'":
                return k
            k += 1
        return None
    # A plain char literal is exactly one character wide.
    if k + 1 < len(text) and text[k + 1] == "'":
        return k + 1
    return None


# The SAME id position, but with a COMPUTED text — `format!(...)` rather than a
# literal. `_SERVER_MSG` cannot see these, so every server-id check silently
# excluded them and the denominator overstated coverage (codex review, PR #483).
#
# Observed live: `mesh_config.refusal.store_unavailable` is emitted as
# `err(status, "store_unavailable", "mesh_config.refusal.store_unavailable",
# format!("The substrate could not be read: {e}"))` and is ABSENT from en.json —
# so it renders the server's English in all 29 languages while the guard
# reported all 241 examined ids covered.
#
# The id is extracted from both shapes; the exact SOURCE-TEXT comparison stays
# restricted to the literal shape, because a `format!` template is not a string
# this checker can evaluate.
_SERVER_MSG_ID_FORMATTED = re.compile(
    r'"([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)"\s*,\s*format!\s*\(', re.S
)


# **THE ID, WHATEVER FOLLOWS IT.**
#
# The two patterns above key on the TEXT — a literal, or a `format!`. An
# emission whose text is any other expression matched neither, so its id was
# excluded from every server-id check and removing its bundle entry left the
# strict gate green (codex review, PR #483). Live at the time:
# `auth.oauth.provider_unavailable` (followed by `&e.message()`) and
# `accord.duty.holder_custody` (followed by a bound `msg`).
#
# So ids are also taken from ARGUMENT POSITION in a call to one of the emitter
# helpers, whatever the remaining arguments look like. The helper list is
# derived from the source rather than guessed — these are the five identifiers
# that actually enclose dotted-id literals in `src/`, and the alternative,
# "any dotted literal followed by a comma", sweeps in hostnames
# (`accounts.google.com`), filenames (`libykcs11.dll`) and machine-only
# degradation CODES, which are a different contract entirely.
_SERVER_EMITTERS = re.compile(r"\b(?:m|err|msg|refuse|refusal|browser_refusal)\s*\(")
_DOTTED_ID = re.compile(r'"([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)"')


def _emitter_call_ids(text: str) -> List[str]:
    """Dotted-id literals appearing as arguments to an emitter helper."""
    out: List[str] = []
    for call in _SERVER_EMITTERS.finditer(text):
        depth, j = 0, call.end() - 1
        while j < len(text):
            c = text[j]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out.extend(x.group(1) for x in _DOTTED_ID.finditer(text[call.end() : j]))
    return out


def _rust_unescape(raw: str) -> str:
    r"""Resolve a Rust string literal body, including `\`-line-continuations.

    A backslash followed by a newline eats the newline AND the leading
    whitespace of the next line — that is what makes the multi-line literals in
    `src/operator_surface.rs` a single sentence rather than a ragged one.
    """
    out, i = [], 0
    simple = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'"}
    while i < len(raw):
        if raw[i] == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            if nxt == "\n":
                i += 2
                while i < len(raw) and raw[i] in " \t":
                    i += 1
                continue
            out.append(simple.get(nxt, nxt))
            i += 2
            continue
        out.append(raw[i])
        i += 1
    return "".join(out)

# Per-file bookkeeping subtree (translator, review_status, native_name, …) —
# legitimately varies between locales and is never a UI key, so it's excluded
# from every key-set comparison.
_IGNORED_ROOTS = ("_meta",)

# Runtime interpolation tokens that MUST survive translation verbatim:
#   {named}       — LocalizationManager named-brace params ({count}, {provider}…)
#   ${...}        — Kotlin/template interpolation
#   {0} {1}       — indexed
#   %s %d %1$s    — printf-style
_PLACEHOLDER = re.compile(r"\$\{[^}]*\}|\{[A-Za-z0-9_]+\}|%[0-9]*\$?[sd]")


# ===========================================================================
# Bundle primitives — all written against runtime (resolveKey) semantics
# ===========================================================================


def load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def flat_values(obj: dict, prefix: str = "", top: bool = True) -> Dict[str, Any]:
    """Map every leaf of a localization dict to its dotted ADDRESS -> value.

    Note this is address-space only: it deliberately CANNOT distinguish the
    nested form from the flat dotted form — that blindness is exactly what made
    the old key-parity check green over #366. Anything that depends on the
    distinction must go through :func:`resolve_key`.
    """
    out: Dict[str, Any] = {}
    for k, v in obj.items():
        if top and k in _IGNORED_ROOTS:
            continue
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flat_values(v, key, False))
        else:
            out[key] = v
    return out


def resolve_key(obj: dict, key: str) -> Optional[str]:
    """Faithful port of ``LocalizationManager.resolveKey``
    (client/shared/src/commonMain/…/localization/LocalizationManager.kt:296).

    The Kotlin::

        val parts = key.split(".")
        var current: JsonElement = obj
        for (part in parts) {
            current = when (current) {
                is JsonObject -> current[part] ?: return null
                else -> return null
            }
        }
        return when (current) { is JsonPrimitive -> current.contentOrNull; else -> null }

    Note what it does NOT do: it never falls back to an exact top-level match.
    That is the whole of CIRISServer#366 — a flat dotted key is unreachable, and
    the English fallback path uses this same function, so a flat key in en.json
    is dead for every reader in every language.

    Ports of the leaf cases: JsonPrimitive (string/number/bool) resolves; JSON
    null, arrays and objects do not. Keep this function in step with the Kotlin
    — it is the definition of "this key works at runtime".
    """
    cur: Any = obj
    for part in key.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    if isinstance(cur, bool) or isinstance(cur, (str, int, float)):
        return str(cur)
    return None


def manifest_languages(bundle: Path) -> List[str]:
    """Read the supported-language list from the bundle manifest (source of truth)."""
    manifest = load_json(bundle / "manifest.json")
    langs = manifest.get("languages")
    if isinstance(langs, dict):
        return list(langs.keys())
    if isinstance(langs, list):
        return [x.get("code") if isinstance(x, dict) else x for x in langs]
    raise ValueError("could not read 'languages' from manifest.json")


def locale_files(bundle: Path) -> List[Path]:
    return sorted(p for p in bundle.glob("*.json") if p.name != "manifest.json")


# ===========================================================================
# Checks. Each returns (messages, examined) — ``examined`` is the denominator
# the check actually looked at, so "0 findings" can be told apart from "the
# instrument looked at nothing" (CIRISServer#366, and the health-check grep in
# FSD/RCA_INGEST_REJECTION_2026-08-05.md that matched 0 of 25,927 warnings).
# ===========================================================================

Result = Tuple[List[str], int]


def check_json_validity(root: Path) -> Result:
    msgs: List[str] = []
    examined = 0
    for b in MIRROR_BUNDLES:
        bundle = root / b
        if not bundle.exists():
            msgs.append(f"bundle dir missing: {b}")
            continue
        for f in sorted(bundle.glob("*.json")):
            examined += 1
            try:
                doc = load_json(f)
            except Exception as e:  # noqa: BLE001 - report any parse failure
                msgs.append(f"invalid JSON: {f.relative_to(root)}: {e}")
                continue
            if not isinstance(doc, dict):
                msgs.append(f"not a JSON object: {f.relative_to(root)}")
    return msgs, examined


def check_bundle_mirror(root: Path) -> Result:
    """Every one of the four runtime bundles must be byte-identical to canonical."""
    msgs: List[str] = []
    canonical = root / MIRROR_BUNDLES[0]
    if not canonical.exists():
        return [f"canonical bundle missing: {MIRROR_BUNDLES[0]}"], 0
    canonical_files = {p.name for p in canonical.glob("*.json")}
    examined = 0

    for b in MIRROR_BUNDLES[1:]:
        other = root / b
        if not other.exists():
            msgs.append(f"mirror bundle missing: {b}")
            continue
        other_files = {p.name for p in other.glob("*.json")}
        for f in sorted(canonical_files - other_files):
            msgs.append(f"{b}: missing file present in canonical: {f}")
        for f in sorted(other_files - canonical_files):
            msgs.append(f"{b}: extra file not in canonical: {f}")
        for f in sorted(canonical_files & other_files):
            examined += 1
            if (canonical / f).read_bytes() != (other / f).read_bytes():
                msgs.append(
                    f"{b}/{f} differs from {MIRROR_BUNDLES[0]}/{f} "
                    f"(all {len(MIRROR_BUNDLES)} runtime bundles must be byte-identical)"
                )
    return msgs, examined


def check_manifest_coverage(root: Path, langs: Sequence[str]) -> Result:
    """The manifest and the shipped locale files must name the same set."""
    canonical = root / MIRROR_BUNDLES[0]
    present = {p.stem for p in locale_files(canonical)}
    listed = set(langs)
    msgs = [f"manifest lists '{c}' but {c}.json is missing from canonical" for c in sorted(listed - present)]
    msgs += [f"{c}.json ships in canonical but the manifest does not list '{c}'" for c in sorted(present - listed)]
    return msgs, len(listed | present)


def referenced_keys(root: Path) -> Dict[str, Path]:
    """Map each statically-extractable localization key -> first Kotlin call site."""
    keys: Dict[str, Path] = {}
    common = root / COMMON_MAIN
    if not common.exists():
        return keys
    for kt in sorted(common.rglob("*.kt")):
        text = kt.read_text(encoding="utf-8")
        for m in _KEY_CALL.finditer(text):
            keys.setdefault(m.group(1), kt.relative_to(root))
    return keys


def check_reference_coverage(root: Path, en: dict) -> Result:
    """Every literal key in commonMain must RESOLVE in en.json (not merely exist
    in its flattened address space — see the module docstring)."""
    msgs: List[str] = []
    refs = referenced_keys(root)
    unresolved = sorted((k, p) for k, p in refs.items() if resolve_key(en, k) is None)
    if unresolved:
        msgs.append(
            f"{len(unresolved)} key(s) referenced in commonMain do not resolve in "
            f"en.json (they render RAW on every platform):"
        )
        for key, site in unresolved:
            msgs.append(f"    - {key}    ({site})")
    return msgs, len(refs)


def _emitter_src_dirs(root: Path) -> List[Tuple[Path, Path]]:
    """Every Rust tree to scan, as (src_dir, path_label_base).

    ``--server-src`` wins for the tree the CLI was pointed at, and ONLY that
    tree ([EMITTER_FOR_ROOT]). Each argument may be a checkout root (its
    ``src/`` is used) or a source directory itself, so both
    ``--server-src ~/CIRISServer`` and ``--server-src ~/CIRISServer/src`` mean
    the same thing. Everything else — a fixture tree, and a CIRISServer
    checkout running this file in place — falls back to ``<root>/src``, which
    is what keeps the tool byte-identical in its home repo.
    """
    if EMITTER_FOR_ROOT is None or root.resolve() != EMITTER_FOR_ROOT:
        src = root / SERVER_SRC
        return [(src, root)] if src.is_dir() else []

    found: List[Tuple[Path, Path]] = []
    for raw in EMITTER_ROOTS:
        base = Path(raw).expanduser().resolve()
        src = base / SERVER_SRC if (base / SERVER_SRC).is_dir() else base
        if src.is_dir():
            found.append((src, base))
    if found:
        return found
    src = root / SERVER_SRC
    return [(src, root)] if src.is_dir() else []


def _emitter_files(root: Path) -> List[Tuple[Path, Path]]:
    """(file, label) for every ``*.rs`` under every emitter tree.

    The label disambiguates when more than one checkout is scanned — an id
    reported against ``src/health.rs`` is not actionable if two repos both have
    one.
    """
    dirs = _emitter_src_dirs(root)
    multi = len(dirs) > 1 or bool(EMITTER_ROOTS)
    out: List[Tuple[Path, Path]] = []
    for src, base in dirs:
        for rs in sorted(src.rglob("*.rs")):
            rel = rs.relative_to(base)
            out.append((rs, Path(base.name) / rel if multi else rel))
    return out


def server_message_ids(root: Path) -> Dict[str, Path]:
    """Map each server-emitted message id -> first Rust emission site."""
    ids: Dict[str, Path] = {}
    for rs, label in _emitter_files(root):
        text = _without_test_modules(rs.read_text(encoding="utf-8"))
        for m in _SERVER_MSG.finditer(text):
            if " " not in m.group(2):
                continue  # not an English sentence — not an (id, text) pair
            ids.setdefault(m.group(1), label)
        # Same id position, computed text. See `_SERVER_MSG_ID_FORMATTED`.
        for m in _SERVER_MSG_ID_FORMATTED.finditer(text):
            ids.setdefault(m.group(1), label)
        # Same id position, ANY following expression. See `_emitter_call_ids`.
        for mid in _emitter_call_ids(text):
            ids.setdefault(mid, label)
    return ids


def check_server_ids_resolvable(root: Path, en: dict, ids: Dict[str, Path]) -> Result:
    """ERROR: a server-emitted id that en.json DEFINES must be reachable.

    Present-but-unreachable is strictly worse than absent: the bundle claims the
    string is localized, every mirror agrees, and the lookup still returns null.
    That is the 0c728b1 failure exactly.
    """
    en_addrs = set(flat_values(en))
    bad = sorted(i for i in ids if i in en_addrs and resolve_key(en, i) is None)
    msgs = [
        f"{len(bad)} server-emitted id(s) are DEFINED in en.json but unreachable by resolveKey "
        f"({', '.join(bad[:3])}{'…' if len(bad) > 3 else ''})"
    ] if bad else []
    return msgs, len(ids)


def server_message_texts(root: Path) -> Dict[str, str]:
    """Map each server-emitted message id -> its FULL English text from Rust."""
    out: Dict[str, str] = {}
    for mid, texts in _server_message_texts_all(root).items():
        out[mid] = texts[0]
    return out


def _server_message_texts_all(root: Path) -> Dict[str, List[str]]:
    """Map each id -> EVERY distinct English text emitted under it, in file order.

    Plural on purpose. `setdefault` kept only the first, so an id emitted with
    two different texts passed `server-id-text` against whichever one happened
    to come first in file order, while the OTHER endpoint rendered a
    translation of a sentence it does not say (codex review, PR #483).
    """
    out: Dict[str, List[str]] = {}
    for rs, _label in _emitter_files(root):
        text = _without_test_modules(rs.read_text(encoding="utf-8"))
        for m in _SERVER_MSG.finditer(text):
            txt = _rust_unescape(m.group(2))
            if " " not in txt:
                continue
            seen = out.setdefault(m.group(1), [])
            if txt not in seen:
                seen.append(txt)
    return out


# **ENUMERATED DEBT, NOT AN EXEMPTION.**
#
# Broadening id extraction to the `format!`-texted shape (see
# `_SERVER_MSG_ID_FORMATTED`) revealed 13 ids that have NEVER had an en.json
# entry and therefore render the server's English in all 29 languages. They are
# real, they predate this checker being able to see them, and fixing them means
# writing 29 translations apiece — the `localize-ui` workflow, tracked in
# CIRISServer#484.
#
# Listing them here rather than weakening the check keeps three properties:
#   * a NEW uncovered id still fails, so the debt cannot grow;
#   * the debt is enumerated in source, so it cannot be forgotten;
#   * an id that GETS covered must be removed from this list — the check below
#     fails on a stale entry — so the list can only shrink.
#
# WHEN ADDING HERE IS LEGITIMATE, AND WHEN IT IS NOT.
#
# Legitimate: an operator-facing sentence that was previously emitted as BARE
# ENGLISH PROSE with no id at all is given one. That is strictly better for the
# reader — the client can resolve the key the moment a translation lands, where
# before there was nothing to resolve — and this list is the mechanism that
# keeps it visible until then.
#
# Not legitimate: silencing a NEW uncovered id that could simply be translated,
# or one whose only problem is that nobody has run `localize-ui`. Add the
# en.json entry and the 29 bundles instead.
#
# The three `operator.store.*_not_measured` ids below are the first kind: they
# replaced hardcoded English in the `not_measured` block of
# `src/operator_surface.rs`, on a surface that advertises `source_locale` and
# could not honour it.
KNOWN_UNLOCALIZED: Tuple[str, ...] = (
    "accord.duty.assemble",
    "accord.duty.holder_identity_mismatch",
    "accord.duty.no_duty",
    "chat.community_shape_conflict",
    # NOT pre-existing debt and NOT prose-to-key: a DELIBERATE SPLIT. The
    # dismissal path used to share `commons_surface.refusal.objection_absent`,
    # whose 29 locales all translate the BALLOT sentence — so a non-English
    # dismissal rendered "a ballot answers…". Unifying the English alone left
    # 28 languages saying it anyway; giving the dismissal its own id keeps the
    # ballot path's correct translations intact and makes the dismissal
    # English-but-RIGHT rather than translated-but-WRONG, pending #484.
    "commons_surface.refusal.objection_absent_dismissal",
    "mesh_config.refusal.bad_now",
    "mesh_config.refusal.bad_request",
    "mesh_config.refusal.canonicalize_failed",
    "mesh_config.refusal.bad_ttl",
    "mesh_config.refusal.baseline_unreadable",
    "mesh_config.refusal.sign_failed",
    "mesh_config.refusal.store_unavailable",
    "operator.store.per_table_bytes_not_measured",
    "operator.store.wal_bytes_not_measured",
    "trust_root.bad_bundle",
    "trust_root.bad_request",
    "trust_root.bundle_refused",
    "trust_root.install_failed",
    "trust_root.withdraw_failed",
)


def check_known_unlocalized_list_is_current(root: Path, en: dict) -> Result:
    """ERROR: every entry on the debt list must still be BOTH real and needed.

    Two ways an entry goes stale, and both leave an exemption outliving its
    reason — the shape that lets "temporary" debt become permanent coverage
    loss:

      * COVERED — the id now has an en.json entry, so the debt is paid and the
        entry must go;
      * GONE — the emission site was deleted or renamed, so the entry protects
        nothing today AND would silently exempt a future re-introduction of the
        same id, which is the more dangerous half (codex review, PR #483): a
        dead exemption is invisible until it quietly covers for something new.

    The list can therefore only shrink, and only for the right reason.
    """
    addrs = set(flat_values(en))
    emitted = set(server_message_ids(root))
    covered = sorted(i for i in KNOWN_UNLOCALIZED if i in addrs)
    gone = sorted(i for i in KNOWN_UNLOCALIZED if i not in emitted)
    msgs = []
    if covered:
        msgs.append(
            f"{len(covered)} id(s) on KNOWN_UNLOCALIZED now HAVE an en.json entry and must be "
            f"removed from that list ({', '.join(covered[:3])}"
            f"{'…' if len(covered) > 3 else ''}) — an allowlist that outlives its reason is "
            f"how temporary debt becomes permanent"
        )
    if gone:
        msgs.append(
            f"{len(gone)} id(s) on KNOWN_UNLOCALIZED are NO LONGER EMITTED anywhere in src/ "
            f"({', '.join(gone[:3])}{'…' if len(gone) > 3 else ''}) — the entry protects "
            f"nothing now and would silently exempt a future re-introduction of the same id"
        )
    return msgs, len(KNOWN_UNLOCALIZED)


def check_server_ids_are_single_valued(root: Path) -> Result:
    """ERROR: one id must mean one sentence.

    A localization id is a KEY: en.json holds exactly one English string for it,
    and the 29 locales translate that one string. Emitting two different
    sentences under it means at least one endpoint renders text it does not say,
    in every language, and no other check can see it — the id set is right, the
    key resolves, the placeholders match, and `server-id-text` compares en.json
    against whichever emission the scanner happened to reach first.

    Found live: `commons_surface.refusal.objection_absent` said "a ballot
    answers a question about ONE objection" on the ballot path and "a dismissal
    lifts ONE named objection" on the dismissal path, with en.json matching only
    the first.
    """
    all_texts = _server_message_texts_all(root)
    bad = sorted(mid for mid, texts in all_texts.items() if len(texts) > 1)
    msgs = []
    if bad:
        detail = "; ".join(
            f"{mid} -> {len(all_texts[mid])} different texts: "
            + " | ".join(repr(t[:60]) for t in all_texts[mid])
            for mid in bad[:2]
        )
        msgs = [
            f"{len(bad)} server-emitted id(s) are emitted with CONFLICTING English text, so at "
            f"least one endpoint renders a sentence it does not say, in every language "
            f"({detail}{'…' if len(bad) > 2 else ''})"
        ]
    return msgs, len(all_texts)


def check_server_id_text_matches_source(root: Path, en: dict) -> Result:
    """ERROR: en.json's English for a server id must EQUAL what the server emits.

    Nothing else in this guard compares VALUES. Key sets, resolvability,
    placeholders and mirroring all pass over a value that is a truncated prefix
    of the real sentence — and one did: a bulk import built on a regex that
    stopped at the first backslash wrote 55 ids into en.json cut mid-word at
    ~80 chars, and every check stayed green.

    The consequence is not cosmetic. These sentences are load-bearing at exactly
    the end that got cut: a remedy clause, a limiting clause, the second half of
    a "cannot separate X from Y" hedge. And a locale translated from the
    fragment is worse than an absent one, because it renders as a confident,
    complete-looking sentence that says less than the server does — the failure
    mode this file's own module docstring calls a stale translation of different
    content.
    """
    msgs: List[str] = []
    src_texts = server_message_texts(root)
    for msg_id, source_text in sorted(src_texts.items()):
        bundled = resolve_key(en, msg_id)
        if bundled is None or not isinstance(bundled, str) or bundled == source_text:
            continue
        how = (
            f"TRUNCATED at {len(bundled)} of {len(source_text)} chars"
            if source_text.startswith(bundled)
            else "DIVERGED (not a prefix)"
        )
        msgs.append(
            f"    - {msg_id}: {how}\n"
            f"        bundle: …{bundled[-60:]!r}\n"
            f"        source: …{source_text[-60:]!r}"
        )
    if msgs:
        msgs.insert(
            0,
            f"{len(msgs)} server id(s) whose en.json English differs from the text the "
            f"server actually emits (a locale translated from this renders a confident "
            f"sentence saying less than the wire does):",
        )
    return msgs, len(src_texts)


def check_server_ids_covered(root: Path, en: dict, ids: Dict[str, Path]) -> Result:
    """WARNING: a server-emitted id with no en.json entry at all.

    The wire carries ``{id, text}``, so an uncovered id degrades to the server's
    English ``text`` — the designed fallback, same severity class as translation
    lag. But it means the string cannot be localized into ANY of the 29
    languages, so it belongs on the localize-ui worklist rather than in silence.
    """
    # Enumerated debt is excluded — see `KNOWN_UNLOCALIZED`. A NEW uncovered id
    # still fails, which is the property that matters, and
    # `check_known_unlocalized_list_is_current` makes the list shrink-only.
    uncovered = sorted(
        i
        for i in ids
        if i not in set(flat_values(en)) and i not in KNOWN_UNLOCALIZED
    )
    if not uncovered:
        return [], len(ids)
    by_file: Dict[str, int] = {}
    for i in uncovered:
        by_file[str(ids[i])] = by_file.get(str(ids[i]), 0) + 1
    where = ", ".join(f"{f} ({n})" for f, n in sorted(by_file.items(), key=lambda kv: -kv[1]))
    return (
        [
            f"{len(uncovered)} of {len(ids)} server-emitted message id(s) have no en.json entry, "
            f"so they cannot be localized into any language and always render the server's "
            f"English text — {where}; first: {', '.join(uncovered[:3])}…"
        ],
        len(ids),
    )


def check_key_resolvability(root: Path) -> Result:
    """THE #366 check: every leaf address a locale file carries must be reachable
    by :func:`resolve_key` — the faithful port of the Kotlin resolver.

    A key-set comparison cannot see this: flattening collapses
    ``{"nav": {"home": …}}`` and ``{"nav.home": …}`` onto the same address. Only
    the resolver's own walk tells them apart, and only the first one works.

    This is checked per FILE, in the file's own address space, so it fires in
    both directions — a flat key in en.json (dead for everyone, since the English
    fallback fails identically) and a flat key in one locale (dead for that
    locale's readers) are each an error against that file.
    """
    msgs: List[str] = []
    canonical = root / MIRROR_BUNDLES[0]
    examined = 0
    for f in locale_files(canonical):
        try:
            doc = load_json(f)
        except Exception:  # json-validity already reported it
            continue
        addrs = flat_values(doc)
        examined += len(addrs)
        bad = [a for a in sorted(addrs) if resolve_key(doc, a) is None]
        if bad:
            msgs.append(
                f"{f.name}: {len(bad)} key(s) UNREACHABLE by LocalizationManager.resolveKey "
                f"— stored as a flat dotted key (or a non-primitive leaf), so the lookup "
                f"returns null and the id renders raw "
                f"({', '.join(bad[:3])}{'…' if len(bad) > 3 else ''})"
            )
    return msgs, examined


def check_placeholder_parity(root: Path, langs: Sequence[str], en: dict) -> Result:
    """A translated value must carry the SAME multiset of interpolation
    placeholders as its en.json source — a dropped or misspelled ``{count}``
    renders unsubstituted at runtime. Corruption, not translation lag: ERROR."""
    msgs: List[str] = []
    canonical = root / MIRROR_BUNDLES[0]
    en_vals = {k: v for k, v in flat_values(en).items() if isinstance(v, str)}
    examined = 0
    for lang in langs:
        if lang == "en":
            continue
        f = canonical / f"{lang}.json"
        if not f.exists():
            continue  # manifest-coverage's job
        try:
            vals = flat_values(load_json(f))
        except Exception:  # json-validity already reported it
            continue
        bad: List[str] = []
        for key, ev in en_vals.items():
            tv = vals.get(key)
            if not isinstance(tv, str) or tv.strip() == "":
                continue  # missing/empty is translation-drift's job
            examined += 1
            if sorted(_PLACEHOLDER.findall(ev)) != sorted(_PLACEHOLDER.findall(tv)):
                bad.append(
                    f"{key} [en {sorted(_PLACEHOLDER.findall(ev))} != "
                    f"{lang} {sorted(_PLACEHOLDER.findall(tv))}]"
                )
        if bad:
            msgs.append(
                f"{lang}.json: {len(bad)} value(s) with placeholder drift — "
                f"{'; '.join(bad[:3])}{'…' if len(bad) > 3 else ''}"
            )
    return msgs, examined


def check_translation_drift(root: Path, langs: Sequence[str], en: dict) -> Result:
    """WARNING: each locale should carry en.json's full key set, non-empty."""
    msgs: List[str] = []
    canonical = root / MIRROR_BUNDLES[0]
    en_vals = flat_values(en)
    en_keys = set(en_vals)
    examined = 0
    for lang in langs:
        if lang == "en":
            continue
        f = canonical / f"{lang}.json"
        if not f.exists():
            continue  # manifest-coverage's job (an ERROR there)
        try:
            vals = flat_values(load_json(f))
        except Exception:  # json-validity already reported it
            continue
        examined += len(en_keys)
        missing = sorted(en_keys - set(vals))
        empty = sorted(k for k in en_keys & set(vals) if isinstance(vals[k], str) and vals[k].strip() == "")
        extra = sorted(set(vals) - en_keys)
        detail: List[str] = []
        if missing:
            detail.append(f"missing {len(missing)} ({', '.join(missing[:3])}…)")
        if empty:
            detail.append(f"empty {len(empty)} ({', '.join(empty[:3])}…)")
        if extra:
            detail.append(f"extra {len(extra)} ({', '.join(extra[:3])}…)")
        if detail:
            msgs.append(f"{lang}.json: {'; '.join(detail)}")
    return msgs, examined


# ===========================================================================
# Driver
# ===========================================================================


class Report:
    def __init__(self) -> None:
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.lines: List[str] = []  # per-check "OK <name> : <denominator>" lines

    def record(self, name: str, msgs: List[str], examined: int, *, severity: str, unit: str) -> None:
        bucket = self.errors if severity == "error" else self.warnings
        if examined == 0:
            # A check that examined nothing has produced no evidence, whatever
            # it printed. This is the #366 defect class itself.
            self.errors.append(f"{name}: examined 0 {unit} — the check found nothing because it looked at nothing")
            self.lines.append(f"  DEAD  {name:<19}: examined 0 {unit}")
            bucket.extend(f"{name}: {m}" for m in msgs)
            return
        if msgs:
            bucket.extend(f"{name}: {m}" for m in msgs)
            tag = "FAIL " if severity == "error" else "WARN "
            self.lines.append(f"  {tag} {name:<19}: {len(msgs)} finding(s) over {examined} {unit}")
        else:
            self.lines.append(f"  OK    {name:<19}: 0 findings over {examined} {unit}")


def run_checks_synthetic(root: Path) -> Report:
    """`run_checks` over a fixture tree — see `debt_list_applies`."""
    return run_checks(root, debt_list_applies=False)


def run_checks(root: Path, *, debt_list_applies: bool = True) -> Report:
    """`debt_list_applies=False` for SYNTHETIC trees.

    `KNOWN_UNLOCALIZED` is a statement about a real repository's sources. The
    self-test builds a fixture tree containing one emission site, where every
    entry on the list is trivially "no longer emitted" — so the freshness check
    would fire on every mutation and drown out what each one is testing. The
    list is proven separately, against real semantics, by
    `_prove_the_debt_list_is_kept_honest`.

    Where the emitters are is NOT one of these narrowings. It is a pointer
    (`--server-src`, see [EMITTER_ROOTS]) with no default and no way to opt
    out: a run that cannot find them fails and says so.
    """
    rep = Report()
    canonical = root / CANONICAL_BUNDLE

    msgs, n = check_json_validity(root)
    rep.record("json-validity", msgs, n, severity="error", unit="file(s)")

    msgs, n = check_bundle_mirror(root)
    rep.record("bundle-mirror", msgs, n, severity="error", unit="file compare(s)")

    # Everything below needs canonical en.json + manifest.json to parse. If they
    # do not, json-validity has already errored — say so and stop, rather than
    # dying with a traceback (or, worse, reporting the remaining checks as OK).
    try:
        en = load_json(canonical / "en.json")
        langs = manifest_languages(canonical)
    except Exception as e:  # noqa: BLE001
        rep.errors.append(f"canonical bundle unreadable ({e}) — remaining checks could not run")
        rep.lines.append("  SKIP  <remaining checks>  : canonical en.json/manifest.json unreadable")
        return rep

    msgs, n = check_manifest_coverage(root, langs)
    rep.record("manifest-coverage", msgs, n, severity="error", unit="language(s)")

    msgs, n = check_reference_coverage(root, en)
    rep.record("reference-coverage", msgs, n, severity="error", unit="commonMain key(s)")

    msgs, n = check_key_resolvability(root)
    rep.record("key-resolvability", msgs, n, severity="error", unit="address(es)")

    if not _emitter_src_dirs(root):
        # NOT a skip. Five checks exist to compare what the server EMITS against
        # what en.json defines, and with nowhere to look they have a denominator
        # of zero — which this file's own rule says is an error, not a pass.
        # The sources are public; the run just has to be told where they are.
        rep.errors.append(
            "no Rust emitter sources found — pass --server-src <checkout> (e.g. a "
            "CIRISServer clone at the version this client pairs with). Five checks "
            "could not run, and a bundle guard that cannot see the emitters is "
            "reporting on half the problem"
        )
        for name in (
            "server-id-reachable",
            "server-id-coverage",
            "server-id-text",
            "server-id-single-valued",
            "unlocalized-debt-current",
        ):
            rep.lines.append(
                f"  FAIL  {name:<24}: no emitter source — pass --server-src <checkout>"
            )
    else:
        server_ids = server_message_ids(root)
        msgs, n = check_server_ids_resolvable(root, en, server_ids)
        rep.record("server-id-reachable", msgs, n, severity="error", unit="emitted id(s)")
        msgs, n = check_server_ids_covered(root, en, server_ids)
        rep.record("server-id-coverage", msgs, n, severity="warning", unit="emitted id(s)")

        msgs, n = check_server_id_text_matches_source(root, en)
        rep.record("server-id-text", msgs, n, severity="error", unit="emitted id(s)")
        msgs, n = check_server_ids_are_single_valued(root)
        rep.record("server-id-single-valued", msgs, n, severity="error", unit="emitted id(s)")
        if debt_list_applies:
            msgs, n = check_known_unlocalized_list_is_current(root, en)
            rep.record("unlocalized-debt-current", msgs, n, severity="error", unit="known id(s)")

    msgs, n = check_placeholder_parity(root, langs, en)
    rep.record("placeholder-parity", msgs, n, severity="error", unit="value compare(s)")

    msgs, n = check_translation_drift(root, langs, en)
    rep.record("translation-drift", msgs, n, severity="warning", unit="key compare(s)")

    return rep


def _print_report(root: Path, rep: Report, strict: bool) -> int:
    canonical = root / CANONICAL_BUNDLE
    print("Localization guard — CIRIS client bundles")
    try:
        en_keys = len(flat_values(load_json(canonical / "en.json")))
        langs = len(manifest_languages(canonical))
        print(
            f"   canonical: {CANONICAL_BUNDLE}  "
            f"({en_keys} keys, {langs} languages, {len(MIRROR_BUNDLES)} runtime bundles)"
        )
    except Exception:  # noqa: BLE001 - reported as an error below
        print(f"   canonical: {CANONICAL_BUNDLE}  (unreadable)")
    print()
    print("Checks (each line reports what it examined — a zero finding over a zero denominator is not evidence):")
    for line in rep.lines:
        print(line)
    print()

    if rep.errors:
        print("ERRORS (block):")
        for e in rep.errors:
            print(f"  - {e}")
        print()
    if rep.warnings:
        sev = "ERRORS (--strict)" if strict else "WARNINGS (translation drift — falls back to English at runtime)"
        print(sev + ":")
        for w in rep.warnings:
            print(f"  - {w}")
        print()

    failed = bool(rep.errors) or (strict and bool(rep.warnings))
    if failed:
        print(f"localization check FAILED ({len(rep.errors)} error(s), {len(rep.warnings)} warning(s))")
        if rep.warnings and not rep.errors:
            print("   Fix: run the `localize-ui` Claude workflow to fill missing translations.")
        return 1

    if rep.warnings:
        print(f"localization check passed with {len(rep.warnings)} warning(s) (no structural errors)")
    else:
        print("localization check passed (no errors, no warnings)")
    return 0


# ===========================================================================
# --self-test: break it on purpose, prove each check can fail
# ===========================================================================

_FIXTURE_EN = {
    "_meta": {"translator": "fixture"},
    "app_name": "CIRIS",
    "mobile": {"greeting": "Hello {name}", "count": "%d items"},
    # Must equal _FIXTURE_RS's emitted text — `server-id-text` compares them.
    "nav": {"home": "Home, the operator landing surface."},
}
_FIXTURE_DE = {
    "_meta": {"translator": "fixture"},
    "app_name": "CIRIS",
    "mobile": {"greeting": "Hallo {name}", "count": "%d Elemente"},
    "nav": {"home": "Startseite"},
}
_FIXTURE_MANIFEST = {"version": "test", "languages": {"en": {}, "de": {}}}
_FIXTURE_KT = (
    "package fixture\n"
    'val a = localizedString("mobile.greeting")\n'
    'val b = getString("nav.home")\n'
)
# One server emission site, in the (id, english_text) pair shape every operator
# surface uses. Gives server-id-* a non-zero denominator in the fixture.
_FIXTURE_RS = (
    "fn m(id: &str, text: &str) -> Value { json!({ \"id\": id, \"text\": text }) }\n"
    "fn home() -> Value { m(\"nav.home\", \"Home, the operator landing surface.\") }\n"
)


def _write_json(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _build_fixture(root: Path) -> None:
    canonical = root / MIRROR_BUNDLES[0]
    _write_json(canonical / "en.json", _FIXTURE_EN)
    _write_json(canonical / "de.json", _FIXTURE_DE)
    _write_json(canonical / "manifest.json", _FIXTURE_MANIFEST)
    for b in MIRROR_BUNDLES[1:]:
        (root / b).mkdir(parents=True, exist_ok=True)
        for f in canonical.glob("*.json"):
            shutil.copy2(f, root / b / f.name)
    kt = root / COMMON_MAIN / "kotlin" / "Fixture.kt"
    kt.parent.mkdir(parents=True, exist_ok=True)
    kt.write_text(_FIXTURE_KT, encoding="utf-8")
    rs = root / SERVER_SRC / "fixture.rs"
    rs.parent.mkdir(parents=True, exist_ok=True)
    rs.write_text(_FIXTURE_RS, encoding="utf-8")


def _mutations() -> List[Tuple[str, str, Any, str]]:
    """(label, expected severity, mutate(root), substring the message must contain)."""

    def del_key(root: Path) -> None:
        p = root / MIRROR_BUNDLES[0] / "de.json"
        doc = load_json(p)
        del doc["nav"]["home"]
        _write_json(p, doc)
        _resync(root)

    def blank_value(root: Path) -> None:
        p = root / MIRROR_BUNDLES[0] / "de.json"
        doc = load_json(p)
        doc["nav"]["home"] = "   "
        _write_json(p, doc)
        _resync(root)

    def corrupt_named_placeholder(root: Path) -> None:
        p = root / MIRROR_BUNDLES[0] / "de.json"
        doc = load_json(p)
        doc["mobile"]["greeting"] = "Hallo {nmae}"
        _write_json(p, doc)
        _resync(root)

    def corrupt_printf_placeholder(root: Path) -> None:
        p = root / MIRROR_BUNDLES[0] / "de.json"
        doc = load_json(p)
        doc["mobile"]["count"] = "%s Elemente"
        _write_json(p, doc)
        _resync(root)

    def drop_placeholder(root: Path) -> None:
        p = root / MIRROR_BUNDLES[0] / "de.json"
        doc = load_json(p)
        doc["mobile"]["greeting"] = "Hallo"
        _write_json(p, doc)
        _resync(root)

    def desync(idx: int):
        def go(root: Path) -> None:
            p = root / MIRROR_BUNDLES[idx] / "de.json"
            doc = load_json(p)
            doc["nav"]["home"] = "STALE"
            _write_json(p, doc)

        return go

    def extra_file_in_mirror(root: Path) -> None:
        _write_json(root / MIRROR_BUNDLES[2] / "zz.json", {"app_name": "x"})

    def invalid_json_mirror(root: Path) -> None:
        (root / MIRROR_BUNDLES[3] / "de.json").write_text("{ not json", encoding="utf-8")

    def invalid_json_canonical_en(root: Path) -> None:
        (root / MIRROR_BUNDLES[0] / "en.json").write_text("{ not json", encoding="utf-8")

    def new_flat_dotted_key(root: Path) -> None:
        """A newly-added key in the flat shape — how 0c728b1 introduced the bug."""
        p = root / MIRROR_BUNDLES[0] / "en.json"
        doc = load_json(p)
        doc["mesh.brand_new_flat_key"] = "unreachable at runtime"
        _write_json(p, doc)
        # de gets it nested — the exact #366 shape divergence between two files
        pd = root / MIRROR_BUNDLES[0] / "de.json"
        dd = load_json(pd)
        dd["mesh"] = {"brand_new_flat_key": "zur Laufzeit unerreichbar"}
        _write_json(pd, dd)
        _resync(root)

    def unknown_kotlin_key(root: Path) -> None:
        kt = root / COMMON_MAIN / "kotlin" / "Fixture.kt"
        kt.write_text(_FIXTURE_KT + 'val c = getString("nav.nonexistent")\n', encoding="utf-8")

    def flatten_a_nested_key(root: Path) -> None:
        """THE mutation that matters — the exact shape that shipped in 0c728b1.

        Take a CORRECTLY NESTED key and store it as a literal dotted top-level
        key instead, in every language. Afterwards the bundle is still valid
        JSON, still byte-identical across all four runtime bundles, still
        carries the identical flattened key set — and the string is dead in
        every language including English. A key-set comparison sees nothing;
        key-resolvability must go red. (Asserted explicitly in self_test().)
        """
        _flatten_nav_home(root)

    def kotlin_key_flat_only(root: Path) -> None:
        """The blind spot that shipped: en.json HAS the address, flattened, but
        resolveKey cannot reach it. The old checker called this OK."""
        p = root / MIRROR_BUNDLES[0] / "en.json"
        doc = load_json(p)
        doc["settings.theme"] = "Theme"
        _write_json(p, doc)
        _resync(root)
        kt = root / COMMON_MAIN / "kotlin" / "Fixture.kt"
        kt.write_text(_FIXTURE_KT + 'val c = getString("settings.theme")\n', encoding="utf-8")

    def manifest_lists_missing_lang(root: Path) -> None:
        p = root / MIRROR_BUNDLES[0] / "manifest.json"
        doc = load_json(p)
        doc["languages"]["fr"] = {}
        _write_json(p, doc)
        _resync(root)

    def unlisted_locale_file(root: Path) -> None:
        for b in MIRROR_BUNDLES:
            _write_json(root / b / "xx.json", _FIXTURE_DE)

    def extra_key(root: Path) -> None:
        p = root / MIRROR_BUNDLES[0] / "de.json"
        doc = load_json(p)
        doc["nav"]["ghost"] = "Geist"  # no such key in en.json
        _write_json(p, doc)
        _resync(root)

    def empty_bundle(root: Path) -> None:
        """Denominator zero: the instrument looks at nothing."""
        for b in MIRROR_BUNDLES:
            for f in (root / b).glob("*.json"):
                f.unlink()

    def missing_mirror_dir(root: Path) -> None:
        shutil.rmtree(root / MIRROR_BUNDLES[2])

    def server_id_uncovered(root: Path) -> None:
        """A new operator sentence emitted with an id en.json never defines."""
        rs = root / SERVER_SRC / "fixture.rs"
        rs.write_text(
            _FIXTURE_RS
            + 'fn refused() -> Value { m("operator.refusal.brand_new", "A refusal nobody translated.") }\n',
            encoding="utf-8",
        )

    def server_id_defined_but_flat(root: Path) -> None:
        """en.json defines the emitted id — in the shape the resolver cannot read."""
        _flatten_nav_home(root)

    def no_server_sources(root: Path) -> None:
        """Nowhere to look on the server side.

        This used to assert the generic zero-denominator error. It now asserts
        the SPECIFIC one, because the two are different diagnoses: "I scanned
        and found nothing" is a defect in the emitters, while "I had nowhere to
        scan" is a defect in how the run was invoked, and only the second has a
        remedy the reader can act on. The mutation matters as much as ever —
        this is the tree the `--server-src` pointer must NOT rescue, which is
        why the pointer is scoped to one root ([EMITTER_FOR_ROOT]).
        """
        shutil.rmtree(root / SERVER_SRC)

    def conflicting_server_id_text(root: Path) -> None:
        """One id, two sentences — which every other check reads as clean.

        The id set is right, the key resolves, the placeholders match, and
        `server-id-text` compares en.json against whichever emission the
        scanner reached first. Found live on
        `commons_surface.refusal.objection_absent`.
        """
        rs = root / SERVER_SRC / "fixture.rs"
        rs.write_text(
            rs.read_text(encoding="utf-8")
            + '\nfn other() -> Value { m("nav.home", "A DIFFERENT sentence under the same id.") }\n',
            encoding="utf-8",
        )

    def server_id_text_truncated(root: Path) -> None:
        r"""THE 2026-08-05 defect: en.json carries a PREFIX of what the server emits.

        Key sets, resolvability, placeholder parity and bundle mirroring all stay
        green over a value cut mid-word — 55 real ids shipped that way, because
        the extractor's regex stopped at the first `\` of a continued Rust
        literal. Nothing compared VALUES until `server-id-text`.
        """
        _truncate_nav_home(root)

    return [
        ("nested key -> flat dotted key (THE 0c728b1 bug)", "error", flatten_a_nested_key, "resolveKey"),
        ("en.json value is a PREFIX of the emitted text (THE 80-char truncation)", "error", server_id_text_truncated, "TRUNCATED"),
        ("delete a key from de.json", "warning", del_key, "missing 1"),
        ("blank a value in de.json", "warning", blank_value, "empty 1"),
        ("extra key in de.json (not in en.json)", "warning", extra_key, "extra 1"),
        ("locale file the manifest never lists", "error", unlisted_locale_file, "manifest does not list"),
        ("corrupt {name} -> {nmae}", "error", corrupt_named_placeholder, "placeholder drift"),
        ("corrupt %d -> %s", "error", corrupt_printf_placeholder, "placeholder drift"),
        ("drop {name} entirely", "error", drop_placeholder, "placeholder drift"),
        ("desync desktopApp bundle", "error", desync(1), "desktopApp"),
        ("desync androidApp bundle", "error", desync(2), "androidApp"),
        ("desync iosApp bundle", "error", desync(3), "iosApp"),
        ("extra file in androidApp bundle", "error", extra_file_in_mirror, "extra file"),
        ("invalid JSON in iosApp bundle", "error", invalid_json_mirror, "invalid JSON"),
        ("invalid JSON in canonical en.json", "error", invalid_json_canonical_en, "invalid JSON"),
        ("new flat dotted key (unreachable)", "error", new_flat_dotted_key, "resolveKey"),
        ("Kotlin key absent from en.json", "error", unknown_kotlin_key, "do not resolve"),
        ("Kotlin key present but flat-only", "error", kotlin_key_flat_only, "do not resolve"),
        ("manifest lists a language with no file", "error", manifest_lists_missing_lang, "fr.json is missing"),
        ("every bundle emptied (zero denominator)", "error", empty_bundle, "looked at nothing"),
        ("androidApp bundle dir deleted", "error", missing_mirror_dir, "missing"),
        ("server emits an id en.json never defines", "warning", server_id_uncovered, "no en.json entry"),
        ("server id defined but flat (unreachable)", "error", server_id_defined_but_flat, "DEFINED in en.json"),
        ("one id emitted with TWO different texts", "error", conflicting_server_id_text, "CONFLICTING English text"),
        ("nowhere to scan for emissions", "error", no_server_sources, "pass --server-src"),
    ]
def _truncate_nav_home(root: Path) -> None:
    r"""The 2026-08-05 defect, reproduced: en.json carries a PREFIX of the text the
    server actually emits. Key sets, resolvability, placeholders and mirroring all
    stay green — 55 real ids shipped this way, cut mid-word at ~80 chars, because
    the extractor's regex stopped at the first `\` of a continued Rust literal."""
    canonical = root / MIRROR_BUNDLES[0]
    path = canonical / "en.json"
    doc = load_json(path)
    doc["nav"]["home"] = doc["nav"]["home"][:4]
    _write_json(path, doc)
    _resync(root)



def _flatten_nav_home(root: Path) -> None:
    """Re-store the nested ``nav.home`` as a literal dotted top-level key in every
    locale, then re-mirror. Nothing else about the bundle changes."""
    canonical = root / MIRROR_BUNDLES[0]
    for f in locale_files(canonical):
        doc = load_json(f)
        if "nav" not in doc or not isinstance(doc["nav"], dict) or "home" not in doc["nav"]:
            continue
        value = doc["nav"].pop("home")
        if not doc["nav"]:
            del doc["nav"]
        doc["nav.home"] = value
        _write_json(f, doc)
    _resync(root)


def _resync(root: Path) -> None:
    """Re-mirror canonical into the other three bundles (so a mutation aimed at
    one check doesn't trip bundle-mirror as a side effect)."""
    canonical = root / MIRROR_BUNDLES[0]
    for b in MIRROR_BUNDLES[1:]:
        target = root / b
        for f in target.glob("*.json"):
            f.unlink()
        for f in canonical.glob("*.json"):
            shutil.copy2(f, target / f.name)


def _prove_the_debt_list_is_kept_honest(root: Path) -> int:
    """Both halves of `unlocalized-debt-current`, against the REAL tree.

    Proven here rather than as a fixture mutation because the list is a
    statement about this repository's sources: a synthetic tree emits none of
    them, so every entry reads as stale and the check would fire on every other
    mutation instead of on its own.

    It therefore needs the emitters, and says so rather than skipping: without
    them every entry reads as GONE, so the real-tree half would fail for the
    absence rather than for a defect AND the GONE half would pass VACUOUSLY —
    a green line proving nothing, which is the worse of the two. Point
    `--server-src` at a checkout.

      * COVERED — an entry that has since gained an en.json entry must fail, or
        the debt is never actually paid down;
      * GONE — an entry no longer emitted anywhere must fail, because a dead
        exemption is invisible until it quietly covers for a future
        re-introduction of the same id.
    """
    if not _emitter_src_dirs(root):
        print(
            "  FAIL  the debt list's honesty proof needs the emitters: pass "
            "--server-src <checkout>. Without them every entry reads as GONE, and "
            "the GONE half of this proof would pass without proving anything"
        )
        return 1

    global KNOWN_UNLOCALIZED  # noqa: PLW0603 - restored in the finally below
    failures = 0
    en = load_json(root / CANONICAL_BUNDLE / "en.json")

    clean, _ = check_known_unlocalized_list_is_current(root, en)
    if clean:
        print("  FAIL  the debt list is not currently honest:")
        for m in clean:
            print(f"          {m}")
        failures += 1

    # COVERED: pretend en.json defines the first entry.
    if KNOWN_UNLOCALIZED:
        doctored = json.loads(json.dumps(en))
        node = doctored
        parts = KNOWN_UNLOCALIZED[0].split(".")
        for k in parts[:-1]:
            node = node.setdefault(k, {})
            if not isinstance(node, dict):
                node = doctored
                break
        else:
            node[parts[-1]] = "now covered"
        msgs, _ = check_known_unlocalized_list_is_current(root, doctored)
        if not any("HAVE an en.json entry" in m for m in msgs):
            print("  FAIL  a COVERED debt entry did not fail the freshness check")
            failures += 1

    # GONE: an id nothing emits.
    original = KNOWN_UNLOCALIZED
    KNOWN_UNLOCALIZED = original + ("ghost.id.that.is.not.emitted",)
    try:
        msgs, _ = check_known_unlocalized_list_is_current(root, en)
        if not any("NO LONGER EMITTED" in m for m in msgs):
            print("  FAIL  a GONE debt entry did not fail the freshness check")
            failures += 1
    finally:
        KNOWN_UNLOCALIZED = original

    if failures == 0:
        print(
            f"  ok    the debt list is honest in both directions "
            f"({len(KNOWN_UNLOCALIZED)} entry(ies): covered and gone both fail)"
        )
    return failures


def _prove_test_fixtures_are_not_server_emissions(root: Path) -> int:
    """Assert that a `#[cfg(test)]` module cannot invent a server-emitted id.

    The scanner hunts for the pair `"dotted.id", "an English sentence"`, and a
    Rust TEST FIXTURE has exactly that shape:

        raise(Warning::error("t.reduced", "a plane is shed"));

    `src/degradation.rs` produced three such phantoms on first contact — ids no
    server will ever emit, each demanding an en.json entry that would put test
    strings into the shipped product bundle in 29 languages.

    That is worth a prover of its own rather than a mutation entry, because the
    failure direction is the dangerous one: the check invented work and *looked
    like diligence while doing it*. A gate that manufactures findings is trusted
    exactly as long as it takes someone to look at one — and then not at all,
    including for the real findings sitting next to it.

    So: add a test module emitting an id en.json never defines, and show that
    (a) nothing fires, and (b) the emitted-id DENOMINATOR is unchanged — because
    a stripper that silently ate real ids too would also produce a green run.
    """
    _build_fixture(root)
    rs = root / SERVER_SRC / "fixture.rs"
    before = run_checks_synthetic(root)
    before_ids = len(server_message_ids(root))

    # The test module is inserted BEFORE the file's production emission site,
    # not appended. Appended at EOF, over-eating is invisible: blanking to
    # end-of-file destroys nothing, so a matcher that runs past the module's
    # real close still passes. Every construct here made an earlier version do
    # exactly that — `'{'` in particular ran the matcher to EOF.
    hostile = (
        "#[cfg(test)]\nmod tests {\n"
        "    // a comment with an unbalanced } brace\n"
        "    /* and a block comment with an unbalanced { one */\n"
        '    fn lit() -> &\'static str { "a } and a \\" inside" }\n'
        # UNBALANCED on purpose. An earlier fixture carried both '{' and '}',
        # which cancel — so deleting the char-literal handling outright still
        # passed. A fixture whose hazards balance tests nothing.
        "    fn open_brace() -> char { '{' }\n"
        "    fn quote() -> char { '\\'' }\n"
        "    fn unicode_close() -> char { '\\u{7d}' }\n"
        "    mod nested { fn d() { raise(m(\"t.nested\", \"a phantom one level down\")); } }\n"
        '    fn t() { raise(m("t.phantom", "an id no server will ever emit")); }\n'
        "}\n\n"
    )
    rs.write_text(hostile + rs.read_text(encoding="utf-8"), encoding="utf-8")
    after = run_checks_synthetic(root)
    after_ids = len(server_message_ids(root))

    failures = 0
    if after.errors or after.warnings:
        print("  FAIL  a #[cfg(test)] fixture was scanned as a server emission:")
        for m in after.errors + after.warnings:
            print(f"          {m}")
        failures += 1
    elif after_ids != before_ids:
        print(
            f"  FAIL  test-module stripping changed the emitted-id count "
            f"({before_ids} -> {after_ids}); a stripper that eats REAL ids also runs green"
        )
        failures += 1
    elif before.errors or before.warnings:
        print("  FAIL  the fixture was not clean before the test module was added")
        failures += 1
    else:
        print(
            f"  ok    a #[cfg(test)] fixture emits nothing and moves no denominator "
            f"({before_ids} id(s) before and after)"
        )
    return failures


def _prove_keyset_comparison_is_blind(root: Path) -> int:
    """Assert, in code, the premise of CIRISServer#366.

    Flatten a nested key into a dotted top-level key and show that:
      * the flattened key set is IDENTICAL before and after (so the old
        key-parity check could not have failed, and did not),
      * every other check is still green (valid JSON, four bundles byte-identical,
        no drift, no placeholder change),
      * key-resolvability alone goes red.

    If this ever stops holding, the mutation above has stopped reproducing the
    bug it claims to reproduce, and the self-test says so.
    """
    _build_fixture(root)
    canonical = root / MIRROR_BUNDLES[0]
    before = {f.name: set(flat_values(load_json(f))) for f in locale_files(canonical)}
    _flatten_nav_home(root)
    after = {f.name: set(flat_values(load_json(f))) for f in locale_files(canonical)}
    rep = run_checks_synthetic(root)
    resolvability = [e for e in rep.errors if e.startswith("key-resolvability")]
    other_errors = [e for e in rep.errors if not e.startswith("key-resolvability")]
    # reference-coverage and server-id-reachable also fire here — the Kotlin call
    # site and the Rust emission site for nav.home both stop resolving. Both are
    # correct: the same defect seen from the two consumer sides.
    other_errors = [
        e for e in other_errors if not e.startswith(("reference-coverage", "server-id-reachable"))
    ]
    problems: List[str] = []
    if before != after:
        problems.append("the flattened key set CHANGED — the mutation is not the #366 shape")
    if not resolvability:
        problems.append("key-resolvability did not fire")
    if other_errors:
        problems.append(f"unexpected extra errors: {other_errors}")
    if rep.warnings:
        problems.append(f"unexpected drift warnings: {rep.warnings}")
    if problems:
        print("  FAIL  key-set comparison blindness proof:")
        for p in problems:
            print(f"          {p}")
        return 1
    print(
        "  ok    key-set comparison blindness proof: flattening a nested key leaves the key set "
        "BYTE-FOR-BYTE identical (old check: green) while key-resolvability goes red"
    )
    return 0


def self_test() -> int:
    print("Localization guard SELF-TEST — every check is broken on purpose and must fire")
    print()
    failures = 0
    with tempfile.TemporaryDirectory(prefix="loc-guard-selftest-") as td:
        pristine = Path(td) / "pristine"
        _build_fixture(pristine)
        rep = run_checks_synthetic(pristine)
        if rep.errors or rep.warnings:
            print("  FAIL  pristine fixture is not clean:")
            for m in rep.errors + rep.warnings:
                print(f"          {m}")
            failures += 1
        else:
            print(f"  ok    pristine fixture: clean ({len(rep.lines)} checks ran)")

        for label, severity, mutate, needle in _mutations():
            work = Path(td) / "work"
            if work.exists():
                shutil.rmtree(work)
            _build_fixture(work)
            mutate(work)
            rep = run_checks_synthetic(work)
            bucket = rep.errors if severity == "error" else rep.warnings
            other = rep.warnings if severity == "error" else rep.errors
            hit = [m for m in bucket if needle in m]
            strict_rc = 1 if (rep.errors or rep.warnings) else 0
            default_rc = 1 if rep.errors else 0
            want_rc = 1 if severity == "error" else 0
            if not hit:
                print(f"  FAIL  {label}: no {severity} mentioning {needle!r}")
                for m in rep.errors + rep.warnings:
                    print(f"          got: {m}")
                failures += 1
            elif default_rc != want_rc or strict_rc != 1:
                print(
                    f"  FAIL  {label}: caught, but exit codes wrong "
                    f"(default={default_rc} want {want_rc}, --strict={strict_rc} want 1)"
                )
                failures += 1
            else:
                shown = hit[0] if len(hit[0]) <= 110 else hit[0][:107] + "..."
                print(f"  ok    {label}  -> {severity} (exit {default_rc}/strict {strict_rc}): {shown}")
                if severity == "error" and other:
                    for m in other:
                        print(f"          (also warned: {m})")

        failures += _prove_keyset_comparison_is_blind(Path(td) / "blind")
        failures += _prove_test_fixtures_are_not_server_emissions(Path(td) / "cfgtest")
        failures += _prove_the_debt_list_is_kept_honest(Path("."))

    print()
    if failures:
        print(f"SELF-TEST FAILED: {failures} check(s) did not fire — this gate cannot be trusted")
        return 1
    print(f"SELF-TEST PASSED: {len(_mutations())} mutation(s), every one caught with a true message")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="CIRIS client localization bundle guard")
    ap.add_argument(
        "--server-src",
        action="append",
        default=[],
        metavar="PATH",
        help="checkout containing the Rust sources that emit localized message "
             "ids (a repo root, or its src/ directly). Repeatable. Required "
             "whenever <root>/src is not one — the bundles live here, the "
             "emitters live in the consumers, and the five server-id-* checks "
             "compare the two. There is no way to declare the absence: without "
             "this the run FAILS and tells you to pass it",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="treat translation drift (missing/empty/extra keys) as a failure too",
    )
    ap.add_argument(
        "--self-test",
        action="store_true",
        help="mutation-verify the guard against a synthetic bundle and exit",
    )
    ap.add_argument(
        "--root",
        default=str(REPO_ROOT),
        help="repo root to check (default: the repo this script lives in)",
    )
    args = ap.parse_args()

    global EMITTER_ROOTS, EMITTER_FOR_ROOT  # noqa: PLW0603 - CLI-set
    EMITTER_ROOTS = tuple(Path(p) for p in args.server_src)

    if args.self_test:
        # `_prove_the_debt_list_is_kept_honest` grades the real tree at CWD;
        # every other part of the self-test grades a fixture, and must not see
        # the pointer.
        EMITTER_FOR_ROOT = Path(".").resolve()
        return self_test()

    EMITTER_FOR_ROOT = Path(args.root).resolve()

    root = Path(args.root).resolve()
    if not (root / CANONICAL_BUNDLE).exists():
        print(f"ERROR: canonical bundle not found at {root / CANONICAL_BUNDLE}")
        return 1
    return _print_report(root, run_checks(root), args.strict)


if __name__ == "__main__":
    sys.exit(main())
