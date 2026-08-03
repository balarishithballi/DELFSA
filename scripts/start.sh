#!/usr/bin/env bash
# DELFSA start: brings up the core stack (add --profile attack for kali).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ ! -f .env ]; then
    echo "ERROR: .env not found. Run ./scripts/setup.sh first." >&2
    exit 1
fi

echo "==> Starting DELFSA core stack"
docker compose up -d

echo "==> Waiting for core services to report healthy..."
"$(dirname "${BASH_SOURCE[0]}")/healthcheck.sh" || true

echo "==> Started. Kibana: http://localhost:\${KIBANA_PORT:-5601}  Grafana: http://localhost:\${GRAFANA_PORT:-3000}"
echo "==> To include the attacker node: docker compose --profile attack up -d kali"
