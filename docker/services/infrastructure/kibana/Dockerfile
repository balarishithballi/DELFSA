FROM docker.elastic.co/kibana/kibana:8.15.0

LABEL org.delfsa.component="infrastructure" org.delfsa.service="kibana"

COPY docker/services/infrastructure/kibana/kibana.yml /usr/share/kibana/config/kibana.yml

HEALTHCHECK --interval=20s --timeout=10s --start-period=45s --retries=6 \
    CMD curl -sf http://localhost:5601/api/status || exit 1
