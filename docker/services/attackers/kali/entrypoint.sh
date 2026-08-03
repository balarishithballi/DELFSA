#!/bin/bash
# Keeps the attacker container alive and ready for operators to `docker exec`
# in and run attack-scenarios/ playbooks against in-lab targets.
set -e
echo "[delfsa-kali] attacker node ready. Use 'docker compose exec kali bash' and see /attack-scenarios."
tail -f /dev/null
