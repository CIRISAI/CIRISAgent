"""Regressions for defects found by review, not by tests (PR #1092).

Each of these shipped in the F1/F4/ladder work and was caught by a reviewer
reading the code. They share a shape: the code was self-consistent and the
tests agreed with it, but it disagreed with a contract defined somewhere else
in the tree — a scope grammar, a persistence default, a sibling field.
"""

import ast
import inspect
from pathlib import Path

import pytest

from ciris_engine.schemas.services.authority_core import scope_grants

REPO = Path(__file__).resolve().parents[6]


class TestDeferralScopeGrammarIsSingular:
    """The route must request the action name certificates actually grant.

    `resolve_deferral` is what every certificate fixture mints and every other
    caller checks. The route asked for the plural `resolve_deferrals`, which
    matches no scope any authority holds — so instead of denying the wrong
    authorities it would have denied ALL of them, including correctly scoped
    ones. The identical plural slip was already found once inside the service.
    """

    def test_a_correctly_scoped_medical_authority_is_granted(self) -> None:
        resource = f"medical_{'defer_001'}"
        assert scope_grants("resolve_deferral:medical_*", "resolve_deferral", resource) is True

    def test_the_plural_matches_nothing_anyone_grants(self) -> None:
        resource = f"medical_{'defer_001'}"
        assert scope_grants("resolve_deferral:medical_*", "resolve_deferrals", resource) is False, (
            "If this ever passes, the grammar changed and routes/wa.py must change with it."
        )

    def test_a_bare_domain_resource_does_not_match_a_domain_glob(self) -> None:
        """Why the route prefixes the domain onto the deferral id.

        Passing the bare domain "medical" fails `medical_*` (fnmatch needs the
        underscore), so a correctly scoped authority would have been refused.
        """
        assert scope_grants("resolve_deferral:medical_*", "resolve_deferral", "medical") is False

    def test_cross_domain_is_still_denied(self) -> None:
        assert scope_grants("resolve_deferral:medical_*", "resolve_deferral", "financial_defer_001") is False

    def test_unrestricted_spellings_still_work(self) -> None:
        for scope in ("resolve_deferral:any", "resolve_deferral:*", "*"):
            assert scope_grants(scope, "resolve_deferral", "medical_defer_001") is True, scope

    def test_the_route_uses_the_singular_action(self) -> None:
        src = (REPO / "ciris_engine/logic/adapters/api/routes/wa.py").read_text()
        assert '"resolve_deferrals"' not in src, "routes/wa.py must request the singular action name"


class TestJurisdictionLookupFailsClosed:
    """"We could not check" is not "there was nothing to check".

    The gate only runs when a domain was found. If the lookup itself raises, an
    authority with no jurisdiction over the actual domain could resolve the
    deferral — a transient persistence blip becomes a way around F1 entirely.
    """

    def _gate_source(self) -> str:
        from ciris_engine.logic.adapters.api.routes import wa

        return inspect.getsource(wa.resolve_deferral)

    def _lookup_try_block(self) -> ast.Try:
        """The specific `try` that wraps get_pending_deferrals().

        Must be pinned to THAT block: resolve_deferral has other try/excepts
        which do raise, so 'some handler in this function raises' passes even
        when the jurisdiction lookup silently falls through — which is the bug.
        """
        tree = ast.parse(inspect.cleandoc(self._gate_source()))
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                names = {
                    n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)
                } | {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
                if "get_pending_deferrals" in names:
                    return node
        pytest.fail("could not locate the try block wrapping get_pending_deferrals()")

    def test_the_lookup_handler_raises_rather_than_falling_through(self) -> None:
        block = self._lookup_try_block()
        assert block.handlers, "the lookup must be guarded"
        for h in block.handlers:
            assert any(isinstance(n, ast.Raise) for n in ast.walk(h)), (
                "The jurisdiction lookup's except block must raise. Logging and continuing "
                "hands the caller the role-only path, which is exactly the gate being "
                "bypassed: a transient persistence failure becomes a way to resolve a "
                "domain-scoped deferral without jurisdiction."
            )

    def test_it_is_reported_as_a_lookup_failure_not_a_denial(self) -> None:
        src = ast.unparse(self._lookup_try_block())
        assert "503" in src or "SERVICE_UNAVAILABLE" in src, (
            "A failed lookup is not a permissions decision. Returning 403 sends an operator "
            "hunting a certificate problem that does not exist; 503 says 'retry'."
        )


class TestCompletionGuardIsOccurrenceScoped:
    """F4's guard must query siblings in the task's OWN occurrence.

    get_thoughts_by_task_id filters agent_occurrence_id by equality, defaulting
    to "default". Querying without the task's occurrence returns zero siblings
    for any horizontally-scaled deployment, so the guard silently held only on
    single-occurrence installs.
    """

    def test_the_persistence_default_is_still_narrow(self) -> None:
        from ciris_engine.logic.persistence.models.thoughts import get_thoughts_by_task_id

        default = inspect.signature(get_thoughts_by_task_id).parameters["occurrence_id"].default
        assert default == "default", (
            "This test encodes WHY the handler must pass an occurrence explicitly. If the "
            "persistence default became occurrence-agnostic, revisit the handler."
        )

    def test_the_guard_accepts_an_occurrence(self) -> None:
        from ciris_engine.logic.handlers.terminal.task_complete_handler import TaskCompleteHandler

        assert "occurrence_id" in inspect.signature(TaskCompleteHandler._verify_no_pending_thoughts).parameters

    def test_the_guard_is_called_with_the_tasks_occurrence(self) -> None:
        from ciris_engine.logic.handlers.terminal.task_complete_handler import TaskCompleteHandler

        src = inspect.getsource(TaskCompleteHandler._complete_parent_task)
        assert "_verify_no_pending_thoughts(task_id, thought_id, task_occurrence_id)" in src, (
            "The guard must receive the occurrence resolved from the task record, and the "
            "task lookup must therefore happen BEFORE the guard runs."
        )

    def test_the_query_forwards_the_occurrence(self) -> None:
        from ciris_engine.logic.handlers.terminal.task_complete_handler import TaskCompleteHandler

        src = inspect.getsource(TaskCompleteHandler._verify_no_pending_thoughts)
        assert "occurrence_id=occurrence_id" in src


class TestFaultCodeNeverGoesStale:
    """last_error and last_fault_code are read as a pair by the health ladder.

    Health prefers the structured slug over substring-matching the text. If a
    failure path refreshes only the text, a provider whose FIRST failure was
    `model_not_found` and whose CURRENT failure is a timeout keeps telling the
    user to change the model — a remedy for an outage that is already over.
    """

    def test_every_last_error_assignment_has_a_fault_code_beside_it(self) -> None:
        src = (REPO / "ciris_engine/logic/services/runtime/llm_service/service.py").read_text()
        tree = ast.parse(src)

        def _targets(node: ast.AST) -> set[str]:
            out = set()
            for t in getattr(node, "targets", []):
                if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self":
                    out.add(t.attr)
            return out

        assigns = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)]
        err_lines = sorted(n.lineno for n in assigns if "last_error" in _targets(n))
        code_lines = sorted(n.lineno for n in assigns if "last_fault_code" in _targets(n))

        assert err_lines, "expected last_error assignments"
        for line in err_lines:
            assert any(abs(line - c) <= 12 for c in code_lines), (
                f"self.last_error assigned at line {line} with no self.last_fault_code refresh nearby. "
                f"The health ladder reads them together; refreshing one leaves a stale remedy on screen. "
                f"fault-code assignments are at {code_lines}."
            )
