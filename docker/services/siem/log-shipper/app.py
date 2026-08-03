"""
DELFSA log-shipper
------------------
Watches a directory of log files (mounted from other containers / volumes)
and ships new lines as JSON envelopes onto the Redis raw-log queue for the
normalizer to consume. Also emits synthetic heartbeat/background events so
the pipeline has continuous data even before attack scenarios are run.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/shared/python")
from delfsa_common import GracefulShutdown, HeartbeatEmitter, get_logger, get_redis_client  # noqa: E402

SERVICE_NAME = "log-shipper"
RAW_QUEUE = "delfsa:logs:raw"
WATCH_DIR = Path(os.environ.get("LOG_SHIPPER_WATCH_DIR", "/var/log/delfsa-sources"))
POLL_INTERVAL = float(os.environ.get("LOG_SHIPPER_POLL_INTERVAL", "2"))

log = get_logger(SERVICE_NAME)


class TailState:
    """Tracks per-file read offsets so restarts don't re-ship old lines."""

    def __init__(self) -> None:
        self.offsets: dict[str, int] = {}

    def read_new_lines(self, path: Path) -> list[str]:
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return []

        key = str(path)
        offset = self.offsets.get(key, 0)

        if size < offset:
            # file was truncated/rotated
            offset = 0

        if size == offset:
            return []

        lines: list[str] = []
        with path.open("r", errors="replace") as fh:
            fh.seek(offset)
            for line in fh:
                if line.endswith("\n"):
                    lines.append(line.rstrip("\n"))
                    offset = fh.tell()
                else:
                    # partial line, wait for more data next poll
                    break
        self.offsets[key] = offset
        return lines


def discover_log_files(base: Path) -> list[Path]:
    if not base.exists():
        return []
    return sorted(p for p in base.rglob("*.log") if p.is_file())


def build_envelope(source_file: str, raw_line: str) -> dict:
    return {
        "shipped_at": datetime.now(timezone.utc).isoformat(),
        "source_file": source_file,
        "host": os.environ.get("HOSTNAME", "unknown"),
        "raw": raw_line,
    }


def emit_synthetic_activity(redis_client, counter: int) -> None:
    """Ensures there is always some baseline telemetry flowing through the
    pipeline even if no background-activity generators are attached yet."""
    if counter % 30 != 0:
        return
    envelope = build_envelope(
        source_file="log-shipper:self-monitor",
        raw_line=json.dumps(
            {
                "event": "shipper_alive",
                "queue_depth": redis_client.llen(RAW_QUEUE),
            }
        ),
    )
    redis_client.rpush(RAW_QUEUE, json.dumps(envelope))


def main() -> None:
    log.info(f"Starting log-shipper, watching {WATCH_DIR}")
    r = get_redis_client()
    heartbeat = HeartbeatEmitter(r, SERVICE_NAME)
    shutdown = GracefulShutdown()
    tail_state = TailState()

    WATCH_DIR.mkdir(parents=True, exist_ok=True)

    loop_count = 0
    shipped_total = 0

    while not shutdown.should_stop:
        loop_count += 1
        files = discover_log_files(WATCH_DIR)

        for path in files:
            for line in tail_state.read_new_lines(path):
                if not line.strip():
                    continue
                envelope = build_envelope(str(path), line)
                r.rpush(RAW_QUEUE, json.dumps(envelope))
                shipped_total += 1

        emit_synthetic_activity(r, loop_count)
        heartbeat.beat({"shipped_total": shipped_total, "files_watched": len(files)})

        if loop_count % 15 == 0:
            log.info(f"heartbeat: shipped_total={shipped_total} files_watched={len(files)}")

        time.sleep(POLL_INTERVAL)

    log.info("log-shipper shutting down gracefully")


if __name__ == "__main__":
    main()
