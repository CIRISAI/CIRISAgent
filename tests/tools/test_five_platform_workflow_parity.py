"""The modular gate's bring-up must stay byte-identical to the UI gate's.

The modular workflow exists to swap ONLY what drives the platform. If its
emulator/simulator/desktop bring-up drifts from the gate's, a red on one and a
green on the other stops meaning anything about the product.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / ".github/workflows/five-platform-live-qa.yml"
MODULAR = ROOT / ".github/workflows/five-platform-modular-qa.yml"


def _bring_up(path: Path, driving_step: str) -> str:
    text = path.read_text()
    start = text.index("\njobs:\n") + 1
    end = text.index(driving_step)
    # Per-line rstrip: the repo's trailing-whitespace hook normalizes whichever
    # file is touched next, and a byte of trailing space is not bring-up drift.
    return "\n".join(line.rstrip() for line in text[start:end].splitlines())


def test_bring_up_is_identical():
    gate = _bring_up(GATE, "      - name: Run the shared flow on each platform this runner owns")
    modular = _bring_up(MODULAR, "      - name: Run the modular QA runner against each platform's backend")
    assert gate == modular, "bring-up drifted between the two five-platform workflows; regenerate or fix both"


def test_modular_driving_step_has_no_inline_expressions():
    """A run: body containing any ${{ }} is one expression capped at 21000 chars."""
    text = MODULAR.read_text()
    start = text.index("      - name: Run the modular QA runner against each platform's backend")
    end = text.index("      - name: Collect artifacts", start)
    step = text[start:end]
    run_body = step[step.index("        run: |") :]
    assert "${{" not in run_body
