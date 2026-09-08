#!/usr/bin/env python3
"""Rewrite `interactive_config` steps to one key per axis (CIRISClient#39).

    python3 tools/dev/migrate_interactive_config.py            # rewrite in place
    python3 tools/dev/migrate_interactive_config.py --check    # exit 1 if any would change

Five drifts, all structural -- in the schema, so every future step inherited
them. Each rule below is a pure function so the edge cases can be tested:

  optional/required   both defaulted False; a step with neither was a third
                      state nobody could act on. -> `required` only.
  field/field_name    three ways to name what a step collects; `field` was
                      declared and used by nothing. -> `fields` only.
  depends_on          admitted a dict nothing wrote. -> a list of step ids.
  field_id/name       two spellings for a field's identity, 15 vs 43. -> `name`.

IDEMPOTENT: running it twice changes nothing the second time, which is what
lets `--check` guard CI.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def migrate_required(step: dict) -> dict:
    """`optional`/`required` -> `required`. A step carrying both must agree."""
    if "optional" not in step:
        return step
    opt = step.pop("optional")
    if "required" in step:
        if step["required"] == opt:
            raise ValueError(
                f"{step.get('step_id')}: optional={opt} and required={step['required']} "
                f"contradict each other; fix the manifest by hand"
            )
        return step  # `required` already says it
    step["required"] = not opt
    return step


def migrate_fields(step: dict) -> dict:
    """`field_name` (and dead `field`) -> `fields: [{name}]`."""
    step.pop("field", None)
    if "field_name" not in step:
        return step
    name = step.pop("field_name")
    if "fields" in step:
        raise ValueError(f"{step.get('step_id')}: has both field_name and fields")
    step["fields"] = [{"name": name}]
    return step


def migrate_depends_on(step: dict) -> dict:
    """`depends_on` is ORDERING (a list of step ids). A dict there is a
    DISPLAY PREDICATE in the wrong slot, and it moves to `condition`.

    Exactly one existed: mcp_server/api_keys carried
    `depends_on: {"field": "auth_method", "values": ["api_key"]}` -- "show this
    step when auth_method is api_key". That is what `condition` is for. Its
    `values` form (membership) is kept alongside condition's `equals` /
    `not_equals`; they are all predicates on a collected value.
    """
    d = step.get("depends_on")
    if isinstance(d, dict):
        if "field" not in d:
            raise ValueError(
                f"{step.get('step_id')}: depends_on is a dict without `field`; "
                f"cannot tell whether it is ordering or a predicate -- fix by hand"
            )
        if "condition" in step:
            raise ValueError(f"{step.get('step_id')}: has a dict depends_on AND a condition")
        step["condition"] = step.pop("depends_on")
    return step


def migrate_field_ids(step: dict) -> dict:
    """Field-level `field_id` -> `name`."""
    for f in step.get("fields") or []:
        if isinstance(f, dict) and "field_id" in f:
            fid = f.pop("field_id")
            if "name" in f and f["name"] != fid:
                raise ValueError(f"{step.get('step_id')}: field has name={f['name']} and field_id={fid}")
            f["name"] = fid
    return step


def migrate_step(step: dict) -> dict:
    for rule in (migrate_required, migrate_fields, migrate_depends_on, migrate_field_ids):
        step = rule(step)
    return step


def migrate_manifest(data: dict) -> dict:
    ic = data.get("interactive_config")
    if isinstance(ic, dict):
        ic["steps"] = [migrate_step(s) for s in ic.get("steps", [])]
    return data


def patch_text(before: str) -> str:
    """Rewrite ONLY the lines that carry a retired key; every other byte stays.

    WHY NOT RE-SERIALISE. 49 of the 64 manifests are hand-formatted with MIXED
    styles inside one file -- some arrays inline, some expanded -- so no
    emitter reproduces them, and the first cut of this migration rewrote 50
    files to change 22. A diff nobody can review is a migration nobody can
    verify, and "reviewable" is requirement 4 of the language it serves
    (CIRISClient#39).

    Each substitution is same-line and preserves indentation, spacing and the
    trailing comma. All four retired keys occur ONLY inside interactive_config
    steps (checked across every manifest), so nothing else can match.

    THIS IS NOT THE SOURCE OF TRUTH. `migrate_manifest` is, and `main` refuses
    to write any file where `json.loads(patch_text(x)) != migrate_manifest(x)`.
    Two independent implementations must agree, or nothing happens.
    """
    import re

    text = before
    # optional -> required, in place. The sense inverts.
    text = re.sub(r'"optional":\s*true', '"required": false', text)
    text = re.sub(r'"optional":\s*false', '"required": true', text)
    # A step that carried BOTH now has two adjacent `required` lines; keep the
    # first, which was the original `required`. (One instance in the tree; the
    # oracle check below catches any shape this misses.)
    text = re.sub(
        r'(\n[ \t]*"required":\s*(?:true|false),)\n[ \t]*"required":\s*(?:true|false),',
        r"\1", text,
    )
    # field_name -> a one-field list, on the same line.
    text = re.sub(r'"field_name":\s*("(?:[^"\\]|\\.)*")', r'"fields": [{"name": \1}]', text)
    # A dict in the STEP-level ordering slot is a display predicate: rename the
    # key only. Scoped to the step's own indentation, read from this file's
    # `"step_id"` lines, because ConfigurationFieldDefinition legitimately has
    # its own dict-shaped `depends_on` one level deeper -- mcp_server carries
    # both on the same screen (line 137 is the step, 94 and 106 are fields),
    # and a blind rename rewrote the fields too. The oracle caught it.
    m = re.search(r'^([ \t]*)"step_id":', text, re.M)
    if m:
        indent = re.escape(m.group(1))
        text = re.sub(rf'^({indent})"depends_on":(\s*)\{{', r'\1"condition":\2{', text, flags=re.M)
    # field_id -> name.
    text = re.sub(r'"field_id":', '"name":', text)
    return text


def main(argv: list[str]) -> int:
    check = "--check" in argv
    changed = []
    for path in sorted((ROOT / "ciris_adapters").glob("*/manifest.json")):
        before = path.read_text(encoding="utf-8")
        original = json.loads(before)
        oracle = migrate_manifest(json.loads(before))
        if oracle == original:
            continue  # nothing retired here; the file is not touched
        after = patch_text(before)
        # THE ORACLE. The text patch must produce exactly the data the
        # data-level migration produces, or this refuses to write anything.
        try:
            patched = json.loads(after)
        except json.JSONDecodeError as e:
            raise SystemExit(f"{path}: text patch produced invalid JSON: {e}")
        if patched != oracle:
            raise SystemExit(
                f"{path}: the text patch and the data migration disagree; "
                f"refusing to write. Fix patch_text or migrate the file by hand."
            )
        if after != before:
            changed.append(path.relative_to(ROOT))
            if not check:
                path.write_text(after, encoding="utf-8")
    if check and changed:
        print("::error::these manifests still carry a retired interactive_config key:")
        for c in changed:
            print(f"  {c}")
        print("  Run tools/dev/migrate_interactive_config.py")
        return 1
    print(f"{'would change' if check else 'migrated'} {len(changed)} manifest(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
