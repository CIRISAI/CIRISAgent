"""The error reporter must not die while reporting an error.

`result.get("error", "Unknown error")[:100]` returns the default only when the
key is MISSING. When it is present and None — which several modules emit —
you get None, and None[:100] raises:

    TypeError: 'NoneType' object is not subscriptable

That fired inside _print_summary, so the runner crashed at the exact moment it
was describing a failure and the underlying error was never printed. The capture
had succeeded; what was lost was the diagnosis.

It was known: safety_battery.py emits an explicit "" on success purely to dodge
this line, with a comment naming it. One caller was patched; the reporter was
not. These tests pin the reporter instead.
"""

from tools.qa_runner.runner import _err_text


def test_present_but_none_does_not_raise():
    assert _err_text({"error": None}) == "Unknown error"


def test_present_but_none_recovers_status():
    """The status usually carries the real message — surface it, don't discard it."""
    assert _err_text({"error": None, "status": "FAIL: provider 402"}) == "FAIL: provider 402"


def test_missing_key_uses_default():
    assert _err_text({}) == "Unknown error"


def test_normal_error_passes_through():
    assert _err_text({"error": "real failure text"}) == "real failure text"


def test_non_string_error_is_coerced():
    assert _err_text({"error": 42}) == "42"


def test_truncates():
    assert len(_err_text({"error": "x" * 500})) == 100
