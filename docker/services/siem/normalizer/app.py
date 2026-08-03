"""
DELFSA normalizer
------------------
Consumes raw log envelopes from Redis (delfsa:logs:raw), attempts to parse
common enterprise log formats (JSON, syslog-ish, key=value, nginx combined),
and produces a normalized event schema on delfsa:logs:normalized for the
detection engine to consume.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, "/shared/python")
from delfsa_common import GracefulShutdown, HeartbeatEmitter, get_logger, get_redis_client  # noqa: E402

SERVICE_NAME = "normalizer"
RAW_QUEUE = "delfsa:logs:raw"
NORMALIZED_QUEUE = "delfsa:logs:normalized"
BLOCK_TIMEOUT_SECONDS = 5

log = get_logger(SERVICE_NAME)

KV_PATTERN = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)')
SYSLOG_PATTERN = re.compile(
    r"^(?P<month>\w{3})\s+(?P<day>\d{1,2})\s+(?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>\S+)\s+(?P<process>[\w./-]+?)(\[(?P<pid>\d+)\])?:\s*(?P<message>.*)$"
)
NGINX_COMBINED_PATTERN = re.compile(
    r'(?P<remote_addr>\S+) - (?P<remote_user>\S+) \[(?P<time_local>[^\]]+)\] '
    r'"(?P<request>[^"]*)" (?P<status>\d{3}) (?P<body_bytes>\d+) '
    r'"(?P<referer>[^"]*)" "(?P<user_agent>[^"]*)"'
)


def try_parse_json(raw: str) -> dict | None:
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def try_parse_nginx(raw: str) -> dict | None:
    match = NGINX_COMBINED_PATTERN.search(raw)
    if not match:
        return None
    data = match.groupdict()
    method, _, rest = data.get("request", "").partition(" ")
    path, _, protocol = rest.partition(" ")
    return {
        "log_type": "nginx_access",
        "source_ip": data.get("remote_addr"),
        "http_method": method or None,
        "http_path": path or None,
        "http_protocol": protocol or None,
        "http_status": int(data["status"]) if data.get("status", "").isdigit() else None,
        "bytes_sent": int(data["body_bytes"]) if data.get("body_bytes", "").isdigit() else None,
        "user_agent": data.get("user_agent"),
        "referer": data.get("referer"),
    }


def try_parse_syslog(raw: str) -> dict | None:
    match = SYSLOG_PATTERN.match(raw)
    if not match:
        return None
    data = match.groupdict()
    return {
        "log_type": "syslog",
        "host": data.get("host"),
        "process": data.get("process"),
        "pid": data.get("pid"),
        "message": data.get("message"),
    }


def try_parse_kv(raw: str) -> dict | None:
    matches = KV_PATTERN.findall(raw)
    if len(matches) < 2:
        return None
    parsed = {}
    for key, value in matches:
        parsed[key] = value.strip('"')
    parsed["log_type"] = "key_value"
    return parsed


def normalize(envelope: dict) -> dict:
    raw_line = envelope.get("raw", "")

    parsed = (
        try_parse_json(raw_line)
        or try_parse_nginx(raw_line)
        or try_parse_syslog(raw_line)
        or try_parse_kv(raw_line)
        or {"log_type": "unstructured", "message": raw_line}
    )

    return {
        "event_id": f"{envelope.get('shipped_at', '')}-{abs(hash(raw_line)) % (10**8)}",
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "source_file": envelope.get("source_file"),
        "source_host": envelope.get("host"),
        "raw": raw_line,
        "parsed": parsed,
    }


def main() -> None:
    log.info("Starting normalizer")
    r = get_redis_client()
    heartbeat = HeartbeatEmitter(r, SERVICE_NAME)
    shutdown = GracefulShutdown()

    processed_total = 0
    loop_count = 0

    while not shutdown.should_stop:
        loop_count += 1
        item = r.blpop(RAW_QUEUE, timeout=BLOCK_TIMEOUT_SECONDS)

        if item is not None:
            _, raw_json = item
            try:
                envelope = json.loads(raw_json)
                normalized_event = normalize(envelope)
                r.rpush(NORMALIZED_QUEUE, json.dumps(normalized_event))
                processed_total += 1
            except (json.JSONDecodeError, TypeError) as err:
                log.error(f"Failed to normalize event: {err}")

        heartbeat.beat({"processed_total": processed_total})

        if loop_count % 30 == 0:
            log.info(f"heartbeat: processed_total={processed_total}")

    log.info("normalizer shutting down gracefully")


if __name__ == "__main__":
    main()
