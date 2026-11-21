#!/usr/bin/env bash
set -e

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

source .venv/Scripts/activate

export TECHOHUB_RUNTIME=local
export TECHOHUB_LOCAL_DATABASE_URL="sqlite:///$(pwd)/data/voice_manual_test.db"
export TECHOHUB_RAG_ENABLED=false
export TECHOHUB_MCP_ENABLED=false

exec python -m backend.local --port 8000
