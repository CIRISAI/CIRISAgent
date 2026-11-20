"""Regenerate ciris_adapters/ciris_accord_metrics/schemas/trace_format_v3_1_0.json from the enforced egress schema.

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
TARGET = SCHEMAS / "trace_format_v3_1_0.json"


def build() -> dict:
    from ciris_adapters.ciris_accord_metrics import egress_schema as e
    from ciris_adapters.ciris_accord_metrics.services import AccordMetricsService

    d = json.loads(SOURCE.read_text(encoding="utf-8"))
    d["$id"] = "https://ciris.ai/schemas/trace_format_v3.1.0.json"
    d["title"] = "CIRIS Reasoning Trace v3.1.0"
    d["description"] = (
        "Complete reasoning trace from the CIRIS H3ERE pipeline (FSD/TRACE_WIRE_FORMAT.md). 3.1.0 adds the "
        "LLM_CALL context_manifest member (§5.10.1). Stamped by lens-core at seal time from server 0.6 / persist "
        "v62.0; the LlmCallData and ContextManifest definitions are generated from the egress schema "
        "(tools/dev/gen_trace_format_schema.py) and compared to it by test."
    )
    d["properties"]["trace_schema_version"] = {
        "type": "string",
        "const": "3.1.0",
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
    llm = e.json_schema_for(e.EVENT_SCHEMAS["LLM_CALL"])
    cm = llm["properties"].pop("context_manifest")
    cm_def = {k: v for k, v in cm.items() if k not in ("type", "x-ciris-min-level")}
    cm_def["type"] = "object"
    d["definitions"]["ContextManifest"] = cm_def
    llm["properties"]["context_manifest"] = {"$ref": "#/definitions/ContextManifest", "x-ciris-min-level": "detailed"}
    d["definitions"]["LlmCallData"] = llm
    d["definitions"]["EgressAlterations"] = e.json_schema_for({"egress_alterations": e.ALTERATIONS_SPEC})["properties"][
        "egress_alterations"
    ]
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
