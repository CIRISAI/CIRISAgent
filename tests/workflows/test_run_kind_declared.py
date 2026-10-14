"""Every CI step that starts an agent declares its run kind (CIRISAgent#1245).

Ruling (2026-10-14): QA runs are valuable but must be identified as such, and
anything outside a harness is production. A workflow step that boots an agent
with a real model and no declaration ships its traces as ``production``. The
agent-side harness-flag backstop catches most of those, but not a bare
``python main.py`` with a live key; this lint catches it at PR time.

A step that starts an agent passes when ANY of these holds:

* ``CIRIS_TRACE_RUN_KIND`` is in the workflow, job or step ``env``, or is
  assigned inline in the step body before the launch;
* the launch line carries ``--mock-llm`` (the agent marks those ``mock`` itself);
* the launch goes through a self-declaring launcher (``SELF_DECLARING``). Each
  of those is pinned to actually declare by
  ``tests/tools/test_launchers_declare_run_kind.py`` and the qa_runner tests.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple

import pytest

yaml = pytest.importorskip("yaml")

REPO = pathlib.Path(__file__).resolve().parents[2]
RUN_KIND = "CIRIS_TRACE_RUN_KIND"

#: Command lines that boot an agent process.
AGENT_LAUNCH = [
    re.compile(r"\bpython[0-9.]*(?:\.exe)?\s+(?:-\S+\s+)*(?:\S*[/\\])?main\.py\b"),
    re.compile(r"\bpython[0-9.]*(?:\.exe)?\s+(?:-\S+\s+)*-m\s+ciris_engine(?:\.cli)?(?:\s|$)"),
    re.compile(r"(?:^|[;&(]\s*|\b(?:then|do|exec|nohup|time)\s+)(?:\S*[/\\])?ciris-(?:agent|server)(?:\.exe)?(?:\s|$)"),
    re.compile(r"\bdocker\s+run\b.*\bciris-agent\b"),
]

#: Launchers that declare the run kind themselves (and are tested to).
SELF_DECLARING = [
    re.compile(r"-m\s+tools\.qa_runner\b"),
    re.compile(r"\bcapture_traces\.sh\b"),
    re.compile(r"\bhe300_runner\b"),
    re.compile(r"\brecord_demo_clips\b"),
]

#: Lines that only print text naming a launcher.
_PRINT_ONLY = re.compile(r"^\s*(?:echo|printf|Write-Host|Write-Output)\b")

_INLINE_DECLARATION = re.compile(rf"(?:^|\s|\$env:){RUN_KIND}\s*=|-e\s+{RUN_KIND}=|--env\s+{RUN_KIND}=")


def _logical_lines(body: str) -> Iterator[str]:
    """Join bash ``\\`` and PowerShell backtick continuations; drop comment lines."""
    pending = ""
    for raw in body.splitlines():
        line = raw.rstrip()
        if not pending and line.lstrip().startswith("#"):
            continue
        if line.endswith("\\") or line.endswith("`"):
            pending += line[:-1] + " "
            continue
        yield pending + line
        pending = ""
    if pending:
        yield pending


def _env_declares(env: Any) -> bool:
    return isinstance(env, Mapping) and RUN_KIND in env


def undeclared_launches_in_body(body: str, env_declared: bool) -> List[str]:
    """The agent-launch lines in one ``run:`` body that carry no run kind."""
    found: List[str] = []
    inline = False
    for line in _logical_lines(body):
        if _INLINE_DECLARATION.search(line):
            inline = True
        if _PRINT_ONLY.search(line) or not any(p.search(line) for p in AGENT_LAUNCH):
            continue
        if env_declared or inline or "--mock-llm" in line:
            continue
        if any(p.search(line) for p in SELF_DECLARING):
            continue
        found.append(line.strip())
    return found


def _steps(spec: Mapping[str, Any]) -> Iterator[Tuple[str, Mapping[str, Any], bool]]:
    """(location, step, env_declared_above) for every step of a workflow or composite action."""
    wf_env = _env_declares(spec.get("env"))
    jobs = spec.get("jobs") or {}
    for job_name, job in jobs.items():
        if not isinstance(job, Mapping):
            continue
        job_env = wf_env or _env_declares(job.get("env"))
        for i, step in enumerate(job.get("steps") or []):
            if isinstance(step, Mapping):
                yield f"jobs.{job_name}.steps[{i}]", step, job_env
    runs = spec.get("runs")
    if isinstance(runs, Mapping):
        for i, step in enumerate(runs.get("steps") or []):
            if isinstance(step, Mapping):
                yield f"runs.steps[{i}]", step, wf_env


def undeclared_launches(spec: Mapping[str, Any]) -> List[str]:
    out: List[str] = []
    for where, step, above in _steps(spec):
        body = step.get("run")
        if not isinstance(body, str):
            continue
        declared = above or _env_declares(step.get("env"))
        for line in undeclared_launches_in_body(body, declared):
            out.append(f"{where} ({step.get('name', '<unnamed>')}): {line}")
    return out


def _workflow_files() -> List[pathlib.Path]:
    files = sorted((REPO / ".github" / "workflows").glob("*.yml"))
    files += sorted((REPO / ".github" / "workflows").glob("*.yaml"))
    files += sorted((REPO / ".github" / "actions").glob("*/action.yml"))
    return files


def test_there_are_workflows_to_lint() -> None:
    assert len(_workflow_files()) > 10


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: str(p.relative_to(REPO)))
def test_every_agent_launch_declares_a_run_kind(path: pathlib.Path) -> None:
    spec = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    problems = undeclared_launches(spec)
    assert not problems, (
        f"{path.relative_to(REPO)} starts an agent with no run kind; its real-model traces would ship as "
        f"production. Set {RUN_KIND} (qa|battery) in env, pass --mock-llm, or launch via tools.qa_runner:\n  "
        + "\n  ".join(problems)
    )


# --------------------------------------------------------------------------- #
# Negative fixtures: the lint must FAIL on an injected defect.
# --------------------------------------------------------------------------- #


def _wf(run: str, step_env: Optional[Dict[str, str]] = None, job_env: Optional[Dict[str, str]] = None) -> Dict:
    step: Dict[str, Any] = {"name": "boot", "run": run}
    if step_env is not None:
        step["env"] = step_env
    job: Dict[str, Any] = {"runs-on": "ubuntu-latest", "steps": [step]}
    if job_env is not None:
        job["env"] = job_env
    return {"name": "fixture", "on": "push", "jobs": {"j": job}}


@pytest.mark.parametrize(
    "run",
    [
        "python main.py --adapter api --port 8080 &",
        "python3 -u main.py --adapter api",
        "python -m ciris_engine.cli --server",
        "ciris-agent --server",
        "nohup ciris-server --port 8080 &",
        "python main.py \\\n  --adapter api \\\n  --port 8080",
        "docker run -d -p 8080:8080 ghcr.io/cirisai/ciris-agent:latest",
    ],
)
def test_negative_a_bare_launch_fails_the_lint(run: str) -> None:
    assert undeclared_launches(_wf(run)), f"the lint missed an undeclared launch: {run!r}"


def test_negative_a_declaration_on_another_job_does_not_count() -> None:
    spec = _wf("python main.py --adapter api")
    spec["jobs"]["other"] = {"runs-on": "x", "env": {RUN_KIND: "qa"}, "steps": [{"run": "true"}]}
    assert undeclared_launches(spec)


@pytest.mark.parametrize(
    "spec",
    [
        _wf("python main.py --adapter api", step_env={RUN_KIND: "qa"}),
        _wf("python main.py --adapter api", job_env={RUN_KIND: "battery"}),
        {**_wf("python main.py --adapter api"), "env": {RUN_KIND: "qa"}},
        _wf("export CIRIS_TRACE_RUN_KIND=qa\npython main.py --adapter api"),
        _wf("python main.py --adapter api --mock-llm --port 8080 &"),
        _wf("python -m tools.qa_runner auth --live"),
        _wf("./tools/research/capture_traces.sh"),
        _wf("# python main.py --adapter api"),
        _wf("python -m ciris_engine.logic.utils.compose_dump dump"),
        _wf('echo "- ciris-agent" >> $GITHUB_STEP_SUMMARY'),
        _wf('echo "| ciris-server | `$SERVER` |"'),
        _wf("pyinstaller ciris-agent.spec --noconfirm"),
    ],
)
def test_declared_or_non_launch_steps_pass(spec: Dict[str, Any]) -> None:
    assert undeclared_launches(spec) == []
