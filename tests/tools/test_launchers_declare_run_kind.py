"""Every tools/ launcher that starts an agent declares its run kind (CIRISAgent#1245).

Ruling (2026-10-14): QA runs are valuable but must be identified as such, and
anything outside a harness is production. A tool that spawns ``main.py`` or
``ciris_engine.cli`` with a real model and no declaration ships harness traces
as ``production``.

The lint is per function: a function that both spawns a process
(``subprocess.Popen/run/call/check_*``, ``asyncio.create_subprocess_*``) and
names an agent entry point must also, in the same function, either

* name ``CIRIS_TRACE_RUN_KIND`` or call one of the ``tools.qa_runner.run_kind``
  declarers, or
* pass ``--mock-llm`` in an argument list (the agent marks those ``mock``).

Functions that only *match* agent processes (``pkill`` patterns, cmdline
predicates) do not spawn one, so they are not launchers.
"""

from __future__ import annotations

import ast
import pathlib
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Set, Union

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
RUN_KIND = "CIRIS_TRACE_RUN_KIND"

AGENT_ENTRY_POINTS = ("main.py", "ciris_engine.cli", "ciris-agent")
SPAWN_ATTRS = {
    "Popen",
    "run",
    "call",
    "check_call",
    "check_output",
    "create_subprocess_exec",
    "create_subprocess_shell",
}
SPAWN_MODULES = {"subprocess", "_sp", "sp", "asyncio"}
DECLARERS = {"declare_run_kind", "declare_process_run_kind", "ios_simctl_env", "android_setprop_args"}

_Func = Union[ast.FunctionDef, ast.AsyncFunctionDef]


@dataclass
class Finding:
    path: str
    function: str
    line: int

    def __str__(self) -> str:
        return f"{self.path}:{self.line} {self.function}()"


def _is_entry_point(value: str) -> bool:
    return value in AGENT_ENTRY_POINTS or value.endswith("/main.py")


def _is_spawn(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr in SPAWN_ATTRS:
        return isinstance(func.value, ast.Name) and func.value.id in SPAWN_MODULES
    return isinstance(func, ast.Name) and func.id == "Popen"


def _passes_mock_llm(node: ast.AST, parents: Dict[ast.AST, ast.AST]) -> bool:
    """``--mock-llm`` used as an argument: inside a list, or appended/extended onto one."""
    parent = parents.get(node)
    if isinstance(parent, (ast.List, ast.Tuple)):
        return True
    return (
        isinstance(parent, ast.Call)
        and isinstance(parent.func, ast.Attribute)
        and parent.func.attr in ("append", "extend", "insert")
    )


def _called_names(func: _Func) -> Set[str]:
    names: Set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
            elif isinstance(node.func, ast.Name):
                names.add(node.func.id)
    return names


def _declares(func: _Func, parents: Dict[ast.AST, ast.AST], declaring: FrozenSet[str] = frozenset()) -> bool:
    if _called_names(func) & declaring:
        return True  # builds the child env through a same-module helper that declares
    for node in ast.walk(func):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if RUN_KIND in node.value:
                return True
            if node.value == "--mock-llm" and _passes_mock_llm(node, parents):
                return True
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
            if name in DECLARERS:
                return True
    return False


def undeclared_launchers(source: str, path: str = "<fixture>") -> List[Finding]:
    tree = ast.parse(source)
    parents: Dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    funcs = [f for f in ast.walk(tree) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))]
    declaring = frozenset(f.name for f in funcs if _declares(f, parents))
    findings: List[Finding] = []
    for func in funcs:
        entry: Optional[int] = None
        spawns = False
        for node in ast.walk(func):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and _is_entry_point(node.value):
                entry = entry or node.lineno
            elif isinstance(node, ast.Call) and _is_spawn(node):
                spawns = True
        if entry is not None and spawns and not _declares(func, parents, declaring):
            findings.append(Finding(path, func.name, entry))
    return findings


def _tool_sources() -> List[pathlib.Path]:
    return sorted(p for p in (REPO / "tools").rglob("*.py") if "__pycache__" not in p.parts)


def test_there_are_tools_to_lint() -> None:
    assert len(_tool_sources()) > 100


def test_every_tools_launcher_declares_a_run_kind() -> None:
    findings: List[Finding] = []
    for path in _tool_sources():
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        findings += undeclared_launchers(source, str(path.relative_to(REPO)))
    assert not findings, (
        f"these tools spawn an agent with no run kind; real-model traces would ship as production. "
        f"Set {RUN_KIND} in the child env (or call tools.qa_runner.run_kind.declare_run_kind), "
        f"or pass --mock-llm:\n  " + "\n  ".join(str(f) for f in findings)
    )


@pytest.mark.parametrize(
    "path,function",
    [
        ("tools/benchmark/he300_runner.py", "_get_ciris_env"),
        ("tools/record_demo_clips.py", "launch_desktop_app"),
    ],
)
def test_the_named_gaps_now_declare(path: str, function: str) -> None:
    """he300 (G8) and the demo recorder (G10) were real-model launches marked production."""
    tree = ast.parse((REPO / path).read_text(encoding="utf-8"))
    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function]
    assert funcs, f"{path}:{function} moved; update this test"
    assert any(RUN_KIND in ast.unparse(f) for f in funcs)


