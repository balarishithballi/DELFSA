#!/bin/sh
set -e
: "${REDIS_PASSWORD:?REDIS_PASSWORD must be set}"
envsubst '${REDIS_PASSWORD}' < /usr/local/etc/redis/redis.conf.template > /tmp/redis.conf
exec redis-server /tmp/redis.conf
