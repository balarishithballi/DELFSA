"""
DELFSA correlation-engine
--------------------------
Consumes alerts from Redis (delfsa:alerts) and correlates them into
incidents. Correlation key is derived from the alert's source event
(source_ip if present, else source_host, else rule_id) and alerts are
grouped using a Redis sorted set as a sliding time window per key. When
the number of alerts for a key within CORRELATION_WINDOW_SECONDS reaches
CORRELATION_THRESHOLD, an incident is emitted to delfsa:incidents.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, "/shared/python")
from delfsa_common import GracefulShutdown, HeartbeatEmitter, get_logger, get_redis_client  # noqa: E402

SERVICE_NAME = "correlation-engine"
ALERTS_QUEUE = "delfsa:alerts"
INCIDENTS_QUEUE = "delfsa:incidents"
BLOCK_TIMEOUT_SECONDS = 5

CORRELATION_WINDOW_SECONDS = int(os.environ.get("CORRELATION_WINDOW_SECONDS", "300"))
CORRELATION_THRESHOLD = int(os.environ.get("CORRELATION_THRESHOLD", "3"))
# Cooldown prevents re-firing an incident every single alert once threshold is crossed
INCIDENT_COOLDOWN_SECONDS = int(os.environ.get("INCIDENT_COOLDOWN_SECONDS", "120"))

log = get_logger(SERVICE_NAME)


def get_field(event: dict, dotted_path: str) -> Any:
    node: Any = event
    for part in dotted_path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node


def derive_correlation_key(alert: dict) -> str:
    source_event = alert.get("source_event", {}) or {}
    source_ip = get_field(source_event, "parsed.source_ip")
    if source_ip:
        return f"ip:{source_ip}"
    source_host = source_event.get("source_host")
    if source_host:
        return f"host:{source_host}"
    return f"rule:{alert.get('rule_id', 'unknown')}"


def record_alert(r, key: str, alert_id: str, now: float) -> int:
    zset_key = f"delfsa:correlation:window:{key}"
    r.zadd(zset_key, {alert_id: now})
    r.zremrangebyscore(zset_key, 0, now - CORRELATION_WINDOW_SECONDS)
    r.expire(zset_key, CORRELATION_WINDOW_SECONDS * 2)
    return r.zcard(zset_key)


def in_cooldown(r, key: str) -> bool:
    return r.exists(f"delfsa:correlation:cooldown:{key}") == 1


def set_cooldown(r, key: str) -> None:
    r.set(f"delfsa:correlation:cooldown:{key}", "1", ex=INCIDENT_COOLDOWN_SECONDS)


def build_incident(key: str, alert_count: int, latest_alert: dict) -> dict:
    return {
        "incident_id": f"INC-{abs(hash(key + latest_alert.get('generated_at', ''))) % (10**10)}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "correlation_key": key,
        "alert_count_in_window": alert_count,
        "window_seconds": CORRELATION_WINDOW_SECONDS,
        "severity": latest_alert.get("severity", "low"),
        "triggering_rule_id": latest_alert.get("rule_id"),
        "triggering_rule_name": latest_alert.get("rule_name"),
        "mitre_attack_id": latest_alert.get("mitre_attack_id"),
        "latest_alert": latest_alert,
    }


def main() -> None:
    log.info(
        f"Starting correlation-engine window={CORRELATION_WINDOW_SECONDS}s "
        f"threshold={CORRELATION_THRESHOLD}"
    )
    r = get_redis_client()
    heartbeat = HeartbeatEmitter(r, SERVICE_NAME)
    shutdown = GracefulShutdown()

    processed_total = 0
    incidents_total = 0
    loop_count = 0

    while not shutdown.should_stop:
        loop_count += 1
        item = r.blpop(ALERTS_QUEUE, timeout=BLOCK_TIMEOUT_SECONDS)

        if item is not None:
            _, raw_json = item
            try:
                alert = json.loads(raw_json)
                processed_total += 1
                key = derive_correlation_key(alert)
                now = time.time()
                count = record_alert(r, key, alert.get("alert_id", str(now)), now)

                if count >= CORRELATION_THRESHOLD and not in_cooldown(r, key):
                    incident = build_incident(key, count, alert)
                    r.rpush(INCIDENTS_QUEUE, json.dumps(incident))
                    set_cooldown(r, key)
                    incidents_total += 1
                    log.info(
                        f"INCIDENT: {incident['incident_id']} key={key} "
                        f"count={count} rule={alert.get('rule_id')}"
                    )
            except (json.JSONDecodeError, TypeError) as err:
                log.error(f"Failed to process alert: {err}")

        heartbeat.beat({"processed_total": processed_total, "incidents_total": incidents_total})

        if loop_count % 30 == 0:
            log.info(f"heartbeat: processed_total={processed_total} incidents_total={incidents_total}")

    log.info("correlation-engine shutting down gracefully")


if __name__ == "__main__":
    main()
