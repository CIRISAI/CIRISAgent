#!/usr/bin/env python3
"""Analyze nodes returned by timeline."""

import requests


def analyze_timeline():
    """Analyze timeline nodes and their edges."""
    # Login
    login_resp = requests.post(
        "http://localhost:8080/v1/auth/login", json={"username": "admin", "password": "qa_test_password_12345"}
    )
    token = login_resp.json()["access_token"]

    # Get timeline with 1000 nodes
    timeline_resp = requests.get(
        "http://localhost:8080/v1/memory/timeline",
        params={"hours": 168, "limit": 1000, "include_edges": True},
        headers={"Authorization": f"Bearer {token}"},
    )

    data = timeline_resp.json()["data"]
    nodes = data["memories"]
    edges = data.get("edges", [])

    print(f"Timeline returned {len(nodes)} nodes and {len(edges)} edges")

    # Count node types
    node_types = {}
    for node in nodes:
        node_type = node["type"]
        node_types[node_type] = node_types.get(node_type, 0) + 1

    print("\nNode types in timeline:")
    for ntype, count in sorted(node_types.items(), key=lambda x: x[1], reverse=True):
        print(f"  {ntype}: {count}")

    # Check which nodes have edges
    node_ids_with_edges = set()
    if edges:
        for edge in edges:
            node_ids_with_edges.add(edge["source_id"])
            node_ids_with_edges.add(edge["target_id"])

    print(f"\n{len(node_ids_with_edges)} nodes have edges")

    # Check if summary nodes are included
    summary_nodes = [n for n in nodes if n["type"].endswith("_summary")]
    print(f"\nFound {len(summary_nodes)} summary nodes in timeline:")
    for node in summary_nodes[:10]:
        print(f"  {node['id']} ({node['type']})")


if __name__ == "__main__":
    analyze_timeline()
