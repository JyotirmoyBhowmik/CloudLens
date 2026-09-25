#!/usr/bin/env bash
set -euo pipefail

echo ">>> Starting CloudLens Developer Bootstrap..."

if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required but was not found on PATH." >&2
    exit 1
fi

python3 scripts/bootstrap.py

echo ">>> To start the API server locally: uvicorn api.cloudlens_api.main:app --reload --port 8000"
echo ">>> To start the Web server: cd web && pnpm dev"
