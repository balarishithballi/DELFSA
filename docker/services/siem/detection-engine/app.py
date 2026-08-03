"""
DELFSA detection-engine
------------------------
Consumes normalized events from Redis (delfsa:logs:normalized), evaluates
them against detection rules loaded from /rules/*.yml, and pushes any
matches as alerts onto delfsa:alerts for the correlation engine.

Rule file format (YAML):

    - id: RULE-001
      name: "Repeated failed SSH logins"
      severity: medium
      match:
        field: parsed.process
        equals: sshd
      contains:
        field: parsed.message
        substring: "Failed password"
      mitre: T1110

Supported matchers per rule (all optional, all must pass if present):
  - equals:   {field, value}
  - contains: {field, substring}
  - regex:    {field, pattern}
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, "/shared/python")
from delfsa_common import GracefulShutdown, HeartbeatEmitter, get_logger, get_redis_client  # noqa: E402

SERVICE_NAME = "detection-engine"
NORMALIZED_QUEUE = "delfsa:logs:normalized"
ALERTS_QUEUE = "delfsa:alerts"
RULES_DIR = Path("/rules")
RULES_RELOAD_INTERVAL = 60  # seconds
BLOCK_TIMEOUT_SECONDS = 5

log = get_logger(SERVICE_NAME)


def get_field(event: dict, dotted_path: str) -> Any:
    node: Any = event
    for part in dotted_path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node


def load_rules(rules_dir: Path) -> list[dict]:
    rules: list[dict] = []
    if not rules_dir.exists():
        return rules
    for path in sorted(rules_dir.glob("*.yml")) + sorted(rules_dir.glob("*.yaml")):
        try:
            with path.open() as fh:
                loaded = yaml.safe_load(fh) or []
            if isinstance(loaded, list):
                for rule in loaded:
                    rule["_source_file"] = str(path)
                    rules.append(rule)
        except yaml.YAMLError as err:
            log.error(f"Failed to load rule file {path}: {err}")
    return rules


def rule_matches(rule: dict, event: dict) -> bool:
    checks_present = False

    equals = rule.get("match")
    if equals:
        checks_present = True
        value = get_field(event, equals.get("field", ""))
        if str(value) != str(equals.get("value", equals.get("equals", ""))):
            return False

    contains = rule.get("contains")
    if contains:
        checks_present = True
        value = get_field(event, contains.get("field", ""))
        substring = contains.get("substring", "")
        if value is None or substring not in str(value):
            return False

    regex_rule = rule.get("regex")
    if regex_rule:
        checks_present = True
        value = get_field(event, regex_rule.get("field", ""))
        pattern = regex_rule.get("pattern", "")
        if value is None or not re.search(pattern, str(value)):
            return False

    return checks_present


def build_alert(rule: dict, event: dict) -> dict:
    return {
        "alert_id": f"{rule.get('id', 'UNKNOWN')}-{abs(hash(event.get('event_id', ''))) % (10**8)}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rule_id": rule.get("id"),
        "rule_name": rule.get("name"),
        "severity": rule.get("severity", "low"),
        "mitre_attack_id": rule.get("mitre"),
        "source_event": event,
    }


def main() -> None:
    log.info(f"Starting detection-engine, loading rules from {RULES_DIR}")
    r = get_redis_client()
    heartbeat = HeartbeatEmitter(r, SERVICE_NAME)
    shutdown = GracefulShutdown()

    rules = load_rules(RULES_DIR)
    log.info(f"Loaded {len(rules)} detection rule(s)")

    last_reload = time.time()
    processed_total = 0
    alerts_total = 0
    loop_count = 0

    while not shutdown.should_stop:
        loop_count += 1

        if time.time() - last_reload > RULES_RELOAD_INTERVAL:
            rules = load_rules(RULES_DIR)
            last_reload = time.time()
            log.info(f"Reloaded {len(rules)} detection rule(s)")

        item = r.blpop(NORMALIZED_QUEUE, timeout=BLOCK_TIMEOUT_SECONDS)

        if item is not None:
            _, raw_json = item
            try:
                event = json.loads(raw_json)
                processed_total += 1
                for rule in rules:
                    if rule_matches(rule, event):
                        alert = build_alert(rule, event)
                        r.rpush(ALERTS_QUEUE, json.dumps(alert))
                        alerts_total += 1
                        log.info(f"ALERT: {alert['rule_id']} - {alert['rule_name']}")
            except (json.JSONDecodeError, TypeError) as err:
                log.error(f"Failed to process event: {err}")

        heartbeat.beat({"processed_total": processed_total, "alerts_total": alerts_total, "rules_loaded": len(rules)})

        if loop_count % 30 == 0:
            log.info(f"heartbeat: processed_total={processed_total} alerts_total={alerts_total}")

    log.info("detection-engine shutting down gracefully")


if __name__ == "__main__":
    main()
