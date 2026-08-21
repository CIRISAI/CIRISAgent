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


class TestEveryMintedAuthorityCanActuallyResolve:
    """A gate nobody can pass is an outage, not a control.

    Before this, no supported minting path issued a scope the F1 gate accepts:
    setup authorities got read:any/write:any, OAuth authorities got the
    `wa.resolve_deferral` PERMISSION (a different grammar — no colon, so it
    names an action and no domain and grants nothing). Every non-ROOT
    authority in production would have been refused every domain-tagged
    deferral, i.e. F1 would have "closed" by breaking the human-resolution
    path it exists to protect.
    """

    RESOURCE = "medical_defer_001"

    def test_setup_minted_authority_scopes_pass_the_gate(self) -> None:
        src = (REPO / "ciris_engine/logic/runtime/service_initializer.py").read_text()
        assert '"resolve_deferral:any"' in src, "setup-created AUTHORITY must be minted with jurisdiction"
        assert any(
            scope_grants(s, "resolve_deferral", self.RESOURCE)
            for s in ["read:any", "write:any", "resolve_deferral:any"]
        )

    def test_the_old_setup_scopes_alone_would_have_been_refused(self) -> None:
        assert not any(
            scope_grants(s, "resolve_deferral", self.RESOURCE) for s in ["read:any", "write:any"]
        ), "this is why the mint had to change; if it ever passes, the grammar moved"

    def test_the_wa_permission_is_not_a_scope(self) -> None:
        assert scope_grants("wa.resolve_deferral", "resolve_deferral", self.RESOURCE) is False, (
            "wa.resolve_deferral is an API permission, not a certificate scope. A bare scope "
            "with no colon must not be read as 'therefore every domain'."
        )

    def test_oauth_minting_adds_the_scope_for_authority_only(self) -> None:
        src = (REPO / "ciris_engine/logic/adapters/api/services/auth_service.py").read_text()
        assert '"resolve_deferral:any"' in src
        assert "WARole.AUTHORITY, WARole.ROOT" in src, "OBSERVER must not be granted deferral jurisdiction"


class TestTheBackfillRestoresBreadthWithoutWideningAnyone:
    def _holds(self, scopes: list) -> bool:
        from ciris_engine.logic.services.infrastructure.authentication.service import (
            AuthenticationService,
        )

        return AuthenticationService._holds_deferral_jurisdiction(scopes)

    def test_pre_grammar_certificates_are_backfilled(self) -> None:
        assert self._holds(["read:any", "write:any"]) is False
        assert self._holds(["wa.resolve_deferral", "wa.mint"]) is False

    def test_a_deliberately_narrow_certificate_is_left_alone(self) -> None:
        """The important half.

        A grant-based check would ask scope_grants(s, "resolve_deferral", probe)
        and get False for resolve_deferral:medical_* against any probe outside
        medical — then widen to :any the exact certificates an operator
        deliberately narrowed. The check is structural for that reason.
        """
        assert self._holds(["resolve_deferral:medical_*"]) is True
        assert self._holds(["resolve_deferral:org/acme/*"]) is True
        assert self._holds(["resolve_deferral:any"]) is True
        assert self._holds(["*"]) is True

    def test_malformed_scopes_do_not_count_as_jurisdiction(self) -> None:
        assert self._holds(["resolve_deferral:"]) is False
        assert self._holds(["   "]) is False
        assert self._holds([]) is False

    def test_only_authority_is_backfilled(self) -> None:
        import inspect

        from ciris_engine.logic.services.infrastructure.authentication.service import (
            AuthenticationService,
        )

        src = inspect.getsource(AuthenticationService._backfill_deferral_scopes)
        assert "WARole.AUTHORITY" in src, "ROOT bypasses the gate; OBSERVER must not resolve deferrals"


class TestOAuthAuthoritiesAreLookedUpByCertificate:
    """AuthContext.user_id is not the certificate id for ingress auth."""

    @pytest.mark.asyncio
    async def test_an_oauth_identity_maps_to_its_certificate(self) -> None:
        from types import SimpleNamespace

        from ciris_engine.logic.adapters.api.routes.wa import resolve_certificate_id

        async def _by_oauth(provider: str, external_id: str):
            assert (provider, external_id) == ("google", "12345")
            return SimpleNamespace(wa_id="wa-2026-08-21-ABC123")

        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(authentication_service=SimpleNamespace(get_wa_by_oauth=_by_oauth)))
        )
        resolved = await resolve_certificate_id(request, SimpleNamespace(user_id="google:12345"))
        assert resolved == "wa-2026-08-21-ABC123"

    @pytest.mark.asyncio
    async def test_a_password_user_already_carries_the_certificate_id(self) -> None:
        from types import SimpleNamespace

        from ciris_engine.logic.adapters.api.routes.wa import resolve_certificate_id

        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
        resolved = await resolve_certificate_id(request, SimpleNamespace(user_id="wa-2026-08-21-ABC123"))
        assert resolved == "wa-2026-08-21-ABC123"

    @pytest.mark.asyncio
    async def test_an_unmappable_identity_is_returned_unchanged(self) -> None:
        """So the gate reports WA_NOT_FOUND naming it, rather than inventing a certificate."""
        from types import SimpleNamespace

        from ciris_engine.logic.adapters.api.routes.wa import resolve_certificate_id

        async def _none(provider: str, external_id: str):
            return None

        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(authentication_service=SimpleNamespace(get_wa_by_oauth=_none)))
        )
        resolved = await resolve_certificate_id(request, SimpleNamespace(user_id="google:unknown"))
        assert resolved == "google:unknown"
