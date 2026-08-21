"""Live-API LLM provider conformance matrix.

Why this exists
---------------
A user could not configure an LLM through the setup wizard. Three separate
defects stacked up:

1. With no model chosen, ``_validate_openai_compatible`` substitutes
   ``"gpt-3.5-turbo"`` and sends that OpenAI model name to whichever provider
   the user picked.
2. OpenRouter answered ``404 "No endpoints available matching your guardrail
   restrictions and data policy"`` — a privacy-settings problem. The product's
   classifier substring-matches, misses every pattern, and renders "Could not
   reach the API endpoint. Please check your configuration.", sending the user
   to inspect their network.
3. The live model listing failed seven times, logged no exception detail, and
   showed a cached catalogue as though it were current.

The space is small and finite — six providers, twenty-two catalogued models —
so it can be locked down by exhaustive testing rather than by hoping. This
module sweeps it and reports the gap between what a provider actually said and
what CIRIS tells the user it said.

Layout
------
``dimensions.py``     the matrix axes, as data
``schemas.py``        typed cells, outcomes, findings, report
``product_bridge.py`` the only import seam into ciris_engine
``probes.py``         the only code that touches the network
``analysis.py``       finding detection, including static table audits
``matrix.py``         expansion and execution
``report.py``         console + JSON rendering
``fixtures.py``       recorded provider behaviour for --dry-run
``__main__.py``       CLI

Entry point: ``python3 -m tools.qa_runner.modules.llm_matrix --dry-run``
"""

from .dimensions import PROVIDERS, ProviderSpec
from .matrix import BudgetExceeded, LLMMatrix, MatrixOptions, expand_cells
from .report import default_report_dir, render_console, write_report
from .schemas import (
    CellResult,
    ClassifierVerdict,
    CredentialMode,
    ExpectedCause,
    FindingKind,
    LLMProbeOutcome,
    MatrixCell,
    ModelSelector,
    ProbeKind,
    QuirkFinding,
    QuirksReport,
    RenderedCause,
    Severity,
)

__all__ = [
    "BudgetExceeded",
    "CellResult",
    "ClassifierVerdict",
    "CredentialMode",
    "ExpectedCause",
    "FindingKind",
    "LLMMatrix",
    "LLMProbeOutcome",
    "MatrixCell",
    "MatrixOptions",
    "ModelSelector",
    "PROVIDERS",
    "ProbeKind",
    "ProviderSpec",
    "QuirkFinding",
    "QuirksReport",
    "RenderedCause",
    "Severity",
    "default_report_dir",
    "expand_cells",
    "render_console",
    "write_report",
]
