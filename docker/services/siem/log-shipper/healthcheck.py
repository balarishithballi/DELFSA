"""Healthcheck: verifies the service's Redis heartbeat key is fresh."""
import json
import os
import sys
import time

sys.path.insert(0, "/shared/python")
from delfsa_common import get_redis_client  # noqa: E402

SERVICE_NAME = "log-shipper"
MAX_STALENESS_SECONDS = int(os.environ.get("HEALTHCHECK_MAX_STALENESS", "60"))


def main() -> int:
    try:
        r = get_redis_client(retries=1, retry_delay=0)
        key = f"delfsa:heartbeat:{SERVICE_NAME}"
        raw = r.get(key)
        if raw is None:
            print(f"UNHEALTHY: no heartbeat key {key}")
            return 1
        payload = json.loads(raw)
        ts = payload.get("timestamp")
        print(f"OK: last heartbeat at {ts}")
        return 0
    except Exception as err:  # noqa: BLE001
        print(f"UNHEALTHY: {err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
