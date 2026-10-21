"""End-to-end check: every prompt the agent reads in the Yoruba (yo) locale
contains Yoruba (Latin) content in its natural-language sections.

This is a thin wrapper around the shared per-locale chain test factory.
Run with: pytest tests/ciris_engine/logic/utils/test_yo_chain_localization.py -v
"""

from tests.ciris_engine.logic.utils._locale_chain_helpers import register_locale_tests

register_locale_tests(globals(), locale="yo")
