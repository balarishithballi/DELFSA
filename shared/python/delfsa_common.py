"""
DELFSA shared utilities: Redis connection helper, structured logging,
heartbeat emission, and graceful shutdown handling.

Used by: log-shipper, normalizer, detection-engine, correlation-engine
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any, Optional

import redis


def get_logger(service_name: str) -> logging.Logger:
    """Return a JSON-line structured logger writing to stdout."""
    logger = logging.getLogger(service_name)
    if logger.handlers:
        return logger
    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())

    handler = logging.StreamHandler(sys.stdout)

    class JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "service": service_name,
                "level": record.levelname,
                "message": record.getMessage(),
            }
            if record.exc_info:
                payload["exception"] = self.formatException(record.exc_info)
            return json.dumps(payload)

    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def get_redis_client(
    host: Optional[str] = None,
    port: Optional[int] = None,
    db: int = 0,
    password: Optional[str] = None,
    retries: int = 10,
    retry_delay: float = 3.0,
) -> redis.Redis:
    """Create a Redis client, retrying until Redis is reachable."""
    host = host or os.environ.get("REDIS_HOST", "redis")
    port = port or int(os.environ.get("REDIS_PORT", "6379"))
    password = password or os.environ.get("REDIS_PASSWORD") or None

    last_err: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            client = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=None,
            )
            client.ping()
            return client
        except Exception as err:  # noqa: BLE001
            last_err = err
            time.sleep(retry_delay)
    raise ConnectionError(
        f"Could not connect to Redis at {host}:{port} after {retries} attempts: {last_err}"
    )


class HeartbeatEmitter:
    """Periodically writes a heartbeat key to Redis so healthchecks/monitoring
    can confirm the service loop is alive (not just that the process exists)."""

    def __init__(self, client: redis.Redis, service_name: str, ttl_seconds: int = 30):
        self.client = client
        self.key = f"delfsa:heartbeat:{service_name}"
        self.ttl_seconds = ttl_seconds

    def beat(self, extra: Optional[dict[str, Any]] = None) -> None:
        payload = {
            "service": self.key,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
        }
        if extra:
            payload.update(extra)
        self.client.set(self.key, json.dumps(payload), ex=self.ttl_seconds)


class GracefulShutdown:
    """Sets a flag on SIGTERM/SIGINT so long-running loops can exit cleanly."""

    def __init__(self) -> None:
        self.should_stop = False
        signal.signal(signal.SIGTERM, self._handle)
        signal.signal(signal.SIGINT, self._handle)

    def _handle(self, signum, frame) -> None:  # noqa: ANN001
        self.should_stop = True
