"""Regenerate ciris_adapters/ciris_accord_metrics/schemas/trace_format_v3_1_1.json from the enforced egress schema.

The current label is 3.1.1 (2.23.2: the context_manifest's ``facts``). Every definition is closed, so a member an
earlier file lacks needs a new label: an admitter selects the pinned schema by it (CC 3.1.5). Shipped files are
frozen: trace_format_v3_1_0.json is the v2.23.0 bytes, pinned by sha256, and is never regenerated.

The LlmCallData and ContextManifest definitions (and every event's egress_alterations member) come from
egress_schema.json_schema_for, so the published trace format is what egress enforces. The envelope comes from the
2.7.0 file, corrected against the 3.0.0-era wire (FSD/TRACE_WIRE_FORMAT.md §0). The test
test_context_manifest_trace.py compares the committed file to this generator.

    python3 tools/dev/gen_trace_format_schema.py          # write
    python3 tools/dev/gen_trace_format_schema.py --check  # exit 1 if the committed file differs
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SCHEMAS = ROOT / "ciris_adapters" / "ciris_accord_metrics" / "schemas"
SOURCE = SCHEMAS / "trace_format_v2_7_0.json"
TARGET = SCHEMAS / "trace_format_v3_1_1.json"


def build() -> dict:
    from ciris_adapters.ciris_accord_metrics import egress_schema as e
    from ciris_adapters.ciris_accord_metrics.services import AccordMetricsService

    d = json.loads(SOURCE.read_text(encoding="utf-8"))
    d["$id"] = "https://ciris.ai/schemas/trace_format_v3.1.1.json"
    d["title"] = "CIRIS Reasoning Trace v3.1.1"
    d["description"] = (
        "Complete reasoning trace from the CIRIS H3ERE pipeline (FSD/TRACE_WIRE_FORMAT.md). 3.1.0 adds the "
        "LLM_CALL context_manifest member (§5.10.1); 3.1.1 adds its `facts`. Stamped by lens-core at seal time from server 0.6 / persist "
        "v62.0; the LlmCallData and ContextManifest definitions are generated from the egress schema "
        "(tools/dev/gen_trace_format_schema.py) and compared to it by test."
    )
    d["properties"]["trace_schema_version"] = {
        "type": "string",
        "const": "3.1.1",
        "description": "Stamped by lens-core at seal time",
    }
    components = d["properties"]["components"]
    components.pop("maxItems", None)
    components["description"] = "Ordered reasoning components (one per captured event; LLM_CALL repeats per provider call)"
    d["properties"]["trace_id"] = {
        "type": "string",
        "minLength": 1,
        "description": "Trace identifier, assigned by the substrate at seal time",
    }
    tc = d["definitions"]["TraceComponent"]["properties"]
    tc["event_type"]["enum"] = [k for k in AccordMetricsService.EVENT_TO_COMPONENT if not k.startswith("ReasoningEvent.")]
    tc["component_type"]["enum"] = sorted(set(AccordMetricsService.EVENT_TO_COMPONENT.values()))
    tc["agent_id_hash"] = {
        "type": "string",
        "description": "sha256(signer pubkey)[:16], denormalized from the envelope; MUST equal the trace's",
    }
    # Every event's data definition is generated from the enforced egress schema (closed: additionalProperties
    # false), so each carries run_kind and egress_alterations and nothing egress would not ship. The 2.7.0
    # hand-written definitions are replaced, not kept beside them.
    for stale in [k for k in d["definitions"] if k.endswith("Data") or k.endswith("Result")]:
        del d["definitions"][stale]
    run_kind_ref = {"$ref": "#/definitions/RunKind", "x-ciris-min-level": "generic"}
    d["definitions"]["RunKind"] = {
        "type": "string",
        "enum": list(e.RUN_KIND_VALUES),
        "description": "CC 3.1.5 run_kind, in every component's signed data; mock is refused at federation admission",
    }
    d["definitions"]["EgressAlterations"] = e.json_schema_for({"egress_alterations": e.ALTERATIONS_SPEC})["properties"][
        "egress_alterations"
    ]
    branches = []
    for event_type in sorted(e.EVENT_SCHEMAS):
        name = "".join(part.capitalize() for part in event_type.split("_")) + "Data"
        data = e.json_schema_for(e.EVENT_SCHEMAS[event_type])
        if "context_manifest" in data["properties"]:
            cm = data["properties"].pop("context_manifest")
            cm_def = {k: v for k, v in cm.items() if k not in ("type", "x-ciris-min-level")}
            cm_def["type"] = "object"
            d["definitions"]["ContextManifest"] = cm_def
            data["properties"]["context_manifest"] = {
                "$ref": "#/definitions/ContextManifest",
                "x-ciris-min-level": "detailed",
            }
        data["properties"]["run_kind"] = run_kind_ref
        data["properties"]["egress_alterations"] = {
            "$ref": "#/definitions/EgressAlterations",
            "x-ciris-min-level": "generic",
        }
        data["required"] = ["run_kind"]
        d["definitions"][name] = data
        branches.append(
            {
                "if": {"properties": {"event_type": {"const": event_type}}, "required": ["event_type"]},
                "then": {"properties": {"data": {"$ref": f"#/definitions/{name}"}}},
            }
        )
    d["definitions"]["TraceComponent"]["allOf"] = branches
    d["definitions"]["TraceComponent"]["properties"]["data"]["description"] = (
        "Component data, by event_type (the <Event>Data definitions); signed (FSD §8)"
    )
    return d


def render() -> str:
    return json.dumps(build(), indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != text:
            print(f"{TARGET.relative_to(ROOT)} is stale: run python3 tools/dev/gen_trace_format_schema.py")
            return 1
        return 0
    TARGET.write_text(text, encoding="utf-8")
    print(f"wrote {TARGET.relative_to(ROOT)} ({len(text)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
