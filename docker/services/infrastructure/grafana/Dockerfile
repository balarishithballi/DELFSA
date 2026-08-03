FROM grafana/grafana:11.2.0

LABEL org.delfsa.component="infrastructure" org.delfsa.service="grafana"

COPY configs/grafana/provisioning /etc/grafana/provisioning

ENV GF_SECURITY_ALLOW_EMBEDDING=true \
    GF_AUTH_ANONYMOUS_ENABLED=false

HEALTHCHECK --interval=20s --timeout=10s --start-period=20s --retries=5 \
    CMD wget -qO- http://localhost:3000/api/health || exit 1
