"""End-to-end check: every prompt the agent reads in the Bengali (bn) locale
contains Bengali content in its natural-language sections.

This is a thin wrapper around the shared per-locale chain test factory.
Run with: pytest tests/ciris_engine/logic/utils/test_bn_chain_localization.py -v
"""

from tests.ciris_engine.logic.utils._locale_chain_helpers import register_locale_tests

register_locale_tests(globals(), locale="bn")
