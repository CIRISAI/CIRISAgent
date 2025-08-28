#!/bin/bash
# Local CI check script to run before pushing

set -e

echo "🔧 Installing dependencies..."
pip install pytest-cov coverage[toml] flake8 black isort mypy bandit

echo "🧹 Running code formatting checks..."
black --check ciris_engine tests/
isort --check-only ciris_engine tests/

echo "🔍 Running linting..."
flake8 ciris_engine --max-line-length=120 --ignore=E203,W503

echo "🛡️ Running security checks..."
bandit -r ciris_engine -f json -o bandit-report.json || true

echo "🧪 Running tests with coverage..."
python -m pytest --cov=ciris_engine \
  --cov-report=xml --cov-report=term-missing \
  --cov-fail-under=80

echo "📊 Coverage report generated: coverage.xml"
echo "📊 HTML coverage report: htmlcov/index.html"

echo "✅ All CI checks passed!"
echo "🚀 Ready to push to GitHub!"
