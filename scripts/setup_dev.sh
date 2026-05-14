#!/usr/bin/env bash
# Development environment setup script.
# Run this once after cloning the repo on a new machine.
# Works on macOS (dev) and WSL2/Linux (company Windows PC).
set -euo pipefail

echo "=== Context-Hub dev setup ==="

# 1. Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python: $python_version"
required_minor=12
actual_minor=$(echo "$python_version" | cut -d. -f2)
if [ "$actual_minor" -lt "$required_minor" ]; then
    echo "ERROR: Python 3.12+ required, got $python_version"
    exit 1
fi

# 2. Create .env from example (if not already present)
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env from .env.example — fill in the real values on the company PC."
fi

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Verify Docker is available
if command -v docker &>/dev/null; then
    echo "Docker: $(docker --version)"
else
    echo "WARNING: Docker not found. You need Docker Desktop (Windows) or Docker Engine (Linux/Mac) to run the full stack."
fi

echo ""
echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. Fill in .env with real API keys (on company PC only)"
echo "  2. docker compose up -d  (starts PostgreSQL)"
echo "  3. python -m pytest      (run tests)"
echo "  4. uvicorn src.main:app --reload  (start API server)"
