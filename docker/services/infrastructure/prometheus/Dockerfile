FROM prom/prometheus:v2.54.1

LABEL org.delfsa.component="infrastructure" org.delfsa.service="prometheus"

COPY configs/prometheus/prometheus.yml /etc/prometheus/prometheus.yml

HEALTHCHECK --interval=20s --timeout=10s --start-period=20s --retries=5 \
    CMD wget -qO- http://localhost:9090/-/healthy || exit 1

ENTRYPOINT ["/bin/prometheus", "--config.file=/etc/prometheus/prometheus.yml", "--storage.tsdb.path=/prometheus"]
