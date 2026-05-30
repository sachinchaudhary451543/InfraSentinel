#!/usr/bin/env bash
set -euo pipefail

# Run the project's pytest suite (migrations + smoke tests)
echo "Running CI tests (migrations + smoke tests)"
pytest -q
