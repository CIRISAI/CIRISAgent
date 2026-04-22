"""Generate a static REST endpoint inventory from FastAPI-style route decorators.

This script scans Python source files for decorator patterns like:
- @router.get("/path")
- @router.post("/path")
- @app.get("/path")

It emits JSON with method/path/file/line metadata for investigation workflows.
"""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

HTTP_METHODS: tuple[str, ...] = ("get", "post", "put", "patch", "delete", "options", "head")


@dataclass(frozen=True)
class EndpointRecord:
    method: str
    path: str
    file: str
    line: int
    function: str
    dependencies: tuple[str, ...]
    requires_auth: bool


@dataclass(frozen=True)
class ScanConfig:
    root: Path
    include_prefix: str


def _extract_path_from_decorator(decorator: ast.expr) -> Optional[tuple[str, str]]:
    if not isinstance(decorator, ast.Call):
        return None

    func = decorator.func
    if not isinstance(func, ast.Attribute):
        return None

    method_name = func.attr.lower()
    if method_name not in HTTP_METHODS:
        return None

    if not decorator.args:
        return None

    first_arg = decorator.args[0]
    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
        return method_name.upper(), first_arg.value

    return None


def _resolve_dependency_name(dep_expr: ast.expr) -> Optional[str]:
    if isinstance(dep_expr, ast.Name):
        return dep_expr.id
    if isinstance(dep_expr, ast.Attribute):
        return dep_expr.attr
    if isinstance(dep_expr, ast.Call):
        nested = dep_expr.func
        if isinstance(nested, ast.Name):
            return nested.id
        if isinstance(nested, ast.Attribute):
            return nested.attr
    return None


def _extract_dependencies(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...]:
    deps: list[str] = []
    all_defaults: Sequence[ast.expr] = list(node.args.defaults) + list(node.args.kw_defaults)
    for default in all_defaults:
        if default is None or not isinstance(default, ast.Call):
            continue

        dep_func = default.func
        dep_func_name: Optional[str] = None
        if isinstance(dep_func, ast.Name):
            dep_func_name = dep_func.id
        elif isinstance(dep_func, ast.Attribute):
            dep_func_name = dep_func.attr

        if dep_func_name != "Depends":
            continue

        if not default.args:
            deps.append("Depends")
            continue

        resolved = _resolve_dependency_name(default.args[0])
        if resolved:
            deps.append(resolved)
        else:
            deps.append("Depends")

    all_args = list(node.args.args) + list(node.args.kwonlyargs)
    for arg in all_args:
        annotation = arg.annotation
        if annotation is None:
            continue

        if not isinstance(annotation, ast.Subscript):
            continue

        annotated_target = annotation.value
        is_annotated = (
            isinstance(annotated_target, ast.Name)
            and annotated_target.id == "Annotated"
            or isinstance(annotated_target, ast.Attribute)
            and annotated_target.attr == "Annotated"
        )
        if not is_annotated:
            continue

        slice_expr = annotation.slice
        metadata_exprs: list[ast.expr] = []
        if isinstance(slice_expr, ast.Tuple):
            metadata_exprs = [expr for expr in slice_expr.elts[1:] if isinstance(expr, ast.expr)]

        for meta in metadata_exprs:
            if not isinstance(meta, ast.Call):
                continue
            meta_func = meta.func
            meta_func_name: Optional[str] = None
            if isinstance(meta_func, ast.Name):
                meta_func_name = meta_func.id
            elif isinstance(meta_func, ast.Attribute):
                meta_func_name = meta_func.attr
            if meta_func_name != "Depends":
                continue
            if meta.args:
                resolved = _resolve_dependency_name(meta.args[0])
                deps.append(resolved or "Depends")
            else:
                deps.append("Depends")

    return tuple(sorted(set(deps)))


def _requires_auth(dependencies: tuple[str, ...]) -> bool:
    auth_markers = ("auth", "current_user", "token", "permission", "rbac", "role", "oauth")
    return any(any(marker in dep.lower() for marker in auth_markers) for dep in dependencies)


def _iter_python_files(root: Path) -> Iterable[Path]:
    for file_path in root.rglob("*.py"):
        if "/.venv/" in f"/{file_path.as_posix()}/":
            continue
        if "__pycache__" in file_path.parts:
            continue
        yield file_path


def _scan_file(file_path: Path, config: ScanConfig) -> List[EndpointRecord]:
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    found: List[EndpointRecord] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue

        for decorator in node.decorator_list:
            extracted = _extract_path_from_decorator(decorator)
            if extracted is None:
                continue

            method, path = extracted
            rel_path = file_path.as_posix()
            if config.include_prefix and not rel_path.startswith(config.include_prefix):
                continue

            dependencies = _extract_dependencies(node)
            found.append(
                EndpointRecord(
                    method=method,
                    path=path,
                    file=rel_path,
                    line=getattr(node, "lineno", 0),
                    function=node.name,
                    dependencies=dependencies,
                    requires_auth=_requires_auth(dependencies),
                )
            )

    return found


def scan_endpoints(config: ScanConfig) -> List[EndpointRecord]:
    endpoints: List[EndpointRecord] = []
    for py_file in _iter_python_files(config.root):
        endpoints.extend(_scan_file(py_file, config))

    endpoints.sort(key=lambda r: (r.path, r.method, r.file, r.line))
    return endpoints


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate static endpoint inventory from decorators")
    parser.add_argument("--root", type=Path, default=Path("ciris_engine"), help="Root directory to scan")
    parser.add_argument(
        "--include-prefix",
        default="ciris_engine/logic/adapters/api",
        help="Only include files whose relative path starts with this prefix",
    )
    parser.add_argument("--output", type=Path, default=Path("reports/investigation/section1_items4_8/evidence/endpoints.json"))
    args = parser.parse_args()

    config = ScanConfig(root=args.root, include_prefix=args.include_prefix)
    endpoints = scan_endpoints(config)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "count": len(endpoints),
        "count_requires_auth": sum(1 for ep in endpoints if ep.requires_auth),
        "count_without_auth_dependency": sum(1 for ep in endpoints if not ep.requires_auth),
        "endpoints": [
            {
                "method": ep.method,
                "path": ep.path,
                "file": ep.file,
                "line": ep.line,
                "function": ep.function,
                "dependencies": list(ep.dependencies),
                "requires_auth": ep.requires_auth,
            }
            for ep in endpoints
        ],
    }
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Wrote {len(endpoints)} endpoints to {args.output}")


if __name__ == "__main__":
    main()
