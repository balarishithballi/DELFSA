#!/usr/bin/env bash
# DELFSA stop: stops all running containers without removing volumes.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "==> Stopping DELFSA stack"
docker compose --profile attack stop
echo "==> Stopped. Data volumes preserved. Use cleanup.sh to remove everything."
