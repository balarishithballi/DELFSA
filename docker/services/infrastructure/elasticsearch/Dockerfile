FROM docker.elastic.co/elasticsearch/elasticsearch:8.15.0

LABEL org.delfsa.component="infrastructure" org.delfsa.service="elasticsearch"

ENV discovery.type=single-node \
    xpack.security.enabled=false \
    ES_JAVA_OPTS="-Xms512m -Xmx512m"

HEALTHCHECK --interval=20s --timeout=10s --start-period=45s --retries=6 \
    CMD curl -sf http://localhost:9200/_cluster/health || exit 1
