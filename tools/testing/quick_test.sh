#!/bin/bash
# Quick test to verify everything is working

echo "🧪 Running CIRIS quick tests..."

# Check Docker
echo -n "Docker: "
if docker --version >/dev/null 2>&1; then
    echo "✓ $(docker --version)"
else
    echo "✗ Not installed"
fi

# Check Docker Compose
echo -n "Docker Compose: "
if docker compose version >/dev/null 2>&1; then
    echo "✓ $(docker compose version)"
else
    echo "✗ Not installed"
fi

# Check Python packages
echo -n "Pytest: "
if python -m pytest --version >/dev/null 2>&1; then
    echo "✓ $(python -m pytest --version)"
else
    echo "✗ Not installed"
fi

# Check if we can import CIRIS
echo -n "CIRIS imports: "
if python -c "import ciris_engine" 2>/dev/null; then
    echo "✓ Working"
else
    echo "✗ Import error"
fi

echo ""
echo "Note: You need to log out and back in for Docker group changes to take effect!"
