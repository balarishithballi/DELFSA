#!/usr/bin/env bash
# DELFSA setup: prepares the environment for first run.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "==> DELFSA setup starting"

if ! command -v docker &>/dev/null; then
    echo "ERROR: docker is not installed or not on PATH." >&2
    exit 1
fi

if ! docker compose version &>/dev/null; then
    echo "ERROR: 'docker compose' (v2 plugin) is required." >&2
    exit 1
fi

if [ ! -f .env ]; then
    echo "==> Creating .env from .env.example"
    cp .env.example .env
    echo "    Edit .env and change all 'change_me_*' passwords before continuing."
else
    echo "==> .env already exists, leaving as-is"
fi

echo "==> Creating required host directories"
mkdir -p volumes/postgres volumes/elasticsearch volumes/redis volumes/grafana
mkdir -p logs/log-shipper logs/normalizer logs/detection-engine logs/correlation-engine

echo "==> Building images (this can take several minutes on first run)"
docker compose build

echo "==> Setup complete. Next: ./scripts/start.sh"
