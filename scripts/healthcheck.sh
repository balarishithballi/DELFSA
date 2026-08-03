#!/usr/bin/env bash
# DELFSA healthcheck: polls `docker compose ps` until all core services
# report healthy, or times out.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

TIMEOUT_SECONDS=180
INTERVAL_SECONDS=5
elapsed=0

echo "==> Waiting up to ${TIMEOUT_SECONDS}s for services to become healthy"

while [ "${elapsed}" -lt "${TIMEOUT_SECONDS}" ]; do
    unhealthy=$(docker compose ps --format '{{.Name}} {{.Health}}' 2>/dev/null | grep -v 'healthy' | grep -v '^$' || true)
    if [ -z "${unhealthy}" ]; then
        echo "==> All services healthy."
        docker compose ps
        exit 0
    fi
    sleep "${INTERVAL_SECONDS}"
    elapsed=$((elapsed + INTERVAL_SECONDS))
done

echo "==> Timed out waiting for healthy status. Current state:"
docker compose ps
exit 1
