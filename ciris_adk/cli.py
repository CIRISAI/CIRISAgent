"""Minimal code generation CLI for CIRIS ADK."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def init_adapter(name: str) -> None:
    path = Path(f"{name}.py")
    if path.exists():
        print(f"{path} already exists", file=sys.stderr)
        return
    path.write_text(
        '"""Auto-generated adapter stub."""\n'
        "from ciris_adk import ToolService\n\n"
        "class {class_name}(ToolService):\n    async def list_tools(self) -> list[str]:\n        return []\n\n    async def call_tool(self, name: str, *, arguments: dict | None = None, timeout: float | None = None) -> dict:\n        return {{}}\n".format(class_name=name.title().replace("_", ""))
    )
    print(f"Created {path}")


def init_wa(name: str) -> None:
    path = Path(f"{name}.py")
    if path.exists():
        print(f"{path} already exists", file=sys.stderr)
        return
    path.write_text(
        '"""Auto-generated wise authority stub."""\n'
        "from ciris_adk import WiseAuthorityService\n\n"
        "class {class_name}(WiseAuthorityService):\n"
        "    async def fetch_guidance(self, context: dict) -> str | None:\n        return None\n\n"
        "    async def send_deferral(self, thought_id: str, reason: str) -> bool:\n        return False\n".format(class_name=name.title().replace("_", ""))
    )
    print(f"Created {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ciris-adk")
    sub = parser.add_subparsers(dest="cmd", required=True)

    init_p = sub.add_parser("init", help="initialize a new component")
    init_p.add_argument("kind", choices=["adapter", "memory", "wa"], help="component type")
    init_p.add_argument("name", help="component name")
    init_p.add_argument("--lang", default="py", choices=["py", "ts"], help="language")

    args = parser.parse_args(argv)

    if args.cmd == "init" and args.lang == "py":
        if args.kind == "adapter":
            init_adapter(args.name)
        elif args.kind == "wa":
            init_wa(args.name)
        else:
            print("Unsupported component type", file=sys.stderr)
            return 1
    else:
        print("Unsupported command", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

