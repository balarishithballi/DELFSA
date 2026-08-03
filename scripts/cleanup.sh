#!/usr/bin/env bash
# DELFSA cleanup: stops and removes containers, networks, and (optionally)
# volumes/images. Destructive — prompts for confirmation.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

read -r -p "This will remove all DELFSA containers and networks. Continue? [y/N] " confirm
if [[ "${confirm}" != "y" && "${confirm}" != "Y" ]]; then
    echo "Aborted."
    exit 0
fi

docker compose --profile attack down

read -r -p "Also remove data volumes (irreversible data loss)? [y/N] " confirm_volumes
if [[ "${confirm_volumes}" == "y" || "${confirm_volumes}" == "Y" ]]; then
    docker compose --profile attack down -v
    echo "==> Volumes removed."
fi

read -r -p "Also remove built images? [y/N] " confirm_images
if [[ "${confirm_images}" == "y" || "${confirm_images}" == "Y" ]]; then
    docker images "delfsa/*" -q | xargs -r docker rmi -f
    echo "==> Images removed."
fi

echo "==> Cleanup complete."