# --------------------------------------------------------------------------- #
# Negative fixtures: the lint must FAIL on an injected defect.
# --------------------------------------------------------------------------- #

_BARE_POPEN = """
import subprocess, sys
def start():
    return subprocess.Popen([sys.executable, "main.py", "--adapter", "api"])
"""

_BARE_CLI = """
import os, subprocess, sys
def launch():
    env = os.environ.copy()
    env["CIRIS_TEST_MODE"] = "true"
    return subprocess.Popen([sys.executable, "-m", "ciris_engine.cli"], env=env)
"""

_PATH_JOIN = """
import subprocess, sys
from pathlib import Path
def start(self):
    main_path = Path(__file__).parent / "main.py"
    cmd = [sys.executable, str(main_path)]
    return subprocess.Popen(cmd)
"""

_ASYNC = """
import asyncio
async def boot():
    return await asyncio.create_subprocess_exec("python", "main.py", "--adapter", "api")
"""

_MOCK_IN_HELP_ONLY = """
import subprocess
def start():
    print("pass --mock-llm to avoid real tokens")
    return subprocess.Popen(["python", "main.py"])
"""


_HELPER_THAT_DOES_NOT_DECLARE = """
import os, subprocess, sys
class Runner:
    def _env(self):
        env = os.environ.copy()
        env["CIRIS_BENCHMARK_MODE"] = "true"
        return env
    def start(self):
        return subprocess.Popen([sys.executable, "main.py"], env=self._env())
"""


@pytest.mark.parametrize(
    "source", [_BARE_POPEN, _BARE_CLI, _PATH_JOIN, _ASYNC, _MOCK_IN_HELP_ONLY, _HELPER_THAT_DOES_NOT_DECLARE]
)
def test_negative_an_undeclared_launch_fails_the_lint(source: str) -> None:
    assert undeclared_launchers(source), "the lint missed an undeclared agent launch"


_DECLARED_ENV = """
import os, subprocess, sys
def start():
    env = os.environ.copy()
    env["CIRIS_TRACE_RUN_KIND"] = "qa"
    return subprocess.Popen([sys.executable, "main.py"], env=env)
"""

_DECLARED_HELPER = """
import os, subprocess, sys
from tools.qa_runner.run_kind import declare_run_kind
def start():
    env = os.environ.copy()
    declare_run_kind(env)
    return subprocess.Popen([sys.executable, "main.py"], env=env)
"""

_MOCK_LIST = """
import subprocess, sys
def start():
    return subprocess.Popen([sys.executable, "main.py", "--adapter", "api", "--mock-llm"])
"""

_MOCK_APPEND = """
import subprocess, sys
def start(mock):
    cmd = [sys.executable, "main.py"]
    cmd.append("--mock-llm")
    return subprocess.Popen(cmd)
"""

_DECLARED_VIA_HELPER_METHOD = """
import os, subprocess, sys
class Runner:
    def _env(self):
        env = os.environ.copy()
        env["CIRIS_TRACE_RUN_KIND"] = "battery"
        return env
    def start(self):
        return subprocess.Popen([sys.executable, "main.py"], env=self._env())
"""

_MATCH_ONLY = """
def is_backend(cmdline):
    return "main.py" in cmdline
"""

_SYNTAX_CHECK_VIA_HELPER = """
async def check():
    return await run_command_async(["python", "-m", "py_compile", "main.py"])
"""


@pytest.mark.parametrize(
    "source",
    [
        _DECLARED_ENV,
        _DECLARED_HELPER,
        _DECLARED_VIA_HELPER_METHOD,
        _MOCK_LIST,
        _MOCK_APPEND,
        _MATCH_ONLY,
        _SYNTAX_CHECK_VIA_HELPER,
    ],
)
def test_declared_or_non_launching_functions_pass(source: str) -> None:
    assert undeclared_launchers(source) == []


# --------------------------------------------------------------------------- #
# H5: the AgentBeats image is a benchmark harness (G9).
# --------------------------------------------------------------------------- #


def dockerfile_declares_run_kind(text: str) -> Optional[str]:
    """The run kind an image's ``ENV`` declares, or None."""
    import re

    m = re.search(rf"^\s*ENV\s+{RUN_KIND}[= ](\S+)\s*$", text, re.MULTILINE)
    return m.group(1).strip("\"'") if m else None


def test_agentbeats_image_declares_battery() -> None:
    text = (REPO / "docker" / "Dockerfile.agentbeats").read_text(encoding="utf-8")
    assert dockerfile_declares_run_kind(text) == "battery"
    example = (REPO / "docker" / ".env.agentbeats.example").read_text(encoding="utf-8")
    assert f"{RUN_KIND}=battery" in example.splitlines()
    compose = (REPO / "docker" / "docker-compose-agentbeats.yml").read_text(encoding="utf-8")
    assert f"- {RUN_KIND}=battery" in compose


@pytest.mark.parametrize(
    "text",
    [
        'ENV CIRIS_ACCORD_METRICS_TRACE_LEVEL=full_traces\nCMD ["python", "main.py"]\n',
        "# ENV CIRIS_TRACE_RUN_KIND=battery\n",
    ],
)
def test_negative_an_image_without_the_env_fails(text: str) -> None:
    assert dockerfile_declares_run_kind(text) is None
