"""
QA Runner - Modular Quality Assurance Testing Framework.

A comprehensive QA testing framework for running integration tests
against the CIRIS API and various adapters.
"""

from .config import QAConfig, QAModule
from .runner import QARunner

__all__ = ["QARunner", "QAConfig", "QAModule"]
