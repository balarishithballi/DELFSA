FROM postgres:16-alpine

LABEL org.delfsa.component="infrastructure" org.delfsa.service="postgres"

COPY docker/services/infrastructure/postgres/init.sql /docker-entrypoint-initdb.d/01-init.sql

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=5 \
    CMD pg_isready -U "${POSTGRES_USER:-delfsa}" -d "${POSTGRES_DB:-delfsa}" || exit 1
