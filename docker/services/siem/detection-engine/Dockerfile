# DELFSA SIEM service: detection-engine
FROM python:3.12-slim AS base

LABEL org.delfsa.component="siem" org.delfsa.service="detection-engine"

RUN groupadd --gid 10001 delfsa && \
    useradd --uid 10001 --gid delfsa --shell /usr/sbin/nologin --create-home delfsa

WORKDIR /app

COPY docker/services/siem/detection-engine/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

COPY shared/python /shared/python
COPY docker/services/siem/detection-engine/app.py /app/app.py
COPY docker/services/siem/detection-engine/healthcheck.py /app/healthcheck.py

RUN mkdir -p /var/log/delfsa-sources && chown -R delfsa:delfsa /app /shared /var/log/delfsa-sources

USER delfsa

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python /app/healthcheck.py || exit 1

ENTRYPOINT ["python", "/app/app.py"]
