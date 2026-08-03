FROM redis:7.4-alpine

LABEL org.delfsa.component="infrastructure" org.delfsa.service="redis"

RUN apk add --no-cache gettext

COPY configs/redis/redis.conf.template /usr/local/etc/redis/redis.conf.template
COPY docker/services/infrastructure/redis/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN mkdir -p /data && \
    chown -R redis:redis /data /usr/local/etc/redis && \
    chmod +x /usr/local/bin/entrypoint.sh

USER redis

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD redis-cli -a "$REDIS_PASSWORD" --no-auth-warning ping | grep -q PONG || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
