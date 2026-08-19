"""A DSN must never reach a log unredacted.

GHSA-jghc-9g86-xg7c. A PostgreSQL DSN carries live credentials —
`postgresql://user:password@host/db` — and two log calls passed one straight
through: an INFO on every boot (stdout AND the log file) and a DEBUG. SQLite
DSNs are only paths, which is why this survived: the SQLite fleet was
unaffected and the exposure was invisible to anyone not running Postgres.

`_redact_dsn` already existed and was used at five other sites. These two simply
did not call it. So the guard is not "add redaction" — it is "no site may skip
the redaction that already exists".
"""

from __future__ import annotations

import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[4]
ENGINE = REPO / "ciris_engine"

#: Argument names that hold a connection string.
_DSN_NAMES = {"dsn", "_expected_dsn", "database_url", "db_url", "_dsn"}


def _is_redacted(node: ast.AST) -> bool:
    """Does this argument expression pass through a redaction helper?"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            fn = sub.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if "redact" in name.lower():
                return True
    return False


def _mentions_dsn(node: ast.AST) -> bool:
    """Is a DSN the VALUE being logged — not merely something tested?

    `"postgres" if dsn else "unset"` logs a literal; `dsn` is the condition and
    never reaches the output. A plain ast.walk flags it anyway, which is a false
    positive that would teach people to weaken this guard. So conditions are
    skipped and only value positions are inspected.
    """
    if isinstance(node, ast.IfExp):
        return _mentions_dsn(node.body) or _mentions_dsn(node.orelse)
    if isinstance(node, (ast.Compare, ast.BoolOp, ast.UnaryOp)):
        return False
    if isinstance(node, ast.Name):
        return node.id in _DSN_NAMES
    if isinstance(node, ast.Attribute):
        return node.attr in _DSN_NAMES or _mentions_dsn(node.value)
    return any(_mentions_dsn(child) for child in ast.iter_child_nodes(node))


def test_no_log_call_passes_a_raw_dsn() -> None:
    """Parse the calls; do not pattern-match them.

    A first attempt used a regex and produced three false positives — it matched
    the WORD "DSN" inside a message with no value in it, and `[^)]*` could not
    span a call containing parentheses, so it truncated before reaching the
    `_redact_dsn(...)` that was right there. Reading the AST asks the question
    that actually matters: is a dsn-valued expression an argument, and does it
    pass through redaction on the way?
    """
    offenders: list[str] = []
    for py in ENGINE.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"info", "debug", "warning", "error", "critical", "exception"}:
                continue
            obj = node.func.value
            if getattr(obj, "id", "") not in {"logger", "log", "logging"}:
                continue
            for arg in list(node.args) + [kw.value for kw in node.keywords]:
                if _mentions_dsn(arg) and not _is_redacted(arg):
                    offenders.append(f"{py.relative_to(REPO)}:{node.lineno}")

    assert not offenders, (
        "these log calls pass a DSN without redaction — a PostgreSQL DSN contains the "
        "live database password, and this leaked it to stdout and the log file on every "
        "boot (GHSA-jghc-9g86-xg7c):\n  " + "\n  ".join(sorted(set(offenders)))
    )


def test_redaction_actually_removes_the_password() -> None:
    """Pin the behaviour, not just the call site."""
    from ciris_engine.logic.persistence.db.core import _redact_dsn

    secret = "s3cretP@ss"
    out = _redact_dsn(f"postgresql://ciris:{secret}@10.0.0.5:5432/ciris_db?sslmode=require")
    assert secret not in out, f"password survived redaction: {out}"
    assert "ciris" in out and "10.0.0.5" in out, "redaction must keep the parts that aid diagnosis"

    # SQLite has no credentials and must pass through recognisably.
    sqlite = "sqlite:////var/lib/ciris/data/ciris_engine.db"
    assert "ciris_engine.db" in _redact_dsn(sqlite)
