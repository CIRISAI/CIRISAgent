"""Graph content must not be able to close an SVG element.

THE BUG. `/v1/memory/visualize/graph` renders the memory graph as SVG and
serves it via `HTMLResponse`. `generate_html_wrapper` escapes the values it
receives — `hours`, `layout`, `node_count` — and says so in a comment. The SVG
body it wraps did not: `node.id` and `edge.relationship` were interpolated raw
into `<title>`, `<text>` and a `data-` attribute.

That is stored XSS, not reflected. The payload is not a query parameter a
victim must be tricked into following; it is a NODE ID, written once by
whatever created the node, and it fires for whoever opens the visualiser
afterwards. Any path that lets remembered content influence a node id is a
write primitive for it.

The wrapper being hardened is what made this survive review — the file reads
as though escaping is handled, and the one comment about XSS sits on the half
that was fine.

These tests assert on `generate_svg` rather than through the route, so they
still hold if the wrapper, the route, or the response class is replaced.
"""

from __future__ import annotations

from typing import List

import pytest

from ciris_engine.logic.adapters.api.routes.memory_visualization import generate_svg
from ciris_engine.schemas.services.graph_core import GraphEdge, GraphNode, GraphScope, NodeType

#: Each closes the element it lands in and opens a script.
PAYLOADS = [
    '</title><script>alert(1)</script>',
    '</text><script>alert(1)</script>',
    '"><script>alert(1)</script>',
    "'><img src=x onerror=alert(1)>",
    '</title><img src=x onerror=alert(1)><title>',
    '<svg onload=alert(1)>',
]


def _node(node_id: str) -> GraphNode:
    return GraphNode(id=node_id, type=NodeType.CONCEPT, scope=GraphScope.LOCAL, attributes={})


def _assert_inert(svg: str, payload: str) -> None:
    """The payload may still be VISIBLE — it must not be STRUCTURAL.

    Asserting `"onerror=" not in svg` would be wrong: correctly escaped, the
    page contains the literal text `&lt;img src=x onerror=alert(1)&gt;`, which
    holds that substring and executes nothing. What must not survive is the
    markup: a `<` that opens a tag, or a `"` that ends an attribute.
    """
    assert payload not in svg, "the payload reached the document verbatim"
    assert "<script" not in svg.lower()
    assert "<img" not in svg.lower()
    # Every `<` in the output must belong to an element we emitted.
    for tag in ("<circle", "<text", "<title", "</title>", "</text>", "</circle>", "<path", "<g", "</g>", "<svg", "</svg>", "<style", "</style>", "<defs", "</defs>", "<marker", "</marker>", "<polygon", "<rect", "<line"):
        svg = svg.replace(tag, "")
    assert "<" not in svg, f"an unaccounted-for `<` survived: {svg[max(0, svg.index('<') - 40):svg.index('<') + 40]!r}"


@pytest.mark.parametrize("payload", PAYLOADS)
def test_node_id_cannot_inject_markup(payload: str) -> None:
    svg = generate_svg(nodes=[_node(payload)], edges=[], layout="hierarchy", width=800, height=600)
    _assert_inert(svg, payload)


@pytest.mark.parametrize("payload", PAYLOADS)
def test_edge_relationship_cannot_inject_markup(payload: str) -> None:
    a, b = _node("node-a"), _node("node-b")
    edge = GraphEdge(source="node-a", target="node-b", relationship=payload, scope=GraphScope.LOCAL)

    svg = generate_svg(nodes=[a, b], edges=[edge], layout="hierarchy", width=800, height=600)
    _assert_inert(svg, payload)


def test_the_title_element_cannot_be_closed_early() -> None:
    """`<title>` is the sink with the longest reach — it holds the full id, untruncated."""
    svg = generate_svg(
        nodes=[_node("</title><script>alert(1)</script><title>x")],
        edges=[],
        layout="hierarchy",
        width=800,
        height=600,
    )
    assert svg.count("<title>") == svg.count("</title>"), "unbalanced <title> means the payload closed one"
    assert "<script>" not in svg


def test_the_data_attribute_cannot_be_broken_out_of() -> None:
    """`data-node-id="…"` — a bare `"` would end the attribute and start a new one."""
    svg = generate_svg(
        nodes=[_node('x" onmouseover="alert(1)')],
        edges=[],
        layout="hierarchy",
        width=800,
        height=600,
    )
    # The literal text may contain `onmouseover=`; what must not exist is a
    # closing quote followed by it, which is what would make it an attribute.
    assert '" onmouseover=' not in svg
    assert 'data-node-id="x"' not in svg


def test_ordinary_ids_are_still_readable() -> None:
    """Escaping must not mangle the normal case — these ids are the UI's labels."""
    svg = generate_svg(
        nodes=[_node("consent:partnered:abc123"), _node("metric_llm_tokens")],
        edges=[],
        layout="hierarchy",
        width=800,
        height=600,
    )
    assert "consent:partnered:abc123" in svg
    assert "metric_llm_tokens" in svg


def test_ampersand_becomes_one_entity_not_two() -> None:
    """Double-escaping would render `&amp;amp;` to the user."""
    svg = generate_svg(nodes=[_node("a&b")], edges=[], layout="hierarchy", width=800, height=600)
    assert "&amp;b" in svg
    assert "&amp;amp;" not in svg


def test_truncated_label_never_ends_mid_entity() -> None:
    """The label truncates at 20 chars; a split entity would emit malformed markup.

    Escaping happens before truncation precisely so the budget is counted over
    the text that is actually emitted.
    """
    svg = generate_svg(
        nodes=[_node("&" * 40)],
        edges=[],
        layout="hierarchy",
        width=800,
        height=600,
    )
    labels: List[str] = [seg.split("</text>")[0] for seg in svg.split('class="node-label"')[1:]]
    for label in labels:
        body = label.split(">", 1)[1] if ">" in label else label
        trimmed = body.replace("&amp;", "").replace(".", "")
        assert "&" not in trimmed, f"truncation split an entity: {body!r}"
